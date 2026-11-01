"""Project authorized repository rows into the pure lifecycle reviewer.

The caller must load and lock these rows and evidence under current authority.
This adapter does not query the database or turn client assertions into evidence.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.acquisition_contracts import ContractEvidence, ContractReviewSnapshot, ContractStatus
from schemas.acquisition_contract_terms import ContractTermsDraft
from schemas.acquisition_contract_transitions import ContractTransitionRequest


class LifecycleDeal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: UUID
    workspace_id: UUID
    acquisition_version: int = Field(strict=True, ge=1, le=2147483647)
    acquisition_sequence: int = Field(strict=True, ge=0, le=2147483647)
    acquisition_status: ContractStatus


class LifecycleTermsVersion(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    workspace_id: UUID
    deal_id: UUID
    version: int = Field(strict=True, ge=1, le=2147483647)
    terms: ContractTermsDraft | None

    @model_validator(mode='after')
    def original_or_sourced(self):
        if (self.version == 1) != (self.terms is None):
            raise ValueError('Original draft or immutable sourced terms required')
        if self.terms and any(s.artifact_version >= self.version for s in self.terms.sources):
            raise ValueError('Terms must retain a preceding original source version')
        return self


def prepare_transition_snapshot(*, workspace_id: UUID, contract_id: UUID,
                                request: ContractTransitionRequest, deal: LifecycleDeal,
                                version: LifecycleTermsVersion, now: datetime,
                                snapshot_at: datetime, evidence: tuple[ContractEvidence, ...],
                                exit_type: Literal['principal_acquisition', 'wholesale_assignment'] | None = None,
                                buyer_id: UUID | None = None) -> ContractReviewSnapshot:
    """No fallback to legacy money/dates/stage or to a historical version's status."""
    if (deal.workspace_id != workspace_id or deal.id != contract_id
            or version.workspace_id != workspace_id or version.deal_id != contract_id):
        raise ValueError('Contract snapshot scope mismatch')
    if (deal.acquisition_version != request.expected_version
            or version.version != request.expected_version
            or deal.acquisition_sequence != request.expected_sequence
            or deal.acquisition_status != request.expected_status):
        raise ValueError('Contract snapshot changed; reload before a new decision')
    if any(e.workspace_id != workspace_id or e.contract_id != contract_id for e in evidence):
        raise ValueError('Contract evidence scope mismatch')
    if len({e.id for e in evidence}) != len(evidence):
        raise ValueError('Duplicate contract evidence')
    terms = version.terms
    dates = {}
    for source, instant, calendar in (
        ('effective', 'effective_at', 'effective_date'),
        ('inspection_deadline', 'inspection_deadline', 'inspection_deadline_date'),
        ('closing_deadline', 'closing_deadline', 'closing_deadline_date'),
    ):
        term = getattr(terms, source) if terms else None
        dates[instant] = term.instant if term else None
        dates[calendar] = term.calendar_date if term else None
    return ContractReviewSnapshot(
        workspace_id=workspace_id, contract_id=contract_id,
        contract_version=version.version, status=deal.acquisition_status,
        target_status=request.target_status, now=now, snapshot_at=snapshot_at,
        assignment_allowed=terms.assignment_allowed if terms else None,
        purchase_price_cents=terms.purchase_price_cents if terms else None,
        earnest_money_cents=terms.earnest_money_cents if terms else None,
        evidence=evidence, exit_type=exit_type, buyer_id=buyer_id, **dates)
