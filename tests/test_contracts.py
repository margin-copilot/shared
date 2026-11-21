from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from margin_copilot_shared.contracts import (
    MAX_ANSWER_CHARS,
    AgentReply,
    DraftRequest,
    Proposal,
    ProposalError,
)


def test_a_reply_carries_an_answer_and_an_optional_refusal():
    assert AgentReply(answer="21.3%").refusal is None
    assert AgentReply(answer="That's the South.", refusal="no_access").refusal == "no_access"


@pytest.mark.parametrize(
    "raw",
    [
        {"answer": ""},
        {"answer": "x" * (MAX_ANSWER_CHARS + 1)},
        {"answer": "ok", "refusal": "maybe"},
        {"answer": "ok", "approved": True},
        {"refusal": "no_data"},
        {"answer": 42},
    ],
)
def test_malformed_replies_are_rejected(raw):
    with pytest.raises(ValidationError):
        AgentReply.model_validate(raw)


def test_a_reply_can_carry_citations():
    reply = AgentReply(answer="x", citations=["PP-04 §3.2", "PP-05-N §2"])
    assert reply.citations == ["PP-04 §3.2", "PP-05-N §2"]
    assert AgentReply(answer="x").citations == []


@pytest.mark.parametrize(
    "citations", [["PP-4 §3"], ["see PP-04"], ["PP-04 §3.2"] * 13, ["PP-05-X §1"]]
)
def test_bad_citations_are_rejected(citations):
    with pytest.raises(ValidationError):
        AgentReply(answer="x", citations=citations)


@pytest.mark.parametrize(
    ("fields", "valid"),
    [
        ({"new_price": Decimal("7.25")}, True),
        ({"change_pct": Decimal("7")}, True),
        ({"new_price": Decimal("7.25"), "change_pct": Decimal("3.6")}, False),
        ({}, False),
    ],
)
def test_a_draft_names_a_new_price_or_a_percent(fields, valid):
    if valid:
        DraftRequest(product="UHT milk 1 L", region="N", **fields)
    else:
        with pytest.raises(ValidationError):
            DraftRequest(product="UHT milk 1 L", region="N", **fields)


@pytest.mark.parametrize("extra", [{"tier": "C"}, {"current_price": Decimal("1.00")}])
def test_a_draft_request_cannot_carry_tier_or_price(extra):
    with pytest.raises(ValidationError):
        DraftRequest(product="Fresh milk 1 L", new_price=Decimal("6.60"), **extra)


def test_money_has_two_decimals():
    with pytest.raises(ValidationError):
        DraftRequest(product="UHT milk 1 L", new_price=Decimal("7.255"))


def _proposal(**overrides):
    fields = {
        "id": "0" * 32,
        "region": "N",
        "sku": "DAI-002",
        "product": "UHT milk 1 L",
        "tier": "B",
        "current_price": Decimal("7.00"),
        "new_price": Decimal("7.25"),
        "change_pct": Decimal("3.57"),
        "approver": "manager",
        "clause": "PP-04 §3.2",
        "status": "pending",
        "proposed_by": "oid-1",
        "proposed_at": datetime(2026, 11, 21, 9, 0, tzinfo=UTC),
    }
    return Proposal(**(fields | overrides))


def test_a_proposal_round_trips_as_json():
    proposal = _proposal()
    assert '"current_price":"7.00"' in proposal.model_dump_json()
    assert Proposal.model_validate_json(proposal.model_dump_json()) == proposal


def test_proposal_errors_cap_their_matches():
    ProposalError(error="several products match", matches=["a"] * 10)
    with pytest.raises(ValidationError):
        ProposalError(error="several products match", matches=["a"] * 11)
