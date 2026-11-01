"""Explicit reviewer-supplied date interpretation; never a replacement contract term.

This isolated boundary is not an API or execution authorization. Persistence must
bind it to the current date-only term and independently verify the cited original.
"""
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, Field, field_validator, model_validator
from schemas.acquisition_contract_terms import Exact, ContractTermSource
from schemas.acquisition_contract_reviews import ContractReviewRequest, ContractReviewReceipt

DeadlineTerm = Literal['effective', 'inspection_deadline', 'closing_deadline']


class ContractDeadlineResolution(Exact):
    term: DeadlineTerm
    calendar_date: date
    local_time: str = Field(strict=True, pattern=r'^\d{2}:\d{2}:\d{2}$')
    time_zone: str = Field(strict=True, min_length=1, max_length=100)
    resolved_instant: AwareDatetime
    basis: Literal['explicit_document_time', 'reviewed_interpretation']
    source: ContractTermSource
    rationale: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('calendar_date', mode='before')
    @classmethod
    def explicit_calendar_date(cls, value):
        if type(value) is date:
            return value
        if isinstance(value, str) and len(value) == 10 and date.fromisoformat(value).isoformat() == value:
            return value
        raise ValueError('Preserve the original calendar date')

    @field_validator('resolved_instant', mode='before')
    @classmethod
    def explicit_offset(cls, value):
        if isinstance(value, datetime) or isinstance(value, str) and 'T' in value:
            return value
        raise ValueError('Explicit resolved instant and UTC offset required')

    @model_validator(mode='after')
    def coherent_source_and_local_time(self):
        if self.source.term != self.term:
            raise ValueError('The cited source must address this exact term')
        if len(self.rationale.strip()) < 20 or '\x00' in self.rationale:
            raise ValueError('Document the interpretation without inferring authority')
        try:
            zone = ZoneInfo(self.time_zone)
            wall_time = time.fromisoformat(self.local_time)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError('Use a named time zone and valid local time') from error
        local = self.resolved_instant.astimezone(zone)
        # An explicit offset disambiguates repeated DST times. Nonexistent local
        # times and offsets inconsistent with the named zone are rejected.
        if (local.date() != self.calendar_date or local.time() != wall_time
                or local.utcoffset() != self.resolved_instant.utcoffset()):
            raise ValueError('Date, local time, named zone and explicit offset must agree')
        return self


class ContractDeadlineResolutionRequest(Exact):
    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    resolution: ContractDeadlineResolution

    @model_validator(mode='after')
    def retained_source(self):
        if self.resolution.source.artifact_version > self.expected_version:
            raise ValueError('A future contract document cannot establish this deadline')
        return self


class DeadlineResolutionReviewRequest(ContractReviewRequest):
    """A term-specific human decision, pending controlled server persistence.

    Sequence is the shared deadline-review ledger sequence, not a per-term
    counter. Withdrawal names the original approval independently of that
    sequence so reviewing another term cannot redirect a withdrawal.
    """
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    term: DeadlineTerm
    resolution: ContractDeadlineResolution | None
    original_review_id: UUID | None

    @model_validator(mode='after')
    def exact_interpretation_decision(self):
        if '\x00' in self.note:
            raise ValueError('Document the review without NUL characters')
        if self.status == 'approved':
            proposal = self.resolution
            if proposal is None or self.original_review_id is not None:
                raise ValueError('Approval requires a new explicit interpretation')
            if proposal.term != self.term or proposal.source.artifact_id != self.artifact_id:
                raise ValueError('Review must identify the exact term and interpretation source')
            if proposal.source.artifact_version > self.expected_version:
                raise ValueError('Interpretation source must be a retained contract version')
        elif (self.resolution is not None or self.original_review_id is None
              or self.original_review_id == self.id or self.expected_sequence == 0):
            raise ValueError('Withdrawal must identify an original approval without replacing its interpretation')
        return self


class DeadlineResolutionReviewReceipt(ContractReviewReceipt):
    """Historical persistence only; never a fresh execution permission."""
    kind: Literal['deadline_resolution']
    term: DeadlineTerm
    interpretation_review_id: UUID

    @model_validator(mode='after')
    def exact_interpretation_identity(self):
        if ((self.status == 'approved') != (self.interpretation_review_id == self.review_id)):
            raise ValueError('Preserve the approval identity separately from its withdrawal')
        return self
