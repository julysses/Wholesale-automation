"""Lifecycle command and read-only discovery boundaries; authority is enforced in SQL.

Version identifies immutable terms; sequence identifies lifecycle history. Evidence,
actor, policy, buyer and closing structure must be loaded from authorized storage.
"""
from uuid import UUID
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

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


# Choices describe a fresh read, not permission to execute the transition later.
class PendingSignatureChoice(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    expected_status: Literal['draft']
    target_status: Literal['pending_signature']
    signature_review_id: UUID
    expires_at: AwareDatetime

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit expiry timestamp required')
        return value


class ExecutedContractChoice(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=0, lt=2147483647)
    expected_status: Literal['pending_signature']
    target_status: Literal['executed']
    execution_review_id: UUID
    expires_at: AwareDatetime

    @field_validator('expires_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit expiry timestamp required')
        return value


class TitleReviewChoice(ExecutedContractChoice):
    expected_status: Literal['executed']
    target_status: Literal['title_review']


class ContractTransitionChoice(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    current_version: int = Field(strict=True, ge=1, le=2147483647)
    current_status: Literal['draft', 'pending_signature', 'executed', 'title_review']
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    status: Literal['version_changed', 'paused', 'awaiting_signature', 'history_requires_review',
                    'signature_review_required', 'execution_review_required', 'execution_recorded', 'title_review_required', 'title_review_started', 'ready_for_human_review']
    candidate: PendingSignatureChoice | ExecutedContractChoice | TitleReviewChoice | None
    checked_at: AwareDatetime
    execution_authorized: StrictBool

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit checked timestamp required')
        return value

    @model_validator(mode='after')
    def coherent_choice(self):
        if self.execution_authorized or self.current_version < self.contract_version:
            raise ValueError('Exact non-executing contract context required')
        if (self.status == 'version_changed') != (self.current_version != self.contract_version):
            raise ValueError('Version change must remain held')
        if (self.status == 'ready_for_human_review') != (self.candidate is not None):
            raise ValueError('Held state cannot offer a transition')
        if self.status == 'awaiting_signature' and (self.current_status != 'pending_signature' or self.sequence != 1):
            raise ValueError('Recorded lifecycle required')
        if self.status == 'execution_recorded' and (self.current_status != 'executed' or self.sequence != 2):
            raise ValueError('Recorded execution lifecycle required')
        if self.status == 'execution_review_required' and (self.current_status != 'pending_signature' or self.sequence != 1):
            raise ValueError('Awaiting-signature lifecycle required')
        if self.status in {'title_review_required', 'title_review_started'}:
            status, sequence = ('executed', 2) if self.status == 'title_review_required' else ('title_review', 3)
            if self.current_status != status or self.sequence != sequence:
                raise ValueError('Exact title-review lifecycle required')
        choice = self.candidate
        if choice and (choice.expected_version != self.contract_version or choice.expected_sequence != self.sequence
                or self.current_status != choice.expected_status
                or self.sequence != ({'pending_signature': 0, 'executed': 1, 'title_review': 2}[choice.target_status]) or choice.expires_at <= self.checked_at):
            raise ValueError('Exact current transition choice required')
        return self
