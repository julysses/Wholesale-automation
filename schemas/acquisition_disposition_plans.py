"""Internal purchase-path intent; no legal, marketing or closing authority."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from schemas.acquisition_contract_reviews import Exact
from schemas.acquisition_contracts import ContractStatus

PlanStatus = Literal['proposed', 'withdrawn']
ExitType = Literal['principal_acquisition', 'wholesale_assignment']


class PlanIdentity(Exact):
    status: PlanStatus
    exit_type: ExitType
    original_plan_id: UUID | None


class DispositionPlanRequest(PlanIdentity):
    id: UUID
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    expected_sequence: int = Field(strict=True, ge=0, le=2147483646)
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('note')
    @classmethod
    def meaningful_note(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Describe the internal purchase-path intent')
        return value

    @model_validator(mode='after')
    def original_shape(self):
        if self.status == 'proposed' and self.original_plan_id is not None:
            raise ValueError('New proposal cannot impersonate withdrawal')
        if self.status == 'withdrawn' and (self.original_plan_id is None or self.original_plan_id == self.id or self.expected_sequence < 1):
            raise ValueError('Withdrawal requires the exact original proposal')
        return self


class DispositionPlanReceipt(PlanIdentity):
    plan_id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    duplicate: StrictBool
    plan_recorded: Literal[True]
    disposition_approved: Literal[False]
    execution_authorized: Literal[False]


class LatestPlan(PlanIdentity):
    plan_id: UUID
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    note: str = Field(strict=True, min_length=20, max_length=4000)
    created_at: AwareDatetime

    @field_validator('created_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Explicit original timestamp required')
        return value

    @model_validator(mode='after')
    def original_shape(self):
        DispositionPlanRequest(id=self.plan_id, expected_version=1, expected_sequence=self.sequence-1,
            status=self.status, exit_type=self.exit_type, original_plan_id=self.original_plan_id, note=self.note)
        return self


class PlanWithdrawal(Exact):
    plan_id: UUID
    exit_type: ExitType
    expected_sequence: int = Field(strict=True, ge=1, le=2147483646)


class DispositionPlanState(Exact):
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    current_version: int = Field(strict=True, ge=1, le=2147483647)
    current_status: ContractStatus
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    readiness: Literal['ready_for_planning', 'paused', 'contract_unavailable', 'history_limit_reached']
    latest: LatestPlan | None
    withdrawal: PlanWithdrawal | None
    checked_at: AwareDatetime
    disposition_approved: Literal[False]
    execution_authorized: Literal[False]

    @field_validator('checked_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        return LatestPlan.explicit_timestamp(value)

    @model_validator(mode='after')
    def consistent_context(self):
        if self.current_version < self.contract_version:
            raise ValueError('Retained contract version required')
        if (self.latest.sequence if self.latest else 0) != self.sequence:
            raise ValueError('Latest plan must match retained sequence')
        if self.latest and self.latest.created_at > self.checked_at:
            raise ValueError('Plan cannot postdate its read')
        if self.readiness == 'ready_for_planning' and (self.current_version != self.contract_version or self.current_status != 'title_review' or self.sequence == 2147483647):
            raise ValueError('Planning requires current title-review context')
        if (self.readiness == 'history_limit_reached') != (self.sequence == 2147483647):
            raise ValueError('History limit changed')
        if self.withdrawal:
            if (not self.latest or self.latest.status != 'proposed' or
                (self.withdrawal.plan_id, self.withdrawal.exit_type, self.withdrawal.expected_sequence) !=
                (self.latest.plan_id, self.latest.exit_type, self.sequence)):
                raise ValueError('Withdrawal must retain the latest original proposal')
        return self
