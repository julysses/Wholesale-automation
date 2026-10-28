"""Server-sourced snapshots for deterministic mail proposal preparation.

These models are not public request bodies or authorization evidence by themselves.
The eventual repository must load verified records under workspace authorization.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Snapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class TimedSnapshot(Snapshot):
    @field_validator('*')
    @classmethod
    def aware_dates(cls, value):
        if isinstance(value, datetime) and value.utcoffset() is None:
            raise ValueError('timezone required')
        return value


class MailCandidate(TimedSnapshot):
    workspace_id: UUID
    lead_id: UUID
    property_id: UUID
    owner_id: UUID
    score: int | None = Field(default=None, strict=True, ge=0, le=100)
    county: Literal['Dallas', 'Collin', 'other', 'unknown']
    state: str
    # Opaque canonical recipient/delivery-point identity, preserving unit distinctions.
    # Never computed by stripping punctuation from a caller's raw address.
    recipient_address_key: str | None = Field(default=None, min_length=1, max_length=256)
    address_status: Literal['verified', 'unverified', 'undeliverable']
    address_evidence_ref: UUID | None = None
    address_expires_at: datetime | None = None
    owner_status: Literal['living', 'deceased', 'unknown']
    preference: Literal['clear', 'suppressed', 'unknown']
    eligibility: Literal['ALLOW', 'BLOCK', 'REVIEW']
    eligibility_decision_id: UUID
    eligibility_expires_at: datetime | None = None


class MailHistory(TimedSnapshot):
    workspace_id: UUID
    campaign_id: UUID
    job_id: UUID
    property_id: UUID
    recipient_address_key: str
    status: Literal['proposed', 'approved', 'submitting', 'submitted', 'fulfilled',
                    'unknown', 'failed', 'cancelled']
    # Submission/fulfillment time for completed work; reservation time otherwise.
    effective_at: datetime
    cost_cents: int = Field(strict=True, ge=0)
    # Release requires authoritative non-fulfillment evidence, not merely a failed request.
    release_evidence_ref: UUID | None = None


class MailBatchInput(TimedSnapshot):
    workspace_id: UUID
    campaign_id: UUID
    batch_id: UUID
    template_id: UUID
    template_version: int = Field(strict=True, ge=1)
    format: Literal['letter', 'postcard']
    tracking_destination_ref: UUID
    vendor_id: str = Field(min_length=1, max_length=100)
    quote_ref: UUID
    currency: Literal['USD']
    quote_expires_at: datetime
    unit_cost_cents: int = Field(strict=True, gt=0)
    budget_cents: int = Field(strict=True, ge=0)
    minimum_score: int = Field(strict=True, ge=0, le=100)
    frequency_days: int = Field(strict=True, ge=1, le=3650)
    maximum_pieces: int = Field(strict=True, ge=1, le=10000)
    now: datetime
    history_as_of: datetime
    # Completeness covers this workspace's jobs across every campaign and date,
    # not just the most recent page. Required for campaign lifetime budget accounting.
    history_complete: StrictBool
    candidates: tuple[MailCandidate, ...]
    history: tuple[MailHistory, ...]
