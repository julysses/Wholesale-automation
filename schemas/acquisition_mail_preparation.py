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


class ContentReviewRequest(ExactModel):
    id: UUID
    expected_version: int = Field(strict=True, ge=0, lt=1000000000)
    action: Literal['approved', 'withdrawn']
    creative_id: UUID | None = None
    destination_review_id: UUID | None = None
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    preparation_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    evidence_ref: UUID | None = None
    evidence_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    expires_at: AwareDatetime | None = None
    note: str = Field(min_length=20, max_length=2000)

    @model_validator(mode='after')
    def require_review(self):
        evidence = (self.creative_id, self.destination_review_id, self.company_name, self.preparation_hash,
                    self.evidence_ref, self.evidence_hash, self.expires_at)
        if len(self.note.strip()) < 20:
            raise ValueError('Documented content review required')
        if self.action == 'approved' and any(value is None for value in evidence):
            raise ValueError('Exact preparation and evidence required')
        if self.action == 'withdrawn' and any(value is not None for value in evidence):
            raise ValueError('Withdrawal retains prior content evidence')
        return self


class ContentReviewRecord(ExactModel):
    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    content_id: UUID
    version: int = Field(strict=True, ge=1, le=1000000000)
    action: Literal['approved', 'withdrawn']
    creative_id: UUID
    destination_review_id: UUID
    company_name: str = Field(min_length=1, max_length=200)
    renderer_version: str
    preparation_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    evidence_ref: UUID
    evidence_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    expires_at: AwareDatetime
    review_note: str = Field(min_length=20, max_length=2000)
    actor_id: UUID
    actor_membership_updated_at: AwareDatetime
    request_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    created_at: AwareDatetime


class ContentReviewState(ExactModel):
    workspace_id: UUID
    campaign_id: UUID
    content_id: UUID
    version: int = Field(strict=True, ge=0, le=1000000000)
    latest_review: ContentReviewRecord | None
    review_current: StrictBool
    status: Literal['pending_review', 'approved', 'withdrawn', 'requires_review']
    preparation: ContentPreparation | None
    execution_authorized: StrictBool
    checked_at: AwareDatetime

    @model_validator(mode='after')
    def check_state(self):
        if self.execution_authorized or self.review_current != (self.status == 'approved'):
            raise ValueError('Content state cannot grant execution authority')
        latest = self.latest_review
        if self.version == 0:
            if latest is not None or self.status != 'pending_review' or self.preparation is not None:
                raise ValueError('Unexpected initial state')
            return self
        if (latest is None or latest.version != self.version
                or (latest.workspace_id, latest.campaign_id, latest.content_id) != (self.workspace_id, self.campaign_id, self.content_id)
                or self.status == 'pending_review' or (latest.action == 'withdrawn') != (self.status == 'withdrawn')):
            raise ValueError('Review identity or action mismatch')
        if not self.review_current:
            if self.preparation is not None:
                raise ValueError('Stale review cannot expose current preparation')
            return self
        prepared = self.preparation
        if (prepared is None or prepared.checked_at != self.checked_at or latest.expires_at <= self.checked_at
                or latest.created_at > self.checked_at or prepared.preparation_hash != latest.preparation_hash
                or latest.expires_at > prepared.destination_valid_until):
            raise ValueError('Current preparation evidence required')
        snapshot = prepared.snapshot
        if ((snapshot.workspace_id, snapshot.campaign_id, snapshot.company_name, snapshot.renderer_version) !=
                (self.workspace_id, self.campaign_id, latest.company_name, latest.renderer_version)
                or snapshot.template.creative_id != latest.creative_id
                or snapshot.destination.review_id != latest.destination_review_id):
            raise ValueError('Prepared source identities changed')
        return self
