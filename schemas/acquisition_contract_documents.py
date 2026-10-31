"""Internal version-bound descriptors; never caller authorization or legal review."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictBool, field_validator, model_validator
from schemas.acquisition_evidence_object import MAX_EVIDENCE_BYTES
from schemas.acquisition_evidence_object import RetainedEvidenceObject
from schemas.acquisition_evidence import EvidenceRegistration, EvidenceRegistrationReceipt, UploadCapacityAdmission


DocumentPurpose = Literal['purchase_contract', 'title_report', 'assignment_agreement',
                          'seller_disclosure', 'assignee_disclosure', 'closing_statement', 'supporting_document']


class ContractDocumentRegistration(EvidenceRegistration):
    purpose: DocumentPurpose


class ContractDocumentRegistrationReceipt(EvidenceRegistrationReceipt):
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)


class ContractDocumentArtifact(RetainedEvidenceObject):
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    # Classification alone never proves signature, title, disclosure or legal sufficiency.
    purpose: DocumentPurpose


class ContractDocumentState(ContractDocumentArtifact):
    """Current scoped metadata, including unavailable historical documents."""
    id: UUID = Field(validation_alias='artifact_id')
    sha256: str = Field(validation_alias='expected_sha256', pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(validation_alias='expected_byte_size', strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    retention_policy_id: UUID
    status: Literal['pending_verification', 'revoked', 'expired', 'policy_review_required']
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
        if self.bytes_verified or self.legal_review_approved or self.execution_authorized:
            raise ValueError('Current unverified registry state required')
        if self.checked_at < self.created_at:
            raise ValueError('State cannot precede document creation')
        if self.status == 'revoked':
            if self.revoked_at is None or self.revoked_at > self.checked_at:
                raise ValueError('Current revocation required')
        elif self.revoked_at is not None:
            raise ValueError('Revocation takes precedence')
        elif self.status == 'expired':
            if self.retain_until > self.checked_at:
                raise ValueError('Retention has not expired')
        elif self.retain_until <= self.checked_at:
            raise ValueError('Expired retention takes precedence')
        return self

    def descriptor(self):
        return ContractDocumentArtifact.model_validate({key: getattr(self,key) for key in ContractDocumentArtifact.model_fields})


class ContractDocumentRegistryState(ContractDocumentState):
    """Only current unverified metadata may enter the byte-observation transport."""
    status: Literal['pending_verification']


class ContractDocumentUploadAdmission(UploadCapacityAdmission):
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    purpose: DocumentPurpose


class ContractDocumentUploadReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['stored_unverified']
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    artifact_id: UUID
    purpose: DocumentPurpose
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    media_type: Literal['application/pdf', 'image/png', 'image/jpeg', 'text/plain']
    retention_policy_id: UUID
    checked_at: AwareDatetime
    registry_checked_at: AwareDatetime
    retain_until: AwareDatetime
    verifier_version: Literal['acquisition-contract-document-bytes-v1']
    registry_verifier_version: Literal['acquisition-contract-document-registry-v1']
    upload_version: Literal['acquisition-contract-document-upload-v1']
    write_outcome: Literal['stored_or_existing']
    scan_status: Literal['not_scanned']
    byte_match_observed: StrictBool
    verification_persisted: StrictBool
    legal_review_approved: StrictBool
    execution_authorized: StrictBool

    @field_validator('checked_at', 'registry_checked_at', 'retain_until', mode='before')
    @classmethod
    def timestamp_strings(cls, value):
        if not isinstance(value, str):
            raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def observed_bytes_are_not_approval(self):
        if not self.byte_match_observed or self.verification_persisted or self.legal_review_approved or self.execution_authorized:
            raise ValueError('Unpersisted byte observation without approval required')
        if (self.retain_until <= max(self.checked_at, self.registry_checked_at)
                or (self.checked_at-self.registry_checked_at).total_seconds()>5):
            raise ValueError('Current retained evidence required')
        return self
