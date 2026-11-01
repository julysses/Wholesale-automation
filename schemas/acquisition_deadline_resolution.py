"""Explicit reviewer-supplied date interpretation; never a replacement contract term.

This isolated boundary is not an API or execution authorization. Persistence must
bind it to the current date-only term and independently verify the cited original.
"""
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, StrictBool, Field, field_validator, model_validator
from schemas.acquisition_contract_terms import Exact, ContractTermSource, ContractDateTerm
from schemas.acquisition_contract_reviews import ContractReviewRequest, ContractReviewReceipt, ReviewApprovalChoice, ReviewWithdrawalChoice

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


class DeadlineResolutionReviewState(Exact):
    """Selected-term history and shared concurrency cursor are distinct."""
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    kind: Literal['deadline_resolution']
    term: DeadlineTerm
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    review_sequence: int | None = Field(strict=True, ge=1, le=2147483647)
    review_id: UUID | None
    interpretation_review_id: UUID | None
    original_term: ContractDateTerm
    resolution: ContractDeadlineResolution | None
    status: Literal['not_reviewed', 'approved', 'withdrawn', 'requires_review']
    approval_current: StrictBool
    expires_at: AwareDatetime | None
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @field_validator('expires_at', 'checked_at', mode='before')
    @classmethod
    def explicit_state_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit state timestamp required')
        return value

    @model_validator(mode='after')
    def coherent_term_history(self):
        if self.execution_authorized or self.approval_current != (self.status == 'approved'):
            raise ValueError('Interpretation state cannot infer execution authority')
        if self.status == 'not_reviewed':
            if any(value is not None for value in (self.review_id, self.review_sequence, self.interpretation_review_id, self.resolution)):
                raise ValueError('Unreviewed term cannot carry another term decision')
        else:
            if (self.review_id is None or self.review_sequence is None or self.review_sequence > self.sequence
                    or self.interpretation_review_id is None or self.resolution is None):
                raise ValueError('Exact selected-term history required')
            if (self.status == 'withdrawn') == (self.review_id == self.interpretation_review_id):
                raise ValueError('Preserve original interpretation and distinct withdrawal identities')
            if (self.resolution.term != self.term or self.resolution.source.artifact_version > self.contract_version
                    or self.original_term.precision != 'date'
                    or self.original_term.calendar_date != self.resolution.calendar_date):
                raise ValueError('Preserve the original calendar date and term source')
        if self.approval_current:
            if self.expires_at is None or self.expires_at <= self.checked_at:
                raise ValueError('Current interpretation requires a future expiry')
        elif self.expires_at is not None:
            raise ValueError('Historical interpretation cannot expose current expiry')
        return self


class DeadlineOriginalSource(ContractTermSource):
    verification_id: UUID


class DeadlineApprovalChoice(ReviewApprovalChoice):
    source_version: int = Field(strict=True, ge=1, le=2147483647)


class DeadlineWithdrawalChoice(ReviewWithdrawalChoice):
    source_version: int = Field(strict=True, ge=1, le=2147483647)


class DeadlineResolutionCandidate(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    term: DeadlineTerm
    artifact_id: UUID
    status: Literal['paused', 'contract_unavailable', 'history_limit_reached', 'prepared_terms_required',
                    'original_date_required', 'original_evidence_review_required', 'reviewer_policy_required',
                    'evidence_review_required', 'ready_for_human_review']
    candidate: DeadlineApprovalChoice | None
    withdrawal: DeadlineWithdrawalChoice | None
    original_source: DeadlineOriginalSource | None
    current_review: DeadlineResolutionReviewState
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_candidate_timestamp(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit candidate timestamp required')
        return value

    @model_validator(mode='after')
    def exact_term_actions(self):
        state = self.current_review
        if (self.execution_authorized or (state.workspace_id, state.contract_id, state.contract_version, state.term, state.checked_at)
                != (self.workspace_id, self.contract_id, self.contract_version, self.term, self.checked_at)):
            raise ValueError('Exact current deadline context required')
        if (self.status == 'ready_for_human_review') != (self.candidate is not None):
            raise ValueError('Held state cannot offer approval')
        if self.original_source and (self.original_source.term != self.term
                or self.original_source.artifact_version >= self.contract_version):
            raise ValueError('Exact retained original date source required')
        choice = self.candidate
        if choice and (self.original_source is None or state.original_term.precision != 'date'
                or choice.artifact_id != self.artifact_id or choice.source_version > self.contract_version
                or choice.expected_sequence != state.sequence
                or not 0 < (choice.max_expires_at-self.checked_at).total_seconds() <= 86400):
            raise ValueError('Bounded exact source and shared save sequence required')
        withdrawal = self.withdrawal
        if withdrawal and (withdrawal.source_version > self.contract_version
                or withdrawal.review_id != state.review_id or withdrawal.expected_sequence != state.sequence
                or state.status not in {'approved', 'requires_review'} or state.resolution is None
                or withdrawal.artifact_id != state.resolution.source.artifact_id
                or withdrawal.source_version != state.resolution.source.artifact_version):
            raise ValueError('Original selected-term withdrawal required')
        return self
