"""Bounded original findings and current renewal choices, never execution authority."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, BeforeValidator, Field, StrictBool, model_validator
from schemas.acquisition_contract_reviews import Exact
from schemas.acquisition_review_renewal import ReviewKind, DeadlineTerm
from schemas.acquisition_deadline_resolution import ContractDeadlineResolution
from schemas.acquisition_execution_review import ExecutionFindings
from schemas.acquisition_title_review import TitleFindings
from schemas.acquisition_disposition_review import DispositionFindings
from schemas.acquisition_title_history import TitleHistorySource


def explicit_timestamp(value):
    if isinstance(value, datetime) or isinstance(value, str) and 'T' in value:
        return value
    raise ValueError('Explicit timezone-aware review timestamp required')


Timestamp = Annotated[AwareDatetime, BeforeValidator(explicit_timestamp)]


class RenewalOriginal(Exact):
    created_at: Timestamp
    expires_at: Timestamp
    findings: ContractDeadlineResolution | ExecutionFindings | TitleFindings | DispositionFindings


class RenewalCurrent(Exact):
    review_id: UUID
    expires_at: Timestamp
    approval_current: StrictBool


class RenewalDependency(RenewalCurrent):
    root_review_id: UUID
    kind: ReviewKind
    deadline_term: DeadlineTerm | None

    @model_validator(mode='after')
    def kind_context(self):
        if (self.kind == 'deadline_resolution') != (self.deadline_term is not None):
            raise ValueError('Exact supporting date-review context required')
        return self


class RenewalApprovalChoice(Exact):
    expected_sequence: int = Field(strict=True, ge=1, le=2147483646)
    previous_review_id: UUID
    policy_id: UUID
    expected_snapshot_sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    max_expires_at: Timestamp
    sources: tuple[TitleHistorySource, ...] = Field(min_length=1, max_length=64)


class ReviewRenewalCandidate(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    root_review_id: UUID
    kind: ReviewKind
    deadline_term: DeadlineTerm | None
    status: Literal['paused', 'contract_unavailable', 'withdrawn_or_superseded', 'history_limit_reached',
                    'reviewer_policy_required', 'supporting_review_required', 'evidence_review_required',
                    'report_review_required', 'purchase_path_changed', 'legal_evidence_required', 'ready_for_human_review']
    candidate: RenewalApprovalChoice | None
    original: RenewalOriginal
    current_review: RenewalCurrent | None
    dependencies: tuple[RenewalDependency, ...] = Field(max_length=3)
    checked_at: Timestamp
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def exact_original_and_current_bounds(self):
        if self.execution_authorized:
            raise ValueError('Renewal choices never authorize execution')
        types = dict(deadline_resolution=ContractDeadlineResolution, executed_contract=ExecutionFindings,
                     title_findings=TitleFindings, disposition_findings=DispositionFindings)
        if not isinstance(self.original.findings, types[self.kind]):
            raise ValueError('Findings must match the original review kind')
        if (self.kind == 'deadline_resolution') != (self.deadline_term is not None):
            raise ValueError('Exact original date-review context required')
        if self.kind == 'deadline_resolution' and self.original.findings.term != self.deadline_term:
            raise ValueError('Original interpretation must match its date term')
        if self.original.created_at > self.checked_at or self.original.expires_at <= self.original.created_at:
            raise ValueError('Original review chronology required')
        if (self.status == 'ready_for_human_review') != (self.candidate is not None):
            raise ValueError('Only ready choices may offer a personal review')
        identities = [d.root_review_id for d in self.dependencies]
        if len(set(identities)) != len(identities) or self.root_review_id in identities:
            raise ValueError('Distinct original supporting reviews required')
        permitted = {'deadline_resolution': set(), 'executed_contract': {'deadline_resolution'},
                     'title_findings': {'executed_contract'}, 'disposition_findings': {'executed_contract', 'title_findings'}}
        if any(d.kind not in permitted[self.kind] for d in self.dependencies):
            raise ValueError('Unexpected supporting review kind')
        if self.current_review and self.current_review.approval_current and self.current_review.expires_at <= self.checked_at:
            raise ValueError('Current review cannot already be expired')
        if any(d.approval_current and d.expires_at <= self.checked_at for d in self.dependencies):
            raise ValueError('Current support cannot already be expired')
        if self.candidate:
            c = self.candidate
            if not self.current_review or c.previous_review_id != self.current_review.review_id or c.max_expires_at <= self.checked_at:
                raise ValueError('Current exact predecessor and bounded expiry required')
            if any(not d.approval_current or c.max_expires_at > d.expires_at for d in self.dependencies):
                raise ValueError('Renewal cannot outlive its current supporting reviews')
            expected = 0 if self.kind == 'deadline_resolution' else (len(self.original.findings.deadline_reviews or ()) if self.kind == 'executed_contract'
                else 1 if self.kind == 'title_findings' else 2)
            if self.kind == 'disposition_findings' and {d.kind for d in self.dependencies} != {'executed_contract', 'title_findings'}:
                raise ValueError('Execution and title support both required')
            if self.kind == 'executed_contract' and {(d.root_review_id, d.deadline_term) for d in self.dependencies} != {(d.review_id, d.term) for d in self.original.findings.deadline_reviews or ()}:
                raise ValueError('Original date interpretation roots must match')
            if len(self.dependencies) != expected:
                raise ValueError('Complete supporting review set required')
            if len({s.artifact_id for s in c.sources}) != len(c.sources) or any(s.source_version > self.contract_version or c.max_expires_at > s.expires_at for s in c.sources):
                raise ValueError('Exact bounded original source identities required')
        return self


class RenewalSummary(Exact):
    root_review_id: UUID
    kind: ReviewKind
    deadline_term: DeadlineTerm | None
    status: Literal['paused', 'contract_unavailable', 'withdrawn_or_superseded', 'history_limit_reached',
                    'reviewer_policy_required', 'supporting_review_required', 'evidence_review_required',
                    'report_review_required', 'purchase_path_changed', 'legal_evidence_required', 'ready_for_human_review']
    current_review: RenewalCurrent | None

    @model_validator(mode='after')
    def consistent_context(self):
        if (self.kind == 'deadline_resolution') != (self.deadline_term is not None):
            raise ValueError('Original review kind/date context required')
        if self.status == 'ready_for_human_review' and self.current_review is None:
            raise ValueError('Ready review requires an exact predecessor')
        return self


class ReviewRenewalIndex(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    items: tuple[RenewalSummary, ...] = Field(max_length=6)
    checked_at: Timestamp
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def bounded_original_reviews(self):
        if self.execution_authorized:
            raise ValueError('Discovery cannot authorize execution')
        if len({item.root_review_id for item in self.items}) != len(self.items) or len({(item.kind,item.deadline_term) for item in self.items}) != len(self.items):
            raise ValueError('One original root per current review stream required')
        if any(item.current_review and item.current_review.approval_current and item.current_review.expires_at <= self.checked_at for item in self.items):
            raise ValueError('Current review cannot already be expired')
        return self
