"""Current proposal/reviewer choices; original withdrawal is independent."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact
from schemas.acquisition_disposition_plans import ExitType
from schemas.acquisition_disposition_review import DispositionReviewState
from schemas.acquisition_title_history import TitleHistorySource


class DispositionResolutionChoice(Exact):
    plan_id: UUID
    exit_type: ExitType
    policy_id: UUID
    execution_transition_id: UUID
    title_entry_id: UUID
    title_review_id: UUID
    title_status: Literal['approved', 'requires_resolution']
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    available_until: AwareDatetime
    executed_source: TitleHistorySource
    legal_source: TitleHistorySource | None

    @field_validator('available_until', mode='before')
    @classmethod
    def explicit_availability(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit choice availability required')
        return value

    @model_validator(mode='after')
    def original_sources(self):
        if self.executed_source.purpose != 'purchase_contract' or self.available_until > self.executed_source.expires_at:
            raise ValueError('Choice must retain the bounded executed original')
        if self.exit_type == 'principal_acquisition' and self.legal_source is not None:
            raise ValueError('Principal choice cannot inherit assignment legal authority')
        if self.legal_source and self.legal_source.artifact_id == self.executed_source.artifact_id and self.legal_source != self.executed_source:
            raise ValueError('One original must retain one exact source identity')
        return self


class DispositionApprovalChoice(DispositionResolutionChoice):
    max_expires_at: AwareDatetime

    @field_validator('max_expires_at', mode='before')
    @classmethod
    def explicit_expiry(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit approval bound required')
        return value

    @model_validator(mode='after')
    def bounded_title_and_legal_evidence(self):
        if self.title_status != 'approved' or self.max_expires_at > self.available_until:
            raise ValueError('Current title and bounded approval required')
        if self.exit_type == 'wholesale_assignment' and (self.legal_source is None or self.max_expires_at > self.legal_source.expires_at):
            raise ValueError('Assignment approval needs bounded original legal evidence')
        return self


class DispositionWithdrawalChoice(Exact):
    review_id: UUID
    plan_id: UUID
    exit_type: ExitType
    policy_id: UUID
    expected_sequence: int = Field(strict=True, ge=1, lt=2147483647)
    original_status: Literal['approved', 'requires_resolution']


class DispositionReviewCandidate(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['paused', 'contract_unavailable', 'history_limit_reached', 'proposal_required',
                    'title_findings_required', 'reviewer_policy_required', 'evidence_review_required',
                    'execution_review_required', 'title_review_required', 'legal_evidence_required', 'ready_for_human_review']
    candidate: DispositionApprovalChoice | None
    resolution: DispositionResolutionChoice | None
    withdrawal: DispositionWithdrawalChoice | None
    current_review: DispositionReviewState
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_checked_at(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit current-choice timestamp required')
        return value

    @model_validator(mode='after')
    def exact_current_choices(self):
        state = self.current_review
        if self.execution_authorized or (state.workspace_id, state.contract_id, state.contract_version, state.checked_at) != (
                self.workspace_id, self.contract_id, self.contract_version, self.checked_at):
            raise ValueError('Exact current disposition scope required')
        if (self.status == 'ready_for_human_review') != (self.candidate is not None):
            raise ValueError('Held choices cannot offer approval')
        if (self.status in {'ready_for_human_review', 'execution_review_required', 'title_review_required', 'legal_evidence_required'}) != (self.resolution is not None):
            raise ValueError('Resolution availability must match current context')
        if self.status == 'history_limit_reached' and (state.sequence != 2147483647 or self.withdrawal is not None):
            raise ValueError('Exhausted history cannot offer another decision')
        if self.status == 'legal_evidence_required' and (self.resolution is None or self.resolution.exit_type != 'wholesale_assignment' or self.resolution.legal_source is not None):
            raise ValueError('Missing legal evidence must match an assignment hold')
        if self.resolution:
            choice = self.resolution
            if choice.expected_sequence != state.sequence or not 0 < (choice.available_until-self.checked_at).total_seconds() <= 86400:
                raise ValueError('Current bounded sequence and availability required')
            for source in (choice.executed_source, choice.legal_source):
                if source is not None and (source.source_version > self.contract_version or source.expires_at <= self.checked_at):
                    raise ValueError('Current original source version and validity required')
        if self.candidate:
            choice = self.candidate
            if choice.model_dump(exclude={'max_expires_at'}) != self.resolution.model_dump() or choice.max_expires_at <= self.checked_at:
                raise ValueError('Approval and hold choices must share exact original context')
        if self.withdrawal:
            choice = self.withdrawal
            expected_status = 'requires_resolution' if state.status == 'requires_resolution' else 'approved'
            if choice.review_id != state.review_id or choice.expected_sequence != state.sequence or state.status not in {'approved', 'requires_review', 'requires_resolution'} or choice.original_status != expected_status:
                raise ValueError('Original personal withdrawal identity required')
        return self
