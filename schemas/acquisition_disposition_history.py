"""Historical disposition decisions; retained evidence never implies current authority."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact
from schemas.acquisition_disposition_review import DispositionFindings
from schemas.acquisition_title_history import TitleHistorySource
from schemas.acquisition_disposition_plans import ExitType


class DispositionHistorySummary(Exact):
    id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    kind: Literal['disposition_findings']
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['approved', 'requires_resolution', 'withdrawn']
    artifact_id: UUID
    source_version: int = Field(strict=True, ge=1, le=2147483647)
    disposition_plan_id: UUID
    disposition_exit_type: ExitType
    actor_id: UUID
    note: str = Field(strict=True, min_length=20, max_length=4000)
    expires_at: AwareDatetime | None
    created_at: AwareDatetime
    disposition_original_review_id: UUID | None
    disposition_original_status: Literal['approved', 'requires_resolution'] | None

    @field_validator('expires_at', 'created_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit historical timestamp required')
        return value

    @model_validator(mode='after')
    def original_decision_shape(self):
        if self.source_version > self.contract_version or len(self.note.strip()) < 20 or '\x00' in self.note:
            raise ValueError('Original disposition decision required')
        if self.status == 'approved':
            if self.expires_at is None or self.expires_at <= self.created_at:
                raise ValueError('Original approval validity required')
        elif self.expires_at is not None:
            raise ValueError('Held or withdrawn history cannot carry approval expiry')
        if self.status == 'withdrawn':
            if (self.disposition_original_review_id is None or self.disposition_original_review_id == self.id
                    or self.disposition_original_status is None or self.sequence <= 1):
                raise ValueError('Withdrawal must retain its original review')
        elif self.disposition_original_review_id is not None or self.disposition_original_status is not None:
            raise ValueError('New findings cannot impersonate a withdrawal')
        return self


class DispositionHistoryDetail(DispositionHistorySummary):
    verification_id: UUID
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    personally_reviewed: StrictBool
    disposition_findings: DispositionFindings | None
    disposition_sources: tuple[TitleHistorySource, ...] | None = Field(max_length=22)
    disposition_execution_id: UUID
    disposition_title_entry_id: UUID
    disposition_title_review_id: UUID
    disposition_title_status: Literal['approved', 'requires_resolution']

    @model_validator(mode='after')
    def original_findings_and_sources(self):
        if self.status == 'withdrawn':
            if self.personally_reviewed or self.disposition_findings is not None or self.disposition_sources is not None:
                raise ValueError('Withdrawal does not replace original findings')
            return self
        if not self.personally_reviewed or self.disposition_findings is None or not self.disposition_sources:
            raise ValueError('Retained human findings and original sources required')
        findings = self.disposition_findings
        if findings.exit_type != self.disposition_exit_type:
            raise ValueError('Findings belong to the original proposed exit')
        originals = {source.artifact_id: source for source in self.disposition_sources}
        if len(originals) != len(self.disposition_sources) or any(s.source_version > self.contract_version for s in self.disposition_sources):
            raise ValueError('Unique original sources required')
        contract = originals.get(self.artifact_id)
        if contract is None or (contract.source_version, contract.verification_id, contract.sha256, contract.purpose) != (
                self.source_version, self.verification_id, self.sha256, 'purchase_contract'):
            raise ValueError('Original executed contract identity changed')
        for citation in findings.all_sources():
            original = originals.get(citation.artifact_id)
            if original is None or (citation.artifact_version, citation.sha256) != (original.source_version, original.sha256):
                raise ValueError('Citation differs from its original source')
        for finding in (findings.contractual_interest, findings.assignment.assignment_provisions if findings.assignment else None):
            if finding is not None and finding.finding == 'satisfactory' and not any(s.artifact_id == self.artifact_id for s in finding.sources):
                raise ValueError('Contract findings must retain the recorded executed original')
        if self.status == 'approved' and (any(s.expires_at < self.expires_at for s in self.disposition_sources)
                or self.disposition_title_status != 'approved'
                or any(finding.finding != 'satisfactory' for _, finding in findings.entries())):
            raise ValueError('Original approval needs resolved title and disposition findings')
        return self
