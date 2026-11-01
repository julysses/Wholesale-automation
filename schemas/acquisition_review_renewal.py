"""Input/receipt contract for a future controlled review-renewal writer.

No route or persistence is enabled here. IDs and the discovery fingerprint are
concurrency selectors, never evidence of authority. The writer must derive the
original chain, compare the fresh snapshot, lock dependencies and recheck them.
"""
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

ReviewKind = Literal['deadline_resolution', 'executed_contract', 'title_findings', 'disposition_findings']
DeadlineTerm = Literal['effective', 'inspection_deadline', 'closing_deadline']


class ReviewRenewalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=1, le=2147483646)
    kind: ReviewKind
    deadline_term: DeadlineTerm | None
    root_review_id: UUID
    previous_review_id: UUID
    policy_id: UUID
    # Binds the displayed original facts, scans, policies and dependency reviews.
    # Recompute from authorized server data; never trust this value alone.
    expected_snapshot_sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    expires_at: AwareDatetime
    personally_reviewed: StrictBool
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_expiry(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit expiry timestamp required')
        return value

    @field_validator('note')
    @classmethod
    def substantive_note(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Document the personal renewal review')
        return value  # Retain exact bytes for retries.

    @model_validator(mode='after')
    def original_review_context(self):
        if not self.personally_reviewed:
            raise ValueError('A new personal review is required')
        if self.id in {self.root_review_id, self.previous_review_id}:
            raise ValueError('Renewal must append a distinct review')
        if (self.kind == 'deadline_resolution') != (self.deadline_term is not None):
            raise ValueError('Only deadline renewal identifies a date term')
        return self


class ReviewRenewalReceipt(BaseModel):
    """Confirms only the immutable saved renewal, not current transaction authority."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    kind: ReviewKind
    deadline_term: DeadlineTerm | None
    review_id: UUID
    root_review_id: UUID
    previous_review_id: UUID
    sequence: int = Field(strict=True, ge=2, le=2147483647)
    duplicate: StrictBool
    review_recorded: StrictBool
    approval_current: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def historical_only(self):
        if not self.review_recorded or self.approval_current or self.execution_authorized:
            raise ValueError('Historical non-authorizing confirmation required')
        if self.review_id in {self.root_review_id, self.previous_review_id}:
            raise ValueError('Distinct appended review required')
        if (self.kind == 'deadline_resolution') != (self.deadline_term is not None):
            raise ValueError('Exact review-kind context required')
        return self

    def confirms(self, request: ReviewRenewalRequest, *, workspace_id: UUID, contract_id: UUID) -> bool:
        return (self.workspace_id == workspace_id and self.contract_id == contract_id
                and self.contract_version == request.expected_version and self.kind == request.kind
                and self.deadline_term == request.deadline_term and self.review_id == request.id
                and self.root_review_id == request.root_review_id and self.previous_review_id == request.previous_review_id
                and self.sequence == request.expected_sequence + 1)
