"""Internal document descriptors; registry/API persistence remains required."""
from typing import Literal
from uuid import UUID
from pydantic import Field
from schemas.acquisition_evidence_object import RetainedEvidenceObject


class ContractDocumentArtifact(RetainedEvidenceObject):
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    # Classification alone never proves signature, title, disclosure or legal sufficiency.
    purpose: Literal['purchase_contract', 'title_report', 'assignment_agreement',
                     'seller_disclosure', 'assignee_disclosure', 'closing_statement', 'supporting_document']
