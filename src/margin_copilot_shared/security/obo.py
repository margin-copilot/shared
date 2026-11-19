"""On-behalf-of exchange: trade the caller's token for one addressed to the next service."""

from collections.abc import Callable, Sequence
from typing import Any

import msal
from azure.identity import ManagedIdentityCredential

TOKEN_EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"


class OboFailed(Exception):
    def __init__(
        self, error: str, claims: str | None = None, error_codes: tuple[int, ...] = ()
    ) -> None:
        codes = " ".join(f"AADSTS{code}" for code in error_codes)
        super().__init__(f"{error} {codes}".strip())
        self.error = error
        self.claims = claims
        self.error_codes = error_codes


def managed_identity_assertion(managed_identity_client_id: str) -> Callable[[], str]:
    """Client assertion from a user-assigned managed identity trusted by the app (no secrets)."""
    credential = ManagedIdentityCredential(client_id=managed_identity_client_id)
    return lambda: credential.get_token(TOKEN_EXCHANGE_SCOPE).token


class OboClient:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_assertion: Callable[[], str],
        app: Any = None,
    ) -> None:
        self._app = app or msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential={"client_assertion": client_assertion},
        )

    def exchange(self, user_token: str, scopes: Sequence[str]) -> str:
        # ponytail: msal doesn't cache OBO results, so every call hits Entra; add a cache keyed
        # by (token hash, scopes) if latency matters.
        result = self._app.acquire_token_on_behalf_of(user_token, list(scopes))
        if "access_token" not in result:
            raise OboFailed(
                result.get("error", "unknown_error"),
                result.get("claims"),
                tuple(result.get("error_codes", ())),
            )
        return result["access_token"]
