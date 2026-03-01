from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BuyerStrategy(str, Enum):
    FIX_AND_FLIP = "fix_and_flip"
    BUY_AND_HOLD = "buy_and_hold"
    BTR = "build_to_rent"
    WHOLETAIL = "wholetail"
    INSTITUTIONAL = "institutional"
    DEVELOPER = "developer"


class BuyerSource(str, Enum):
    FACEBOOK_GROUP = "facebook_group"
    BIGGER_POCKETS = "bigger_pockets"
    REIA = "reia"
    DISCORD = "discord"
    DIRECT_REFERRAL = "direct_referral"
    INSTITUTIONAL_OUTREACH = "institutional_outreach"
    MANUAL = "manual"


class BuyerTier(str, Enum):
    TIER_1 = "tier_1"  # Top 3 — most reliable
    TIER_2 = "tier_2"  # Next 4
    TIER_3 = "tier_3"  # Remaining


class BuyerProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    company: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    source: BuyerSource
    source_platform_url: str = ""
    markets: list[str] = Field(default_factory=list)  # zip codes or cities
    strategies: list[BuyerStrategy] = Field(default_factory=list)
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    proof_of_funds: bool = False
    close_speed_days: Optional[int] = None
    inferred_buy_box: str = ""
    notes: str = ""
    permission_granted: bool = False  # have they opted in to deal flow?
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BuyerQualification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    buyer_id: UUID
    reliability_score: float = Field(ge=0.0, le=100.0, default=50.0)
    total_closes_with_agency: int = 0
    ghost_count: int = 0  # times went silent after receiving deal
    lowball_count: int = 0  # times offered far below asking
    avg_close_days: Optional[float] = None
    last_active: Optional[datetime] = None
    disqualified: bool = False
    disqualification_reason: str = ""
    qualified_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str = ""

    def degrade_for_ghost(self) -> None:
        self.ghost_count += 1
        self.reliability_score = max(0.0, self.reliability_score - 15.0)
        self.updated_at = datetime.utcnow()

    def degrade_for_lowball(self) -> None:
        self.lowball_count += 1
        self.reliability_score = max(0.0, self.reliability_score - 8.0)
        self.updated_at = datetime.utcnow()

    def upgrade_for_close(self, days_to_close: int) -> None:
        self.total_closes_with_agency += 1
        self.reliability_score = min(100.0, self.reliability_score + 10.0)
        if self.avg_close_days is None:
            self.avg_close_days = float(days_to_close)
        else:
            closes = self.total_closes_with_agency
            self.avg_close_days = ((self.avg_close_days * (closes - 1)) + days_to_close) / closes
        self.last_active = datetime.utcnow()
        self.updated_at = datetime.utcnow()
