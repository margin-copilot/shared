import jwt
import pytest

from margin_copilot_shared.security.tokens import TokenRejected, entra_validator
from margin_copilot_shared.testing.issuer import LocalIssuer

API = "api-client-id"
CLIENT = "allowed-client-id"


@pytest.fixture
def issuer():
    return LocalIssuer()


@pytest.fixture
def validator(issuer):
    return issuer.validator(audience=API, allowed_callers=frozenset({CLIENT}))


def rejected(validator, token):
    with pytest.raises(TokenRejected) as info:
        validator.validate(token)
    return info.value.status, info.value.reason


def test_valid_token_returns_caller(issuer, validator):
    caller = validator.validate(issuer.issue(audience=API, azp=CLIENT, oid="user-1"))
    assert (caller.oid, caller.azp, caller.tid) == ("user-1", CLIENT, issuer.tenant_id)
    assert "access_as_user" in caller.scopes


def test_expired_token_is_401(issuer, validator):
    token = issuer.issue(audience=API, azp=CLIENT, lifetime=-60)
    assert rejected(validator, token) == (401, "invalid token (ExpiredSignatureError)")


def test_token_signed_by_another_key_is_401(validator):
    other = LocalIssuer()  # same issuer string and tenant, different key
    token = other.issue(audience=API, azp=CLIENT)
    assert rejected(validator, token) == (401, "invalid token (InvalidSignatureError)")


def test_wrong_issuer_is_401(validator):
    token = LocalIssuer(tenant_id="22222222-2222-2222-2222-222222222222").issue(
        audience=API, azp=CLIENT
    )
    assert rejected(validator, token) == (401, "wrong issuer")


def test_token_for_another_service_is_401(issuer, validator):
    token = issuer.issue(audience="some-other-api", azp=CLIENT)
    assert rejected(validator, token) == (401, "invalid token (InvalidAudienceError)")


def test_v1_token_is_401(issuer, validator):
    token = issuer.issue(audience=API, azp=CLIENT, ver="1.0")
    assert rejected(validator, token) == (401, "wrong token version or tenant")


def test_other_tenant_claim_is_401(issuer, validator):
    token = issuer.issue(audience=API, azp=CLIENT, tid="33333333-3333-3333-3333-333333333333")
    assert rejected(validator, token) == (401, "wrong token version or tenant")


def test_missing_azp_is_401(issuer, validator):
    token = issuer.issue(audience=API, azp=CLIENT, drop=("azp",))
    assert rejected(validator, token) == (401, "invalid token (MissingRequiredClaimError)")


def test_unsigned_token_is_401(issuer, validator):
    claims = jwt.decode(issuer.issue(audience=API, azp=CLIENT), options={"verify_signature": False})
    token = jwt.encode(claims, key=None, algorithm="none")
    assert rejected(validator, token)[0] == 401


def test_hs256_token_is_401(issuer, validator):
    claims = jwt.decode(issuer.issue(audience=API, azp=CLIENT), options={"verify_signature": False})
    token = jwt.encode(claims, key="a-shared-secret-of-thirty-two-bytes!", algorithm="HS256")
    assert rejected(validator, token)[0] == 401


def test_garbage_is_401(validator):
    assert rejected(validator, "not-a-jwt") == (401, "malformed token")


def test_missing_scope_is_403(issuer, validator):
    token = issuer.issue(audience=API, azp=CLIENT, scp="something.else")
    assert rejected(validator, token) == (403, "missing scope")


def test_unlisted_calling_app_is_403(issuer, validator):
    token = issuer.issue(audience=API, azp="unlisted-client-id")
    assert rejected(validator, token) == (403, "calling app not allowed")


def test_entra_validator_rejects_local_issuer_tokens_without_network(issuer):
    validator = entra_validator(issuer.tenant_id, API, frozenset({CLIENT}))
    token = issuer.issue(audience=API, azp=CLIENT)
    assert rejected(validator, token) == (401, "wrong issuer")


def test_groups_come_from_the_token(issuer, validator):
    caller = validator.validate(issuer.issue(audience=API, azp=CLIENT, groups=["g1", "g2"]))
    assert caller.groups == frozenset({"g1", "g2"})
    assert caller.groups_overage is False


def test_no_groups_claim_means_no_groups(issuer, validator):
    caller = validator.validate(issuer.issue(audience=API, azp=CLIENT))
    assert caller.groups == frozenset()
    assert caller.groups_overage is False


@pytest.mark.parametrize("overage", [{"_claim_names": {"groups": "src1"}}, {"hasgroups": True}])
def test_group_overage_is_flagged(issuer, validator, overage):
    caller = validator.validate(issuer.issue(audience=API, azp=CLIENT, **overage))
    assert caller.groups_overage is True
    assert caller.groups == frozenset()


def test_a_groups_claim_that_isnt_a_list_of_strings_is_rejected(issuer, validator):
    token = issuer.issue(audience=API, azp=CLIENT, groups="g1")
    assert rejected(validator, token) == (401, "malformed groups claim")
