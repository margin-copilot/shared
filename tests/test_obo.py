import pytest

from margin_copilot_shared.security.obo import OboClient, OboFailed


class StubMsal:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def acquire_token_on_behalf_of(self, user_assertion, scopes):
        self.calls.append((user_assertion, scopes))
        return self.result


def test_exchange_returns_the_new_token_for_the_requested_scope():
    stub = StubMsal({"access_token": "downstream-token"})
    obo = OboClient("tenant", "client", lambda: "assertion", app=stub)
    assert obo.exchange("user-token", ["api://next/access_as_user"]) == "downstream-token"
    assert stub.calls == [("user-token", ["api://next/access_as_user"])]


def test_exchange_failure_raises_with_the_error_code_and_claims():
    stub = StubMsal({"error": "interaction_required", "claims": '{"access_token":{}}'})
    obo = OboClient("tenant", "client", lambda: "assertion", app=stub)
    with pytest.raises(OboFailed) as info:
        obo.exchange("user-token", ["api://next/access_as_user"])
    assert (info.value.error, info.value.claims) == ("interaction_required", '{"access_token":{}}')


def test_failure_keeps_the_entra_error_codes():
    stub = StubMsal({"error": "invalid_client", "error_codes": [70021]})
    obo = OboClient("tenant", "client", lambda: "assertion", app=stub)
    with pytest.raises(OboFailed) as info:
        obo.exchange("user-token", ["api://next/access_as_user"])
    assert info.value.error_codes == (70021,)
    assert str(info.value) == "invalid_client AADSTS70021"
