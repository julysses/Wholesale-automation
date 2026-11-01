"""Exact original-document references; discovery never grants approval."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,StrictBool,field_validator,model_validator
from schemas.acquisition_contract_terms import Exact
from schemas.acquisition_contract_documents import DocumentPurpose


class ContractReference(Exact):
    workspace_id:UUID
    contract_id:UUID
    contract_version:int=Field(strict=True,ge=1,le=2147483647)
    artifact_id:UUID
    source_version:int=Field(strict=True,ge=1,le=2147483647)
    reference_type:Literal['native','term_source','linked']
    link_id:UUID|None
    status:Literal['reference_withdrawn','source_revoked','requires_review','available_for_review']
    purpose:DocumentPurpose
    sha256:str=Field(strict=True,pattern=r'^[0-9a-f]{64}$')
    verification_id:UUID|None
    checked_at:AwareDatetime
    review_approved:StrictBool
    execution_authorized:StrictBool

    @field_validator('checked_at',mode='before')
    @classmethod
    def explicit_stamp(cls,value):
        if not isinstance(value,str):raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def bound_source(self):
        if self.source_version>self.contract_version or (self.reference_type=='native')!=(self.source_version==self.contract_version):
            raise ValueError('Original source version must match reference type')
        if (self.reference_type=='linked')!=(self.link_id is not None):
            raise ValueError('Explicit link identity required')
        if self.status=='reference_withdrawn' and self.reference_type!='linked':raise ValueError('Only explicit links can be withdrawn')
        if (self.status=='available_for_review')!=(self.verification_id is not None):raise ValueError('Current source verification required')
        if self.review_approved or self.execution_authorized:raise ValueError('Discovery cannot approve or execute')
        return self


class ContractReferenceChoice(ContractReference):
    source_created_at:AwareDatetime

    @field_validator('source_created_at',mode='before')
    @classmethod
    def explicit_created(cls,value):
        if not isinstance(value,str):raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def original_creation(self):
        if self.source_created_at>self.checked_at:raise ValueError('Source creation cannot follow current check')
        return self


class ContractReferencePage(Exact):
    workspace_id:UUID
    contract_id:UUID
    contract_version:int=Field(strict=True,ge=1,le=2147483647)
    purpose:DocumentPurpose
    items:tuple[ContractReferenceChoice,...]=Field(max_length=50)
    next_after:UUID|None
    checked_at:AwareDatetime
    execution_authorized:StrictBool

    @field_validator('checked_at',mode='before')
    @classmethod
    def explicit_stamp(cls,value):
        if not isinstance(value,str):raise ValueError('Timestamp string required')
        return value

    @model_validator(mode='after')
    def exact_page(self):
        previous=None
        if self.execution_authorized:raise ValueError('Discovery cannot execute')
        for row in self.items:
            if (row.workspace_id,row.contract_id,row.contract_version,row.purpose,row.checked_at)!=(
                    self.workspace_id,self.contract_id,self.contract_version,self.purpose,self.checked_at) or previous is not None and row.artifact_id.int<=previous:
                raise ValueError('Reference page scope or ordering changed')
            previous=row.artifact_id.int
        if self.next_after is not None and (not self.items or self.next_after!=self.items[-1].artifact_id):
            raise ValueError('Reference cursor must be the last returned identity')
        return self
