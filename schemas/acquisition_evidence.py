"""Internal immutable evidence descriptor, never a public download request.

The protected evidence registry supplies these fields through actual workspace
membership checks. A descriptor alone is not proof of access, provenance or approval.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

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


class EvidenceRegistryState(EvidenceArtifact):
    """Exact current-state RPC projection; never accept this model from an HTTP caller."""
    id: UUID = Field(validation_alias='artifact_id')
    sha256: str = Field(validation_alias='expected_sha256', pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(validation_alias='expected_byte_size', strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    retention_policy_id: UUID
    status: Literal['pending_verification']
    bytes_verified: StrictBool
    content_approved: StrictBool
    execution_authorized: StrictBool
    checked_at: AwareDatetime

    @model_validator(mode='after')
    def unverified_state(self):
        if self.revoked_at is not None or self.bytes_verified or self.content_approved or self.execution_authorized:
            raise ValueError('Unverified current registry state required')
        return self

    def descriptor(self) -> EvidenceArtifact:
        return EvidenceArtifact.model_validate({key: getattr(self, key) for key in EvidenceArtifact.model_fields})
