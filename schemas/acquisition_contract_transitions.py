"""Lifecycle command boundary. No endpoint or persistence authority is exposed here.

Version identifies immutable terms; sequence identifies lifecycle history. Evidence,
actor, policy, buyer and closing structure must be loaded from authorized storage.
"""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from schemas.acquisition_contracts import CONTRACT_TRANSITIONS, ContractStatus


class ContractTransitionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    expected_status: ContractStatus
    target_status: ContractStatus
    reason: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('reason')
    @classmethod
    def substantive_reason(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Document the requested lifecycle change')
        return value  # Preserve exact bytes for retry identity.

    @model_validator(mode='after')
    def permitted_edge(self):
        if self.target_status not in CONTRACT_TRANSITIONS[self.expected_status]:
            raise ValueError('Contract lifecycle transition is not permitted')
        return self


class ContractTransitionReceipt(BaseModel):
    """Historical recording confirmation, never present-tense permission to act."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    workspace_id: UUID
    contract_id: UUID
    request_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    previous_status: ContractStatus
    recorded_status: ContractStatus
    duplicate: StrictBool
    transition_recorded: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def historical_confirmation(self):
        if not self.transition_recorded or self.execution_authorized:
            raise ValueError('Non-executing historical receipt required')
        if self.recorded_status not in CONTRACT_TRANSITIONS[self.previous_status]:
            raise ValueError('Invalid recorded lifecycle edge')
        return self

    def confirms(self, request: ContractTransitionRequest, *, workspace_id: UUID,
                 contract_id: UUID) -> bool:
        return (self.workspace_id == workspace_id and self.contract_id == contract_id
                and self.request_id == request.id
                and self.contract_version == request.expected_version
                and self.sequence == request.expected_sequence + 1
                and self.previous_status == request.expected_status
                and self.recorded_status == request.target_status)
