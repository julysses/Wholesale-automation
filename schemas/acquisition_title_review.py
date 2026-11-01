"""Human title findings, never verified facts or authority supplied by a client.

The controlled writer binds these to recorded execution and resolves original
sources under workspace/session/reviewer/scanner/retention locks.
Historical save receipts never represent current approval or execution authority.
"""
from typing import Literal
import re
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact, ContractReviewReceipt, ContractReviewState
from schemas.acquisition_contract_terms import ContractDateTerm

TITLE_FINDING_NAMES = ('ownership', 'legal_description', 'liens_and_payoffs',
                       'exceptions_and_encumbrances', 'occupancy_and_possession')


class TitleSource(Exact):
    artifact_id: UUID
    artifact_version: int = Field(strict=True, ge=1, le=2147483647)
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    locator: str = Field(strict=True, min_length=1, max_length=1000)

    @field_validator('locator')
    @classmethod
    def original_location(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Identify the original page or clause')
        return value


class TitleFinding(Exact):
    finding: Literal['satisfactory', 'requires_resolution', 'unknown']
    note: str = Field(strict=True, min_length=20, max_length=4000)
    required_action: str | None = Field(strict=True, min_length=20, max_length=4000)
    sources: tuple[TitleSource, ...] = Field(max_length=3)

    @model_validator(mode='after')
    def explicit_conclusion(self):
        if len(self.note.strip()) < 20 or '\x00' in self.note:
            raise ValueError('Explain the human finding without inferring facts')
        if self.finding == 'satisfactory':
            if not self.sources or self.required_action is not None:
                raise ValueError('Satisfactory findings require sources and no unresolved action')
        elif self.required_action is None or len(self.required_action.strip()) < 20 or '\x00' in self.required_action:
            raise ValueError('Unknown or unresolved findings require a concrete next action')
        identities = [(s.artifact_id, s.artifact_version, s.sha256, s.locator) for s in self.sources]
        if len(identities) != len(set(identities)):
            raise ValueError('Do not repeat the same original citation')
        return self


class TitleFindings(Exact):
    report_as_of: ContractDateTerm
    report_as_of_source: TitleSource | None
    report_note: str = Field(strict=True, min_length=20, max_length=4000)
    ownership: TitleFinding
    legal_description: TitleFinding
    liens_and_payoffs: TitleFinding
    exceptions_and_encumbrances: TitleFinding
    occupancy_and_possession: TitleFinding

    @field_validator('report_as_of', mode='before')
    @classmethod
    def preserve_report_timestamp_precision(cls, value):
        if isinstance(value, dict) and value.get('precision') == 'instant':
            stamp = value.get('instant')
            if isinstance(stamp, str) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', stamp):
                raise ValueError('Use an explicit report timestamp without losing source precision')
        return value

    @model_validator(mode='after')
    def source_precision_and_consistency(self):
        if len(self.report_note.strip()) < 20 or '\x00' in self.report_note:
            raise ValueError('Document the title report scope and cutoff')
        if (self.report_as_of.precision == 'unknown') != (self.report_as_of_source is None):
            raise ValueError('A known report cutoff needs its original citation; unknown remains unknown')
        # One immutable artifact cannot acquire contradictory bytes or versions
        # across findings. Different clauses within the same original are allowed.
        originals = {}
        for source in self.all_sources():
            identity = (source.artifact_version, source.sha256)
            if source.artifact_id in originals and originals[source.artifact_id] != identity:
                raise ValueError('Original source identity conflicts across title findings')
            originals[source.artifact_id] = identity
        return self

    def all_sources(self):
        sources = [self.report_as_of_source] if self.report_as_of_source else []
        for name in TITLE_FINDING_NAMES:
            sources.extend(getattr(self, name).sources)
        return tuple(sources)


class TitleReviewRequest(Exact):
    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    status: Literal['approved', 'requires_resolution', 'withdrawn']
    artifact_id: UUID
    verification_id: UUID
    policy_id: UUID
    expires_at: AwareDatetime | None
    personally_reviewed: StrictBool
    note: str = Field(strict=True, min_length=20, max_length=4000)
    findings: TitleFindings | None

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_expiry(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Use an explicit expiry timestamp with timezone')
        return value

    @model_validator(mode='after')
    def original_human_decision(self):
        if len(self.note.strip()) < 20 or '\x00' in self.note:
            raise ValueError('Explain this human title review decision')
        if self.status == 'withdrawn':
            if self.personally_reviewed or self.expires_at is not None or self.findings is not None:
                raise ValueError('Withdraw the original review without replacing findings or renewing authority')
            return self
        if not self.personally_reviewed or self.findings is None:
            raise ValueError('Personal review and explicit findings are required')
        if any(source.artifact_version > self.expected_version for source in self.findings.all_sources()):
            raise ValueError('Title findings cannot cite a future contract version')
        report_source = self.findings.report_as_of_source
        if report_source is not None and report_source.artifact_id != self.artifact_id:
            raise ValueError('Report cutoff must refer to the selected original title report')
        if self.status == 'approved':
            if self.expires_at is None or self.findings.report_as_of.precision == 'unknown':
                raise ValueError('Approval requires expiry and a sourced report cutoff')
            if any(getattr(self.findings, name).finding != 'satisfactory' for name in TITLE_FINDING_NAMES):
                raise ValueError('Unresolved title findings cannot be approved')
        elif self.expires_at is not None:
            raise ValueError('A resolution hold cannot carry approval expiry')
        return self


class TitleReviewReceipt(ContractReviewReceipt):
    kind: Literal['title_findings']
    status: Literal['approved', 'requires_resolution', 'withdrawn']


class TitleReviewState(ContractReviewState):
    kind: Literal['title_findings']
    status: Literal['not_reviewed', 'approved', 'requires_resolution', 'withdrawn', 'requires_review']


    @field_validator('expires_at', 'checked_at', mode='before')
    @classmethod
    def explicit_state_timestamp(cls, value):
        if value is not None and (not isinstance(value, str) or 'T' not in value):
            raise ValueError('Explicit current title timestamp required')
        return value


class TitleReportPolicy(Exact):
    max_age_seconds: int | None = Field(strict=True, ge=1, le=31536000)
    max_age_days: int | None = Field(strict=True, ge=0, le=365)
    timezone: str | None = Field(strict=True, min_length=1, max_length=100)

    @model_validator(mode='after')
    def explicit_supported_precision(self):
        if self.max_age_seconds is None and self.max_age_days is None:
            raise ValueError('At least one report precision must be explicitly supported')
        if (self.max_age_days is None) != (self.timezone is None):
            raise ValueError('Calendar report age requires an explicit named timezone')
        if self.timezone is not None:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError('Named report policy timezone required') from None
        return self


class TitleResolutionChoice(Exact):
    artifact_id: UUID
    source_version: int = Field(strict=True, ge=1, le=2147483647)
    verification_id: UUID
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    policy_id: UUID
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    available_until: AwareDatetime

    @field_validator('available_until', mode='before')
    @classmethod
    def explicit_availability(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit choice availability required')
        return value


class TitleApprovalChoice(TitleResolutionChoice):
    max_expires_at: AwareDatetime
    report_policy: TitleReportPolicy

    @field_validator('max_expires_at', mode='before')
    @classmethod
    def explicit_maximum(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit approval expiry bound required')
        return value


class TitleWithdrawalChoice(Exact):
    review_id: UUID
    artifact_id: UUID
    source_version: int = Field(strict=True, ge=1, le=2147483647)
    verification_id: UUID
    policy_id: UUID
    expected_sequence: int = Field(strict=True, ge=1, lt=2147483647)
    original_status: Literal['approved', 'requires_resolution']


class TitleReviewCandidate(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    artifact_id: UUID | None
    status: Literal['paused', 'contract_unavailable', 'history_limit_reached', 'document_required',
                    'reviewer_policy_required', 'evidence_review_required', 'execution_review_required',
                    'report_freshness_policy_required', 'ready_for_human_review']
    candidate: TitleApprovalChoice | None
    resolution: TitleResolutionChoice | None
    withdrawal: TitleWithdrawalChoice | None
    current_review: TitleReviewState
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_checked_time(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit choice check timestamp required')
        return value

    @model_validator(mode='after')
    def exact_choices(self):
        state = self.current_review
        if self.execution_authorized or ((state.workspace_id, state.contract_id, state.contract_version, state.checked_at)
                != (self.workspace_id, self.contract_id, self.contract_version, self.checked_at)):
            raise ValueError('Exact current title scope required')
        if (self.status == 'ready_for_human_review') != (self.candidate is not None):
            raise ValueError('Held title choice cannot offer approval')
        if (self.status in {'ready_for_human_review', 'execution_review_required', 'report_freshness_policy_required'}) != (self.resolution is not None):
            raise ValueError('Resolution choice must match current source and reviewer availability')
        if self.resolution:
            choice = self.resolution
            if (choice.artifact_id != self.artifact_id or choice.source_version > self.contract_version
                    or choice.expected_sequence != state.sequence
                    or not 0 < (choice.available_until-self.checked_at).total_seconds() <= 86400):
                raise ValueError('Current original source and bounded choice required')
        if self.candidate:
            choice = self.candidate
            if (choice.model_dump(exclude={'max_expires_at', 'report_policy'}) != self.resolution.model_dump()
                    or not self.checked_at < choice.max_expires_at <= choice.available_until):
                raise ValueError('Approval and resolution choices must share exact source and policy')
        if self.withdrawal:
            choice = self.withdrawal
            expected_status = 'requires_resolution' if state.status == 'requires_resolution' else 'approved'
            if (choice.source_version > self.contract_version or choice.review_id != state.review_id
                    or choice.expected_sequence != state.sequence or state.status not in {'approved', 'requires_review', 'requires_resolution'}
                    or choice.original_status != expected_status):
                raise ValueError('Original title withdrawal identity required')
        return self
