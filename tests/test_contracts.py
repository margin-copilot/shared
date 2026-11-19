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
