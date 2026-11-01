"""Human post-execution findings, never client-supplied disposition authority.

The controlled writer resolves the selected proposal and original sources
and binds current execution, deadline, title and reviewer-policy evidence.
Draft preparation reviews cannot satisfy those bindings.
"""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact, ContractReviewReceipt, ContractReviewState
from schemas.acquisition_disposition_plans import ExitType
from schemas.acquisition_title_review import TitleSource, TitleFinding

# Reuse the exact original-citation and finding validation already used by title
# review; using those value types does not reuse title approval authority.
COMMON_FINDINGS = ('contractual_interest', 'closing_structure', 'remaining_obligations')
ASSIGNMENT_FINDINGS = ('assignment_provisions', 'legal_basis', 'seller_disclosure_requirements', 'assignee_disclosure_requirements')


class AssignmentFindings(Exact):
    assignment_provisions: TitleFinding
    legal_basis: TitleFinding
    seller_disclosure_requirements: TitleFinding
    assignee_disclosure_requirements: TitleFinding


class DispositionFindings(Exact):
    exit_type: ExitType
    contractual_interest: TitleFinding
    closing_structure: TitleFinding
    remaining_obligations: TitleFinding
    assignment: AssignmentFindings | None

    def entries(self):
        items = [(name, getattr(self, name)) for name in COMMON_FINDINGS]
        if self.assignment is not None:
            items.extend((name, getattr(self.assignment, name)) for name in ASSIGNMENT_FINDINGS)
        return tuple(items)

    def all_sources(self) -> tuple[TitleSource, ...]:
        return tuple(source for _, finding in self.entries() for source in finding.sources)

    @model_validator(mode='after')
    def separate_exit_and_original_evidence(self):
        if (self.exit_type == 'wholesale_assignment') != (self.assignment is not None):
            raise ValueError('Assignment findings must match the proposed exit')
        originals = {}
        for source in self.all_sources():
            identity = (source.artifact_version, source.sha256)
            if source.artifact_id in originals and originals[source.artifact_id] != identity:
                raise ValueError('Conflicting original source identities')
            originals[source.artifact_id] = identity
        return self


class DispositionReviewRequest(Exact):
    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=0, le=2147483646)
    status: Literal['approved', 'requires_resolution', 'withdrawn']
    plan_id: UUID
    original_review_id: UUID | None
    policy_id: UUID
    expires_at: AwareDatetime | None
    personally_reviewed: StrictBool
    note: str = Field(strict=True, min_length=20, max_length=4000)
    findings: DispositionFindings | None

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_expiry(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit review expiry with timezone required')
        return value

    @model_validator(mode='after')
    def original_human_review(self):
        if len(self.note.strip()) < 20 or '\x00' in self.note:
            raise ValueError('Explain the human disposition review')
        if self.status == 'withdrawn':
            if (self.original_review_id is None or self.original_review_id == self.id or self.expected_sequence < 1
                    or self.personally_reviewed or self.expires_at is not None or self.findings is not None):
                raise ValueError('Withdraw the original review without replacing findings or renewing authority')
            return self
        if self.original_review_id is not None or not self.personally_reviewed or self.findings is None:
            raise ValueError('New disposition findings require personal review')
        if any(source.artifact_version > self.expected_version for source in self.findings.all_sources()):
            raise ValueError('Disposition findings cannot cite future contract versions')
        if self.status == 'approved':
            if self.expires_at is None or any(finding.finding != 'satisfactory' for _, finding in self.findings.entries()):
                raise ValueError('Unresolved disposition findings cannot be approved')
        elif self.expires_at is not None:
            raise ValueError('Resolution holds cannot carry approval expiry')
        return self


class DispositionReviewReceipt(ContractReviewReceipt):
    kind: Literal['disposition_findings']
    status: Literal['approved', 'requires_resolution', 'withdrawn']


class DispositionReviewState(ContractReviewState):
    kind: Literal['disposition_findings']
    status: Literal['not_reviewed', 'approved', 'requires_resolution', 'withdrawn', 'requires_review']

    @field_validator('expires_at', 'checked_at', mode='before')
    @classmethod
    def explicit_state_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit current disposition timestamp required')
        return value
