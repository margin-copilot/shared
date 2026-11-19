"""Contracts between services. Agent output is untrusted: receivers validate it here (D-029)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

MAX_ANSWER_CHARS = 4_000
Refusal = Literal["out_of_scope", "no_access", "no_data"]


class AgentReply(BaseModel):
    """An agent's reply over A2A. `refusal` is set only when nothing could be answered."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: StrictStr = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    refusal: Refusal | None = None
