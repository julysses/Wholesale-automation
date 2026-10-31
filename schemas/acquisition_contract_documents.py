"""Internal version-bound descriptors; never caller authorization or legal review."""
from typing import Literal
from uuid import UUID
from pydantic import Field, AwareDatetime, StrictBool, field_validator, model_validator
from schemas.acquisition_evidence_object import MAX_EVIDENCE_BYTES
from schemas.acquisition_evidence_object import RetainedEvidenceObject


class ContractDocumentArtifact(RetainedEvidenceObject):
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    # Classification alone never proves signature, title, disclosure or legal sufficiency.
    purpose: Literal['purchase_contract', 'title_report', 'assignment_agreement',
                     'seller_disclosure', 'assignee_disclosure', 'closing_statement', 'supporting_document']


class ContractDocumentRegistryState(ContractDocumentArtifact):
    """Only a current unverified registry projection can enter byte observation."""
    id: UUID = Field(validation_alias='artifact_id')
    sha256: str = Field(validation_alias='expected_sha256', pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(validation_alias='expected_byte_size', strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    retention_policy_id: UUID
    status: Literal['pending_verification']
    bytes_verified: StrictBool
    legal_review_approved: StrictBool
    execution_authorized: StrictBool
    checked_at: AwareDatetime

    @field_validator('created_at', 'retain_until', 'revoked_at', 'checked_at', mode='before')
    @classmethod
    def rpc_timestamp_strings(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def current_unverified(self):
        if self.bytes_verified or self.legal_review_approved or self.execution_authorized or not self.available_at(self.checked_at):
            raise ValueError('Current unverified registry state required')
        return self

    def descriptor(self):
        return ContractDocumentArtifact.model_validate({key: getattr(self,key) for key in ContractDocumentArtifact.model_fields})
