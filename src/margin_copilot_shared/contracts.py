"""Contracts between services. Agent output is untrusted: receivers validate it here (D-029)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints, model_validator

MAX_ANSWER_CHARS = 4_000
Refusal = Literal["out_of_scope", "no_access", "no_data"]
Citation = Annotated[str, StringConstraints(pattern=r"^PP-\d{2}(-[NCS])? §\d+(\.\d+)?$")]


class AgentReply(BaseModel):
    """An agent's reply over A2A. `refusal` is set only when nothing could be answered."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: StrictStr = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    refusal: Refusal | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=12)


Region = Literal["N", "C", "S"]
Money = Annotated[Decimal, Field(gt=0, max_digits=9, decimal_places=2)]


class DraftRequest(BaseModel):
    """The action agent's draft for proposals-api. Tier and current price are deliberately absent:
    proposals-api reads them itself, as the user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product: StrictStr = Field(min_length=2, max_length=80)
    region: Region | None = None
    new_price: Money | None = None
    change_pct: Annotated[Decimal, Field(ge=-50, le=100, decimal_places=2)] | None = None

    @model_validator(mode="after")
    def _one_of_price_or_percent(self) -> Self:
        if (self.new_price is None) == (self.change_pct is None):
            raise ValueError("give exactly one of new_price and change_pct")
        return self


class Proposal(BaseModel):
    """A price-change proposal as proposals-api stores it. `approver` is decided at draft time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
    region: Region
    sku: StrictStr = Field(min_length=1, max_length=20)
    product: StrictStr = Field(min_length=1, max_length=80)
    tier: Literal["A", "B", "C"]
    current_price: Money
    new_price: Money
    change_pct: Annotated[Decimal, Field(decimal_places=2)]  # for display; rules use exact values
    approver: Literal["manager", "director"]
    clause: Citation
    status: Literal["pending", "approved", "rejected"]
    proposed_by: StrictStr = Field(min_length=1, max_length=64)
    proposed_at: datetime
    decided_by: StrictStr | None = Field(default=None, max_length=64)
    decided_at: datetime | None = None


class ProposalError(BaseModel):
    """proposals-api's error body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: StrictStr = Field(min_length=1, max_length=300)
    clause: Citation | None = None
    matches: list[Annotated[StrictStr, Field(max_length=80)]] = Field(
        default_factory=list, max_length=10
    )
