import pytest
from pydantic import ValidationError

from margin_copilot_shared.contracts import MAX_ANSWER_CHARS, AgentReply


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
