from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class DataSource(str, Enum):
    TAX_DELINQUENT = "tax_delinquent"
    PROBATE = "probate"
    CODE_VIOLATION = "code_violation"
    EVICTION = "eviction"
    VACANCY = "vacancy"
    PROPSTREAM = "propstream"
    BATCHLEADS = "batchleads"
    REONOMY = "reonomy"
    LISTSOURCE = "listsource"
    MANUAL = "manual"


class DistressSignal(str, Enum):
    TAX_DELINQUENT = "tax_delinquent"
    PROBATE_INHERITED = "probate_inherited"
    VACANCY = "vacancy"
    CODE_VIOLATION = "code_violation"
    ABSENTEE_OWNER = "absentee_owner"
    HIGH_EQUITY = "high_equity"


SIGNAL_WEIGHTS: dict[DistressSignal, int] = {
    DistressSignal.TAX_DELINQUENT: 25,
    DistressSignal.PROBATE_INHERITED: 20,
    DistressSignal.VACANCY: 15,
    DistressSignal.CODE_VIOLATION: 10,
    DistressSignal.ABSENTEE_OWNER: 10,
    DistressSignal.HIGH_EQUITY: 20,
}


class NormalizedAddress(BaseModel):
    street: str
    city: str
    state: str = "TX"
    zip_code: str
    county: str = ""
    full: str = ""

    @field_validator("state")
    @classmethod
    def must_be_texas(cls, v: str) -> str:
        if v.upper() != "TX":
            raise ValueError("Only Texas properties are supported")
        return v.upper()

    def model_post_init(self, __context) -> None:
        if not self.full:
            self.full = f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class PropertyLead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    address: NormalizedAddress
    parcel_id: str = ""
    owner_name: str
    owner_mailing_address: Optional[NormalizedAddress] = None
    phone_numbers: list[str] = Field(default_factory=list)
    email: Optional[str] = None
    source: DataSource
    source_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    signals_raw: list[DistressSignal] = Field(default_factory=list)
    distress_score: Optional[int] = None
    estimated_equity_pct: Optional[float] = None
    assessed_value: Optional[float] = None
    market_value_estimate: Optional[float] = None
    tax_delinquent_amount: Optional[float] = None
    is_vacant: bool = False
    is_absentee: bool = False
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    flagged: bool = False
    flag_reason: str = ""
