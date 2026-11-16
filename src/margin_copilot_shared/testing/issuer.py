"""Local token issuer for tests and ADAPTERS=fake. A deployed service never trusts it (D-019)."""

import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from margin_copilot_shared.security.tokens import TokenPolicy, TokenValidator

LOCAL_TENANT = "11111111-1111-1111-1111-111111111111"


class LocalIssuer:
    def __init__(self, tenant_id: str = LOCAL_TENANT) -> None:
        self.tenant_id = tenant_id
        self.issuer = f"https://local-issuer.invalid/{tenant_id}/v2.0"
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def issue(
        self,
        *,
        audience: str,
        azp: str,
        scp: str = "access_as_user",
        oid: str | None = None,
        lifetime: int = 600,
        drop: tuple[str, ...] = (),
        **overrides: object,
    ) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": self.issuer,
            "aud": audience,
            "azp": azp,
            "scp": scp,
            "oid": oid or str(uuid.uuid4()),
            "tid": self.tenant_id,
            "ver": "2.0",
            "iat": now,
            "nbf": now,
            "exp": now + lifetime,
        }
        claims.update(overrides)
        for name in drop:
            claims.pop(name, None)
        return jwt.encode(claims, self._key, algorithm="RS256")

    def validator(
        self,
        *,
        audience: str,
        allowed_callers: frozenset[str],
        required_scope: str = "access_as_user",
    ) -> TokenValidator:
        policy = TokenPolicy(
            issuer=self.issuer,
            tenant_id=self.tenant_id,
            audience=audience,
            required_scope=required_scope,
            allowed_callers=allowed_callers,
        )
        public_key = self._key.public_key()
        return TokenValidator(policy, lambda _token: public_key)
