"""Internal immutable evidence descriptor, never a public download request.

The protected evidence registry supplies these fields through actual workspace
membership checks. A descriptor alone is not proof of access, provenance or approval.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
EVIDENCE_BUCKET = 'acquisition-evidence'


class EvidenceArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    purpose: Literal['mail_content', 'mail_destination']
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    media_type: Literal['application/pdf', 'image/png', 'image/jpeg', 'text/plain']
    created_at: AwareDatetime
    retain_until: AwareDatetime
    revoked_at: AwareDatetime | None

    @model_validator(mode='after')
    def retention_order(self):
        if self.retain_until <= self.created_at:
            raise ValueError('Retention must follow creation')
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError('Revocation cannot precede creation')
        return self

    @property
    def object_name(self) -> str:
        # No caller filename, URL, traversal, query, or mutable latest-version alias.
        return f'{self.workspace_id}/{self.id}/{self.sha256}'

    def available_at(self, now: datetime) -> bool:
        return now.utcoffset() is not None and self.revoked_at is None and self.created_at <= now < self.retain_until


class EvidenceState(EvidenceArtifact):
    """Exact current-state RPC projection, including unavailable historical artifacts."""
    id: UUID = Field(validation_alias='artifact_id')
    sha256: str = Field(validation_alias='expected_sha256', pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(validation_alias='expected_byte_size', strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    retention_policy_id: UUID
    status: Literal['pending_verification', 'revoked', 'expired', 'policy_review_required']
    bytes_verified: StrictBool
    content_approved: StrictBool
    execution_authorized: StrictBool
    checked_at: AwareDatetime

    @field_validator('created_at', 'retain_until', 'revoked_at', 'checked_at', mode='before')
    @classmethod
    def rpc_timestamps_are_strings(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def unverified_state(self):
        if self.bytes_verified or self.content_approved or self.execution_authorized:
            raise ValueError('Unverified current registry state required')
        if self.checked_at < self.created_at:
            raise ValueError('State cannot precede artifact creation')
        if self.status == 'revoked':
            if self.revoked_at is None or self.revoked_at > self.checked_at:
                raise ValueError('Current revocation required')
        elif self.revoked_at is not None:
            raise ValueError('Revocation must take precedence')
        elif self.status == 'expired':
            if self.retain_until > self.checked_at:
                raise ValueError('Retention has not expired')
        elif self.retain_until <= self.checked_at:
            raise ValueError('Expired retention must take precedence')
        return self

    def descriptor(self) -> EvidenceArtifact:
        return EvidenceArtifact.model_validate({key: getattr(self, key) for key in EvidenceArtifact.model_fields})


class EvidenceRegistryState(EvidenceState):
    """Only this current state may enter the internal byte verification transport."""
    status: Literal['pending_verification']


class EvidenceRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    purpose: Literal['mail_content', 'mail_destination']
    expected_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_byte_size: int = Field(strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    media_type: Literal['application/pdf', 'image/png', 'image/jpeg', 'text/plain']
    retention_policy_id: UUID
    provenance_note: str = Field(min_length=20, max_length=2000)

    @field_validator('provenance_note')
    @classmethod
    def documented_provenance(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Documented provenance required')
        return value  # Preserve exact text for idempotent request recovery.


class EvidenceRevocation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    reason: str = Field(min_length=20, max_length=2000)

    @field_validator('reason')
    @classmethod
    def documented_reason(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Documented revocation required')
        return value


class EvidenceRegistrationReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifact_id: UUID
    workspace_id: UUID
    retain_until: AwareDatetime
    duplicate: StrictBool
    bytes_verified: StrictBool
    execution_authorized: StrictBool

    @field_validator('retain_until', mode='before')
    @classmethod
    def rpc_retention_is_a_string(cls, value):
        if not isinstance(value, str):
            raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def registration_is_not_verification(self):
        if self.bytes_verified or self.execution_authorized:
            raise ValueError('Registration grants no verification or execution')
        return self


class EvidenceRevocationReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revocation_id: UUID
    artifact_id: UUID
    workspace_id: UUID
    duplicate: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def revocation_is_not_execution(self):
        if self.execution_authorized:
            raise ValueError('Revocation grants no execution')
        return self
