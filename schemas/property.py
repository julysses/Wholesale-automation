from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class DataSource(str, Enum):
    TAX_DELINQUENT  = "tax_delinquent"
    PROBATE         = "probate"
    CODE_VIOLATION  = "code_violation"
    UTILITY_SHUTOFF = "utility_shutoff"
    MUNICIPAL_LIEN  = "municipal_lien"
    EVICTION        = "eviction"
    VACANCY         = "vacancy"
    PROPSTREAM      = "propstream"
    BATCHLEADS      = "batchleads"
    REONOMY         = "reonomy"
    LISTSOURCE      = "listsource"
    MANUAL          = "manual"


class DistressSignal(str, Enum):
    # Original signals
    TAX_DELINQUENT   = "tax_delinquent"
    PROBATE_INHERITED= "probate_inherited"
    VACANCY          = "vacancy"
    CODE_VIOLATION   = "code_violation"
    ABSENTEE_OWNER   = "absentee_owner"
    HIGH_EQUITY      = "high_equity"
    PRE_FORECLOSURE  = "pre_foreclosure"
    # New government-data signals
    UTILITY_SHUTOFF  = "utility_shutoff"
    MUNICIPAL_LIEN   = "municipal_lien"
    # Stacking indicators
    OUT_OF_STATE_OWNER = "out_of_state_owner"
    LONG_TERM_OWNER    = "long_term_owner"   # ownership >= 10 years


# ── Blueprint scoring weights (signal only — stacking bonuses added separately) ─
# Weights must sum to 100; the scoring engine caps the final score at 100.
SIGNAL_WEIGHTS: dict[DistressSignal, int] = {
    DistressSignal.TAX_DELINQUENT:     25,
    DistressSignal.PROBATE_INHERITED:  20,
    DistressSignal.HIGH_EQUITY:        20,
    DistressSignal.VACANCY:            15,
    DistressSignal.PRE_FORECLOSURE:     5,
    DistressSignal.ABSENTEE_OWNER:      5,
    DistressSignal.CODE_VIOLATION:      4,
    DistressSignal.UTILITY_SHUTOFF:     2,
    DistressSignal.MUNICIPAL_LIEN:      2,
    DistressSignal.LONG_TERM_OWNER:     1,
    DistressSignal.OUT_OF_STATE_OWNER:  1,
}

# ── Stack definitions with bonus points ─────────────────────────────────────────
# Evaluated in descending bonus order; first match wins the label.
STACK_RULES: list[tuple[str, frozenset[DistressSignal], int]] = [
    # Full distress stack (highest bonus)
    (
        "Ultimate Distress",
        frozenset({
            DistressSignal.ABSENTEE_OWNER,
            DistressSignal.VACANCY,
            DistressSignal.TAX_DELINQUENT,
            DistressSignal.CODE_VIOLATION,
        }),
        70,
    ),
    ("Absentee + Vacant + Tax", frozenset({DistressSignal.ABSENTEE_OWNER, DistressSignal.VACANCY, DistressSignal.TAX_DELINQUENT}), 50),
    ("Utility Shutoff + Vacant", frozenset({DistressSignal.UTILITY_SHUTOFF, DistressSignal.VACANCY}), 45),
    ("Probate + Vacant",         frozenset({DistressSignal.PROBATE_INHERITED, DistressSignal.VACANCY}), 40),
    ("Code Violation + Vacant",  frozenset({DistressSignal.CODE_VIOLATION, DistressSignal.VACANCY}), 40),
    ("Vacant + Tax Delinquent",  frozenset({DistressSignal.VACANCY, DistressSignal.TAX_DELINQUENT}), 35),
    ("Absentee + Tax Delinquent",frozenset({DistressSignal.ABSENTEE_OWNER, DistressSignal.TAX_DELINQUENT}), 30),
    ("Absentee + Vacant",        frozenset({DistressSignal.ABSENTEE_OWNER, DistressSignal.VACANCY}), 30),
]


def compute_stack_bonus(signals: set[DistressSignal]) -> tuple[str, int]:
    """
    Given the set of confirmed signals on a lead, return (stack_name, bonus_points).
    Returns ("Single Signal", 0) if no stacking rules match.
    """
    for name, required, bonus in STACK_RULES:
        if required.issubset(signals):
            return name, bonus
    return "Single Signal", 0


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

    # Financial
    estimated_equity_pct: Optional[float] = None
    assessed_value: Optional[float] = None
    market_value_estimate: Optional[float] = None
    tax_delinquent_amount: Optional[float] = None
    lien_amount: Optional[float] = None

    # Property characteristics
    is_vacant: bool = False
    is_absentee: bool = False
    year_built: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    property_type: str = "single_family"

    # New government data signals
    code_violation_status: bool = False
    utility_shutoff_status: bool = False
    municipal_lien_status: bool = False
    pre_foreclosure_status: bool = False
    probate_status: bool = False

    # Ownership
    years_owned: Optional[int] = None

    # Scoring outputs (populated by SellerScoreAgent)
    seller_score: Optional[int] = None
    stack_name: Optional[str] = None
    stack_bonus: int = 0

    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    flagged: bool = False
    flag_reason: str = ""
