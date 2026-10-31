"""Trusted contract-review snapshots; never accept these as client authorization."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

ContractStatus = Literal['draft', 'pending_signature', 'executed', 'title_review',
                         'disposition_review', 'assigned_or_direct_close', 'closed',
                         'cancelled', 'expired', 'disputed']
EvidenceKind = Literal['signature_release', 'executed_contract', 'contract_review',
                       'title_review', 'assignment_basis', 'seller_disclosure',
                       'assignee_disclosure', 'buyer_verification', 'structure_approval',
                       'assignment_agreement', 'deposit_confirmation', 'closing_confirmation',
                       'cancellation_review', 'expiration_review', 'dispute_report',
                       'dispute_resolution']


class ContractEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1)
    kind: EvidenceKind
    reviewed_by: UUID
    recorded_at: AwareDatetime
    expires_at: AwareDatetime
    revoked: bool = Field(default=False, strict=True)
    # Assignment reviews are tied to the exact proposed buyer and closing structure.
    buyer_id: UUID | None = None
    exit_type: Literal['principal_acquisition', 'wholesale_assignment'] | None = None

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.expires_at <= self.recorded_at:
            raise ValueError('Evidence expiration must follow recording')
        return self


class ContractReviewSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1)
    status: ContractStatus
    target_status: ContractStatus
    now: AwareDatetime
    snapshot_at: AwareDatetime
    exit_type: Literal['principal_acquisition', 'wholesale_assignment'] | None = None
    buyer_id: UUID | None = None
    assignment_allowed: bool | None = Field(default=None, strict=True)
    effective_at: AwareDatetime | None = None
    inspection_deadline: AwareDatetime | None = None
    closing_deadline: AwareDatetime | None = None
    # Legacy DATE values preserve their source precision; no inferred midnight or timezone.
    effective_date: date | None = None
    inspection_deadline_date: date | None = None
    closing_deadline_date: date | None = None
    earnest_money_cents: int | None = Field(default=None, strict=True, ge=0)
    evidence: tuple[ContractEvidence, ...] = ()

    @field_validator('effective_date', 'inspection_deadline_date', 'closing_deadline_date', mode='before')
    @classmethod
    def exact_calendar_date(cls, value):
        if value is None or type(value) is date:
            return value
        if isinstance(value, str) and len(value) == 10:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        raise ValueError('Use an explicit calendar date without an inferred time')

    @model_validator(mode='after')
    def one_precision_per_term(self):
        for instant, calendar in (('effective_at', 'effective_date'),
                                  ('inspection_deadline', 'inspection_deadline_date'),
                                  ('closing_deadline', 'closing_deadline_date')):
            if getattr(self, instant) is not None and getattr(self, calendar) is not None:
                raise ValueError('Contract term cannot claim both date-only and instant precision')
        return self
