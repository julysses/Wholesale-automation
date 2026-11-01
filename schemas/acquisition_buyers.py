"""Workspace-owned buyer details; saving a profile grants no contact or deal authority."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact

Cents = Annotated[int, Field(strict=True, ge=0, le=999999999999)]
PropertyType = Literal['SFR', 'duplex', 'MFR', 'land', 'condo']
Strategy = Literal['fix_flip', 'buy_hold', 'brrrr', 'str', 'development', 'wholesale']


class AcquisitionBuyerDetails(Exact):
    first_name: str = Field(strict=True, min_length=1, max_length=120)
    last_name: str = Field(strict=True, min_length=1, max_length=120)
    company: str | None = Field(default=None, strict=True, min_length=1, max_length=160)
    email: str | None = Field(default=None, strict=True, min_length=3, max_length=320)
    phone: str | None = Field(default=None, strict=True, pattern=r'^\+[1-9][0-9]{7,14}$')
    target_zips: list[Annotated[str, Field(strict=True, pattern=r'^[0-9]{5}$')]] = Field(max_length=100)
    property_types: list[PropertyType] = Field(max_length=5)
    strategies: list[Strategy] = Field(max_length=6)
    min_price_cents: Cents | None = None
    max_price_cents: Cents | None = None
    max_repairs_cents: Cents | None = None
    close_speed_days: int | None = Field(default=None, strict=True, ge=1, le=365)
    active: StrictBool
    source_note: str = Field(strict=True, min_length=20, max_length=2000)

    @field_validator('first_name', 'last_name', 'company', 'email', 'source_note')
    @classmethod
    def clean_text(cls, value):
        if value is not None and (value != value.strip() or any(ord(c)<32 for c in value)):
            raise ValueError('Use trimmed text without control characters')
        return value

    @field_validator('email')
    @classmethod
    def normalized_email(cls, value):
        if value is not None:
            import re
            if value!=value.lower() or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):
                raise ValueError('A normalized email address is required')
        return value

    @field_validator('target_zips', 'property_types', 'strategies')
    @classmethod
    def unique_values(cls, value):
        if len(value)!=len(set(value)):
            raise ValueError('Repeated preferences are not allowed')
        return value

    @model_validator(mode='after')
    def price_range(self):
        if self.min_price_cents is not None and self.max_price_cents is not None and self.min_price_cents>self.max_price_cents:
            raise ValueError('Minimum price cannot exceed maximum price')
        return self


class AcquisitionBuyerRequest(Exact):
    id: UUID
    buyer_id: UUID
    expected_revision: int = Field(strict=True, ge=0, le=2147483646)
    details: AcquisitionBuyerDetails


class AcquisitionBuyerReceipt(Exact):
    request_id: UUID
    workspace_id: UUID
    buyer_id: UUID
    revision: int = Field(strict=True, ge=1, le=2147483647)
    details: AcquisitionBuyerDetails
    duplicate: StrictBool
    profile_recorded: Literal[True]
    buyer_verified: Literal[False]
    contact_authorized: Literal[False]
    execution_authorized: Literal[False]

    def confirms(self, request: AcquisitionBuyerRequest, workspace_id: UUID) -> bool:
        return (self.request_id==request.id and self.workspace_id==workspace_id and self.buyer_id==request.buyer_id
                and self.revision==request.expected_revision+1 and self.details==request.details)


class BuyerSummary(Exact):
    buyer_id: UUID
    revision: int = Field(strict=True, ge=1, le=2147483647)
    first_name: str = Field(strict=True, min_length=1, max_length=120)
    last_name: str = Field(strict=True, min_length=1, max_length=120)
    company: str | None = Field(strict=True, min_length=1, max_length=160)
    active: StrictBool
    buyer_verified: Literal[False]


class BuyerProjection(Exact):
    workspace_id: UUID
    checked_at: AwareDatetime
    can_save: StrictBool
    contact_authorized: Literal[False]
    execution_authorized: Literal[False]

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_time(cls, value):
        if not isinstance(value,str) or 'T' not in value:
            raise ValueError('An explicit server timestamp is required')
        return value


class AcquisitionBuyerProfile(BuyerProjection):
    buyer_id: UUID
    revision: int = Field(strict=True, ge=1, le=2147483647)
    details: AcquisitionBuyerDetails
    buyer_verified: Literal[False]


class AcquisitionBuyerIndex(BuyerProjection):
    items: list[BuyerSummary] = Field(max_length=50)
    next_cursor: UUID | None

    @model_validator(mode='after')
    def ordered_page(self):
        ids=[item.buyer_id.int for item in self.items]
        if ids!=sorted(set(ids)):
            raise ValueError('Buyer page must contain unique ordered identities')
        if self.next_cursor is not None and (not self.items or self.next_cursor!=self.items[-1].buyer_id):
            raise ValueError('Buyer cursor must match the last returned identity')
        return self
