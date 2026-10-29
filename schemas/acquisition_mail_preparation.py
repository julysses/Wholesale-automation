"""Read-only database preparation contract; never an approval or fulfillment receipt."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from schemas.acquisition_mail_render import MailTemplateSnapshot, MailDestinationSnapshot
from tools.acquisition_mail_render import VERSION, content_binding


def epoch(value: datetime) -> Decimal:
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def from_epoch(value: Decimal) -> datetime:
    micros = value * 1000000
    if micros != micros.to_integral_value():
        raise ValueError('Unsupported sub-microsecond evidence time')
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(micros))


class ExactModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ContentPreparationRequest(ExactModel):
    creative_id: UUID
    destination_review_id: UUID
    company_name: str = Field(min_length=1, max_length=200)


class PreparedTemplate(ExactModel):
    creative_id: UUID
    template_id: UUID
    version: int = Field(strict=True, ge=1)
    format: Literal['letter', 'postcard']
    tracking_mode: Literal['phone', 'landing_page']
    body: str = Field(min_length=1, max_length=20000)


class PreparedDestination(ExactModel):
    review_id: UUID
    destination_id: UUID
    version: int = Field(strict=True, ge=1, le=1000000000)
    mode: Literal['phone', 'landing_page']
    value: str = Field(min_length=1, max_length=2048)
    verification_ref: UUID
    verification_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    verified_epoch: Decimal
    expires_epoch: Decimal
    reviewer_id: UUID
    reviewer_membership_epoch: Decimal


class PreparedSnapshot(ExactModel):
    workspace_id: UUID
    campaign_id: UUID
    renderer_version: str
    company_name: str = Field(min_length=1, max_length=200)
    template: PreparedTemplate
    destination: PreparedDestination


class ContentPreparation(ExactModel):
    status: Literal['content_prepared']
    execution_authorized: StrictBool
    content_approved: StrictBool
    snapshot: PreparedSnapshot
    preparation_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    checked_at: AwareDatetime
    destination_valid_until: AwareDatetime

    @model_validator(mode='after')
    def check_current_content(self):
        snapshot = self.snapshot
        destination = snapshot.destination
        if self.execution_authorized or self.content_approved or snapshot.renderer_version != VERSION:
            raise ValueError('Preparation cannot grant authority or change renderer')
        checked = epoch(self.checked_at)
        if not destination.verified_epoch <= checked < destination.expires_epoch:
            raise ValueError('Destination evidence is not current at preparation')
        if epoch(self.destination_valid_until) != destination.expires_epoch:
            raise ValueError('Destination expiry does not match evidence')
        scope = dict(workspace_id=snapshot.workspace_id, campaign_id=snapshot.campaign_id)
        try:
            verified = from_epoch(destination.verified_epoch)
            expires = from_epoch(destination.expires_epoch)
            # Validate with the same text/destination rules used by proof rendering.
            content_binding(MailTemplateSnapshot(**scope, **snapshot.template.model_dump(exclude={'creative_id'})),
                MailDestinationSnapshot(**scope, id=destination.destination_id, version=destination.version,
                    mode=destination.mode, value=destination.value, verification_ref=destination.verification_ref,
                    verified_at=verified, expires_at=expires, revoked=False), snapshot.company_name)
        except (OverflowError, OSError) as error:
            raise ValueError('Unsupported destination evidence date') from error
        return self
