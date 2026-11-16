"""ASGI middleware: every request needs a valid bearer token before it reaches the app."""

import json

from starlette.authentication import SimpleUser
from starlette.types import ASGIApp, Receive, Scope, Send

from margin_copilot_shared.security.context import RequestContext, request_scope
from margin_copilot_shared.security.tokens import TokenRejected, TokenValidator


class AuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        validator: TokenValidator,
        public_paths: frozenset[str] = frozenset(),
    ) -> None:
        self.app = app
        self.validator = validator
        self.public_paths = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.public_paths:
            await self.app(scope, receive, send)
            return
        token = _bearer_token(scope)
        try:
            if token is None:
                raise TokenRejected(401, "missing bearer token")
            caller = self.validator.validate(token)
        except TokenRejected as rejected:
            await _reject(send, rejected)
            return
        scope["user"] = SimpleUser(caller.oid)
        with request_scope(RequestContext(caller=caller, token=token)):
            await self.app(scope, receive, send)


def _bearer_token(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
    return None


async def _reject(send: Send, rejected: TokenRejected) -> None:
    error = "insufficient_scope" if rejected.status == 403 else "invalid_token"
    body = json.dumps({"error": rejected.reason}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": rejected.status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", f'Bearer error="{error}"'.encode()),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
