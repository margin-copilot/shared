"""Validates Entra v2 access tokens: signature, issuer, tenant, audience, scope and calling app."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt

ALGORITHMS = ["RS256"]
REQUIRED_CLAIMS = ["exp", "nbf", "iss", "aud", "tid", "oid", "azp", "ver"]


class TokenRejected(Exception):
    """401 for a token we can't trust, 403 for a trusted token without the right scope or caller."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass(frozen=True)
class Caller:
    oid: str
    tid: str
    azp: str
    scopes: frozenset[str]
    groups: frozenset[str] = frozenset()  # Entra group object IDs, when the app requests them
    groups_overage: bool = False  # too many groups for the token: callers must fail closed


@dataclass(frozen=True)
class TokenPolicy:
    issuer: str
    tenant_id: str
    audience: str
    required_scope: str
    allowed_callers: frozenset[str]


SigningKey = Callable[[str], Any]


class TokenValidator:
    def __init__(self, policy: TokenPolicy, signing_key: SigningKey) -> None:
        self._policy = policy
        self._signing_key = signing_key

    def validate(self, token: str) -> Caller:
        policy = self._policy
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            raise TokenRejected(401, "malformed token") from None
        # Checked before any key lookup, so foreign tokens never trigger a JWKS fetch.
        if unverified.get("iss") != policy.issuer:
            raise TokenRejected(401, "wrong issuer")
        try:
            claims = jwt.decode(
                token,
                self._signing_key(token),
                algorithms=ALGORITHMS,
                audience=policy.audience,
                issuer=policy.issuer,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as error:
            raise TokenRejected(401, f"invalid token ({type(error).__name__})") from None
        if claims["ver"] != "2.0" or claims["tid"] != policy.tenant_id:
            raise TokenRejected(401, "wrong token version or tenant")
        scopes = frozenset(str(claims.get("scp", "")).split())
        if policy.required_scope not in scopes:
            raise TokenRejected(403, "missing scope")
        if claims["azp"] not in policy.allowed_callers:
            raise TokenRejected(403, "calling app not allowed")
        groups = claims.get("groups", [])
        if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
            raise TokenRejected(401, "malformed groups claim")
        overage = "groups" in claims.get("_claim_names", {}) or bool(claims.get("hasgroups"))
        return Caller(
            oid=claims["oid"],
            tid=claims["tid"],
            azp=claims["azp"],
            scopes=scopes,
            groups=frozenset() if overage else frozenset(groups),
            groups_overage=overage,
        )


def entra_validator(
    tenant_id: str,
    audience: str,
    allowed_callers: frozenset[str],
    required_scope: str = "access_as_user",
) -> TokenValidator:
    """Validator for real Entra tokens. The only one a deployed service may use."""
    jwks = jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys", lifespan=3600
    )
    policy = TokenPolicy(
        issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        tenant_id=tenant_id,
        audience=audience,
        required_scope=required_scope,
        allowed_callers=allowed_callers,
    )
    return TokenValidator(policy, lambda token: jwks.get_signing_key_from_jwt(token).key)
