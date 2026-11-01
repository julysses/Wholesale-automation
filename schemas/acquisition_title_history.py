"""Historical title decisions; retained evidence never implies current authority."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact
from schemas.acquisition_contract_documents import DocumentPurpose
from schemas.acquisition_title_review import TitleFindings, TITLE_FINDING_NAMES


class TitleHistorySummary(Exact):
    id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    kind: Literal['title_findings']
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['approved', 'requires_resolution', 'withdrawn']
    artifact_id: UUID
    source_version: int = Field(strict=True, ge=1, le=2147483647)
    actor_id: UUID
    note: str = Field(strict=True, min_length=20, max_length=4000)
    expires_at: AwareDatetime | None
    created_at: AwareDatetime
    title_original_review_id: UUID | None
    title_original_status: Literal['approved', 'requires_resolution'] | None

    @field_validator('expires_at', 'created_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit historical timestamp required')
        return value

    @model_validator(mode='after')
    def original_decision_shape(self):
        if self.source_version > self.contract_version or len(self.note.strip()) < 20 or '\x00' in self.note:
            raise ValueError('Original title decision required')
        if self.status == 'approved':
            if self.expires_at is None or self.expires_at <= self.created_at:
                raise ValueError('Original approval validity required')
        elif self.expires_at is not None:
            raise ValueError('Held or withdrawn history cannot carry approval expiry')
        if self.status == 'withdrawn':
            if (self.title_original_review_id is None or self.title_original_review_id == self.id
                    or self.title_original_status is None or self.sequence <= 1):
                raise ValueError('Withdrawal must retain its original review')
        elif self.title_original_review_id is not None or self.title_original_status is not None:
            raise ValueError('New findings cannot impersonate a withdrawal')
        return self


class TitleHistorySource(Exact):
    artifact_id: UUID
    source_version: int = Field(strict=True, ge=1, le=2147483647)
    verification_id: UUID
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    purpose: DocumentPurpose
    expires_at: AwareDatetime

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_expiry(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit original source validity required')
        return value


class TitleHistoryDetail(TitleHistorySummary):
    verification_id: UUID
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    personally_reviewed: StrictBool
    title_findings: TitleFindings | None
    title_sources: tuple[TitleHistorySource, ...] | None = Field(max_length=16)
    title_execution_transition_id: UUID

    @model_validator(mode='after')
    def original_findings_and_sources(self):
        if self.status == 'withdrawn':
            if self.personally_reviewed or self.title_findings is not None or self.title_sources is not None:
                raise ValueError('Withdrawal does not replace original findings')
            return self
        if not self.personally_reviewed or self.title_findings is None or not self.title_sources:
            raise ValueError('Retained personal findings and original sources required')
        originals = {source.artifact_id: source for source in self.title_sources}
        if len(originals) != len(self.title_sources) or any(s.source_version > self.contract_version for s in self.title_sources):
            raise ValueError('Unique original sources required')
        report = originals.get(self.artifact_id)
        if report is None or (report.source_version, report.verification_id, report.sha256, report.purpose) != (
                self.source_version, self.verification_id, self.sha256, 'title_report'):
            raise ValueError('Original title report identity changed')
        for citation in self.title_findings.all_sources():
            original = originals.get(citation.artifact_id)
            if original is None or (citation.artifact_version, citation.sha256) != (original.source_version, original.sha256):
                raise ValueError('Citation differs from its original source')
        cutoff = self.title_findings.report_as_of_source
        if cutoff is not None and cutoff.artifact_id != self.artifact_id:
            raise ValueError('Report cutoff belongs to another document')
        if self.status == 'approved' and (self.title_findings.report_as_of.precision == 'unknown'
                or any(getattr(self.title_findings, name).finding != 'satisfactory' for name in TITLE_FINDING_NAMES)):
            raise ValueError('Original approval needs fully reviewed findings')
        return self
