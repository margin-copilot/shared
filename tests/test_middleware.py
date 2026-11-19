import asyncio

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from margin_copilot_shared.security.context import RequestContext, current_request
from margin_copilot_shared.security.middleware import AuthMiddleware
from margin_copilot_shared.security.tokens import Caller
from margin_copilot_shared.testing.issuer import LocalIssuer

API = "api-client-id"
CLIENT = "allowed-client-id"


@pytest.fixture
def issuer():
    return LocalIssuer()


@pytest.fixture
def client(issuer):
    async def whoami(request):
        await asyncio.sleep(0.01)  # let concurrent requests interleave
        return JSONResponse({"oid": current_request().caller.oid})

    async def card(request):
        return JSONResponse({"name": "public"})

    app = Starlette(
        routes=[Route("/whoami", whoami), Route("/card", card)],
        middleware=[
            Middleware(
                AuthMiddleware,
                validator=issuer.validator(audience=API, allowed_callers=frozenset({CLIENT})),
                public_paths=frozenset({"/card"}),
            )
        ],
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://svc")


async def test_missing_token_is_401_with_challenge(client):
    response = await client.get("/whoami")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert response.json() == {"error": "missing bearer token"}


async def test_non_bearer_scheme_is_401(client):
    response = await client.get("/whoami", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401


async def test_unlisted_caller_is_403(client, issuer):
    token = issuer.issue(audience=API, azp="unlisted")
    response = await client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.headers["www-authenticate"] == 'Bearer error="insufficient_scope"'


async def test_rejection_never_echoes_the_token(client, issuer):
    token = issuer.issue(audience="other-api", azp=CLIENT)
    response = await client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert token not in response.text


async def test_valid_token_reaches_handler_with_caller(client, issuer):
    token = issuer.issue(audience=API, azp=CLIENT, oid="user-1")
    response = await client.get("/whoami", headers={"Authorization": f"bearer {token}"})
    assert response.json() == {"oid": "user-1"}


async def test_public_path_needs_no_token(client):
    assert (await client.get("/card")).status_code == 200


async def test_concurrent_requests_see_their_own_caller(client, issuer):
    async def call(oid):
        token = issuer.issue(audience=API, azp=CLIENT, oid=oid)
        response = await client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        return response.json()["oid"]

    oids = [f"user-{n}" for n in range(20)]
    assert await asyncio.gather(*(call(oid) for oid in oids)) == oids


async def test_context_is_cleared_after_the_request(client, issuer):
    token = issuer.issue(audience=API, azp=CLIENT)
    await client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    with pytest.raises(RuntimeError, match="no authenticated request"):
        current_request()


def test_request_context_repr_hides_the_token():
    caller = Caller(oid="u", tid="t", azp="a", scopes=frozenset())
    assert "secret-token" not in repr(RequestContext(caller=caller, token="secret-token"))


async def websocket_handshake(issuer, headers):
    """Drives AuthMiddleware over raw ASGI; returns what reached the client."""

    async def echo_caller(scope, receive, send):
        await receive()
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.send", "text": current_request().caller.oid})

    validator = issuer.validator(audience=API, allowed_callers=frozenset({CLIENT}))
    middleware = AuthMiddleware(echo_caller, validator=validator)
    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "websocket", "path": "/ws", "headers": headers}
    await middleware(scope, receive, send)
    return sent


async def test_websocket_without_token_is_closed_with_policy_violation(issuer):
    assert await websocket_handshake(issuer, []) == [{"type": "websocket.close", "code": 1008}]


async def test_websocket_with_valid_token_sees_its_caller(issuer):
    token = issuer.issue(audience=API, azp=CLIENT, oid="user-ws")
    sent = await websocket_handshake(issuer, [(b"authorization", f"Bearer {token}".encode())])
    assert sent == [
        {"type": "websocket.accept"},
        {"type": "websocket.send", "text": "user-ws"},
    ]
