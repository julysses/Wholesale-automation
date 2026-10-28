"""Trusted repository snapshots for mail proof preparation, never public authority inputs."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool

from schemas.acquisition_mail import TimedSnapshot


class MailTemplateSnapshot(TimedSnapshot):
    workspace_id: UUID
    campaign_id: UUID
    template_id: UUID
    version: int = Field(strict=True, ge=1)
    format: Literal['letter', 'postcard']
    tracking_mode: Literal['phone', 'landing_page']
    body: str = Field(min_length=1, max_length=20000)


class MailDestinationSnapshot(TimedSnapshot):
    workspace_id: UUID
    campaign_id: UUID
    id: UUID
    version: int = Field(strict=True, ge=1)
    mode: Literal['phone', 'landing_page']
    value: str = Field(min_length=1, max_length=2048)
    verification_ref: UUID
    verified_at: datetime
    expires_at: datetime
    revoked: StrictBool


class MailContentReview(TimedSnapshot):
    workspace_id: UUID
    campaign_id: UUID
    id: UUID
    approver_id: UUID
    evidence_ref: UUID
    # Digest includes exact content, template version, destination version/value,
    # verification evidence and renderer version. Review is not fulfillment approval.
    binding_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    status: Literal['approved', 'rejected', 'withdrawn']
    reviewed_at: datetime
    expires_at: datetime


class MailRenderInput(TimedSnapshot):
    workspace_id: UUID
    campaign_id: UUID
    property_id: UUID
    tracking_id: UUID
    company_name: str = Field(min_length=1, max_length=200)
    property_address: str = Field(min_length=1, max_length=1000)
    now: datetime
    template: MailTemplateSnapshot
    destination: MailDestinationSnapshot
    review: MailContentReview
