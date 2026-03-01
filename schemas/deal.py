from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DealStrategy(str, Enum):
    WHOLESALE = "wholesale"
    WHOLETAIL = "wholetail"
    CLOSE_AND_REHAB = "close_and_rehab"
    TOO_RISKY = "too_risky"


class DealStatus(str, Enum):
    UNDERWRITING = "underwriting"
    PENDING_OUTREACH = "pending_outreach"
    IN_NEGOTIATION = "in_negotiation"
    UNDER_CONTRACT = "under_contract"
    ASSIGNED = "assigned"
    CLOSED = "closed"
    DEAD = "dead"


class ARVRange(BaseModel):
    low: float
    mid: float
    high: float

    @property
    def conservative(self) -> float:
        """Return conservative ARV for MAO calculation."""
        return self.low


class RehabRange(BaseModel):
    low: float
    mid: float
    high: float

    @property
    def conservative(self) -> float:
        """Return conservative (high) rehab cost for MAO calculation."""
        return self.high


class UnderwritingReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    address_full: str
    arv: ARVRange
    rehab: RehabRange
    mao: float  # (ARV_low × 0.70) − Rehab_high
    strategy: DealStrategy
    comp_count: int = 0
    comp_summary: str = ""
    rationale: str = ""
    weak_deal_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    analyst_notes: str = ""

    @classmethod
    def calculate_mao(cls, arv_low: float, rehab_high: float) -> float:
        return round((arv_low * 0.70) - rehab_high, 2)


class Deal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    underwriting_id: Optional[UUID] = None
    contract_price: Optional[float] = None
    assignment_fee: Optional[float] = None
    status: DealStatus = DealStatus.UNDERWRITING
    assigned_buyer_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    notes: str = ""
