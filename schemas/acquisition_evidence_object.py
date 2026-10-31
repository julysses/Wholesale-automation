"""Immutable retained object metadata shared by scoped evidence registries.

No descriptor grants access or approval; callers must resolve current registry state.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
EVIDENCE_BUCKET = 'acquisition-evidence'


class RetainedEvidenceObject(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: UUID
    workspace_id: UUID
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

