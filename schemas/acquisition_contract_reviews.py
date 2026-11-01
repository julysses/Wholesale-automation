"""Exact human review requests and bounded, non-executing responses."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

ReviewKind = Literal['contract_review', 'title_review', 'assignment_basis']


class Exact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ContractReviewRequest(Exact):
    id: UUID
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    status: Literal['approved', 'withdrawn']
    artifact_id: UUID
    verification_id: UUID
    policy_id: UUID
    expires_at: AwareDatetime | None
    personally_reviewed: StrictBool
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('expires_at', mode='before')
    @classmethod
    def timestamp_string(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def human_decision(self):
        if len(self.note.strip()) < 20:
            raise ValueError('Document the human review decision')
        if self.status == 'approved':
            if not self.personally_reviewed or self.expires_at is None:
                raise ValueError('Personal review and expiry required')
        elif self.personally_reviewed or self.expires_at is not None:
            raise ValueError('Withdrawal must not renew approval')
        return self


class ContractReviewScope(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    kind: ReviewKind
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def no_execution(self):
        if self.execution_authorized:
            raise ValueError('Review cannot authorize execution')
        return self


class ContractReviewReceipt(ContractReviewScope):
    review_id: UUID
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['approved', 'withdrawn']
    duplicate: StrictBool
    review_recorded: StrictBool
    approval_current: StrictBool

    @model_validator(mode='after')
    def historical_only(self):
        if not self.review_recorded or self.approval_current:
            raise ValueError('Historical persistence receipt required')
        return self


class ContractReviewState(ContractReviewScope):
    review_id: UUID | None
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    status: Literal['not_reviewed', 'approved', 'withdrawn', 'requires_review']
    approval_current: StrictBool
    expires_at: AwareDatetime | None
    checked_at: AwareDatetime

    @field_validator('expires_at', 'checked_at', mode='before')
    @classmethod
    def timestamp_string(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def consistent_state(self):
        if self.status == 'not_reviewed':
            if self.review_id is not None or self.sequence != 0:
                raise ValueError('Unreviewed state cannot carry a decision')
        elif self.review_id is None or self.sequence == 0:
            raise ValueError('Review identity required')
        if self.approval_current != (self.status == 'approved'):
            raise ValueError('Inconsistent review authority')
        if self.approval_current:
            if self.expires_at is None or self.expires_at <= self.checked_at:
                raise ValueError('Current review expiry required')
        elif self.expires_at is not None:
            raise ValueError('Historical review must not expose current expiry')
        return self
