"""Sourced execution findings, not trusted facts or authorization.

The mounted API uses controlled persistence to resolve every referenced original
under current workspace, version, scanner and reviewer policy locks. The pure
assessment alone does not approve a contract or authorize a status transition.
"""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, StrictBool, Field, field_validator, model_validator, model_serializer

from schemas.acquisition_contract_reviews import ContractReviewRequest, ContractReviewReceipt, ContractReviewState, ReviewApprovalChoice, ReviewWithdrawalChoice, Exact
from schemas.acquisition_contract_terms import ContractTermsDraft


class ExecutionFinding(Exact):
    finding: Literal['confirmed', 'not_confirmed', 'unknown']
    locator: str = Field(strict=True, min_length=1, max_length=1000)
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @model_validator(mode='after')
    def substantive_source(self):
        # Keep exact text for request identity; reject invisible/empty citations.
        if (not self.locator.strip() or any(ord(c) < 32 for c in self.locator)
                or len(self.note.strip()) < 20 or '\x00' in self.note):
            raise ValueError('Document the source and finding without inferring confirmation')
        return self


class ExecutionDeadlineReview(Exact):
    term: Literal['effective', 'inspection_deadline', 'closing_deadline']
    review_id: UUID


class ExecutionFindings(Exact):
    """All findings refer to the request's exact returned contract artifact.

Supplemental term sources retain their own immutable original identities. The
repository must resolve these before any reviewer decision can be current.
"""
    seller_signatures: ExecutionFinding
    buyer_signatures: ExecutionFinding
    signing_authority: ExecutionFinding
    complete_agreement: ExecutionFinding
    terms: ContractTermsDraft
    deadline_reviews: tuple[ExecutionDeadlineReview, ...] | None = Field(default=None, min_length=1, max_length=3)

    @field_validator('deadline_reviews', mode='before')
    @classmethod
    def explicit_bindings(cls, value):
        if value is None:
            raise ValueError('Omit legacy bindings or provide exact reviewed identities')
        return value

    @model_validator(mode='after')
    def exact_calendar_bindings(self):
        if self.deadline_reviews is not None:
            required = {name for name in ('effective', 'inspection_deadline', 'closing_deadline')
                        if getattr(self.terms, name).precision == 'date'}
            names = [binding.term for binding in self.deadline_reviews]
            identities = [binding.review_id for binding in self.deadline_reviews]
            if set(names) != required or len(set(names)) != len(names) or len(set(identities)) != len(identities):
                raise ValueError('Bind each calendar-only term to its own exact reviewed interpretation')
        return self

    @model_serializer(mode='wrap')
    def preserve_legacy_request(self, handler):
        value = handler(self)
        if self.deadline_reviews is None:
            value.pop('deadline_reviews', None)
        return value


class ExecutionReviewRequest(ContractReviewRequest):
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    findings: ExecutionFindings | None

    @model_validator(mode='after')
    def decision_findings(self):
        if self.status == 'approved':
            if self.findings is None:
                raise ValueError('Execution review requires sourced findings')
            for name in ('seller_signatures', 'buyer_signatures', 'signing_authority', 'complete_agreement'):
                if getattr(self.findings, name).finding != 'confirmed':
                    raise ValueError('Unconfirmed findings cannot support an approved execution review')
            if any(source.artifact_version > self.expected_version for source in self.findings.terms.sources):
                raise ValueError('Execution terms cannot reference a future contract version')
        elif self.findings is not None:
            raise ValueError('Withdrawal preserves the original findings without replacing them')
        return self


# Reuse historical receipt invariants while keeping the old review-kind API closed.
class ExecutionReviewReceipt(ContractReviewReceipt):
    kind: Literal['executed_contract']


class ExecutionReviewState(ContractReviewState):
    kind: Literal['executed_contract']


class ExecutionApprovalChoice(ReviewApprovalChoice):
    source_version: int = Field(strict=True, ge=1, le=2147483647)


class ExecutionWithdrawalChoice(ReviewWithdrawalChoice):
    source_version: int = Field(strict=True, ge=1, le=2147483647)


class ExecutionReviewCandidate(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    artifact_id: UUID
    status: Literal['paused', 'contract_unavailable', 'history_limit_reached', 'prepared_terms_required',
                    'reviewer_policy_required', 'evidence_review_required', 'ready_for_human_review']
    candidate: ExecutionApprovalChoice | None
    withdrawal: ExecutionWithdrawalChoice | None
    prepared_terms: ContractTermsDraft | None
    current_review: ExecutionReviewState
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit checked timestamp required')
        return value

    @model_validator(mode='after')
    def exact_choices(self):
        state = self.current_review
        if self.execution_authorized or ((state.workspace_id, state.contract_id, state.contract_version, state.checked_at)
                != (self.workspace_id, self.contract_id, self.contract_version, self.checked_at)):
            raise ValueError('Exact current review scope required')
        if (self.status == 'ready_for_human_review') != (self.candidate is not None):
            raise ValueError('Held state cannot offer approval')
        if self.prepared_terms and any(source.artifact_version > self.contract_version for source in self.prepared_terms.sources):
            raise ValueError('Prepared terms cannot reference a future source')
        choice = self.candidate
        if choice and (self.prepared_terms is None or choice.artifact_id != self.artifact_id
                or choice.source_version > self.contract_version or choice.expected_sequence != state.sequence
                or not 0 < (choice.max_expires_at-self.checked_at).total_seconds() <= 86400):
            raise ValueError('Current bounded source choice required')
        withdrawal = self.withdrawal
        if withdrawal and (withdrawal.source_version > self.contract_version or withdrawal.review_id != state.review_id
                or withdrawal.expected_sequence != state.sequence or state.status not in {'approved','requires_review'}):
            raise ValueError('Original withdrawal identity required')
        return self
