"""Exact public offer-request contract; no routing, valuation or execution authority."""
from decimal import Decimal
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)]
Version = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$')]


class Exact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


def normalize_offer_phone(value: str) -> str:
    # Match the acquisition contact crosswalk's supported formats. This checks
    # shape only; it does not establish ownership, deliverability or permission.
    if not re.fullmatch(r'\+?[0-9 ().-]+', value):
        raise ValueError('Unsupported telephone format')
    digits = re.sub(r'[^0-9]', '', value)
    if value.startswith('+'):
        normalized = '+' + digits
    elif len(digits) == 10:
        normalized = '+1' + digits
    elif len(digits) == 11 and digits.startswith('1'):
        normalized = '+' + digits
    else:
        raise ValueError('Use an explicit country code')
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', normalized):
        raise ValueError('Unsupported telephone format')
    return normalized


class OfferSeller(Exact):
    name: Text
    phone: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=7, max_length=40)] | None = None
    email: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=3, max_length=254,
                                          pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')] | None = None

    @field_validator('phone')
    @classmethod
    def phone_shape(cls, value):
        if value is not None:
            normalize_offer_phone(value)
        return value

    @model_validator(mode='after')
    def contact_required(self):
        if not self.phone and not self.email:
            raise ValueError('Provide a reply contact')
        return self


class OfferProperty(Exact):
    address: Text
    city: Text
    state: Annotated[str, StringConstraints(strict=True, pattern=r'^[A-Z]{2}$')]
    postal_code: Annotated[str, StringConstraints(strict=True, pattern=r'^\d{5}(?:-\d{4})?$')]
    authority: Literal['owner', 'authorized_representative', 'not_authorized', 'unsure']
    condition: Literal['move_in_ready', 'cosmetic_repairs', 'major_repairs', 'unsure']
    occupancy: Literal['owner_occupied', 'tenant_occupied', 'vacant', 'other', 'unsure']
    timeline: Literal['within_30_days', 'one_to_three_months', 'three_to_six_months', 'flexible', 'unsure']
    motivation: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)]
    # Decimal text or null only. Missing price stays missing, never becomes zero.
    asking_price: Annotated[str, StringConstraints(strict=True, pattern=r'^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$')] | None = None

    @model_validator(mode='after')
    def price_bound(self):
        if self.asking_price is not None and Decimal(self.asking_price) > Decimal('1000000000'):
            raise ValueError('Asking price outside supported range')
        return self


class OnlineOfferRequest(Exact):
    submission_id: UUID
    form_version: Version
    seller: OfferSeller
    property: OfferProperty
    # Missing optional selection differs from an explicit false selection.
    selections: dict[Literal['privacy_acknowledged', 'human_callback_requested', 'email_reply_requested'], StrictBool]

    @model_validator(mode='after')
    def affirmative_acknowledgement(self):
        if self.selections.get('privacy_acknowledged') is not True:
            raise ValueError('Privacy acknowledgement required')
        if self.selections.get('human_callback_requested') is True and not self.seller.phone:
            raise ValueError('Callback request requires a telephone number')
        if self.selections.get('email_reply_requested') is True and not self.seller.email:
            raise ValueError('Email reply request requires an email address')
        return self


class OfferFormDefinition(Exact):
    """Server-loaded reviewed definition, never accepted from the public request."""
    form_key: Version
    version: Version
    privacy_acknowledged: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4000)]
    human_callback_requested: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4000)]
    email_reply_requested: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4000)]
