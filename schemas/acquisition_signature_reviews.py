"""Signature-release review transport, never a signing request or execution permit."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact


class SignatureReviewRequest(Exact):
    id: UUID
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    status: Literal['approved', 'withdrawn']
    basis_review_id: UUID
    policy_id: UUID
    expires_at: AwareDatetime | None
    personally_reviewed: StrictBool
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit timestamp required')
        return value

    @model_validator(mode='after')
    def exact_decision(self):
        if len(self.note.strip()) < 20 or '\x00' in self.note:
            raise ValueError('Document the personal review decision')
        if self.status == 'approved':
            if not self.personally_reviewed or self.expires_at is None:
                raise ValueError('Personal review and bounded expiry required')
        elif self.personally_reviewed or self.expires_at is not None:
            raise ValueError('Withdrawal cannot renew approval')
        return self


class SignatureReviewScope(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def no_execution(self):
        if self.execution_authorized:
            raise ValueError('Review does not authorize execution')
        return self


class SignatureReviewReceipt(SignatureReviewScope):
    review_id: UUID
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['approved', 'withdrawn']
    duplicate: StrictBool
    review_recorded: StrictBool
    approval_current: StrictBool

    @model_validator(mode='after')
    def historical_only(self):
        if not self.review_recorded or self.approval_current:
            raise ValueError('Historical confirmation required')
        return self


class SignatureReviewState(SignatureReviewScope):
    review_id: UUID | None
    basis_review_id: UUID | None
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    status: Literal['not_reviewed', 'approved', 'withdrawn', 'requires_review']
    approval_current: StrictBool
    expires_at: AwareDatetime | None
    checked_at: AwareDatetime

    @field_validator('expires_at', 'checked_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit timestamp required')
        return value

    @model_validator(mode='after')
    def coherent_state(self):
        if self.status == 'not_reviewed':
            if self.review_id is not None or self.basis_review_id is not None or self.sequence != 0:
                raise ValueError('Unreviewed state cannot claim a decision')
        elif self.review_id is None or self.basis_review_id is None or self.sequence == 0:
            raise ValueError('Exact decision and basis required')
        if self.approval_current != (self.status == 'approved'):
            raise ValueError('Inconsistent current approval')
        if self.approval_current:
            if self.expires_at is None or self.expires_at <= self.checked_at:
                raise ValueError('Current expiry required')
        elif self.expires_at is not None:
            raise ValueError('Historical decision cannot expose current expiry')
        return self
