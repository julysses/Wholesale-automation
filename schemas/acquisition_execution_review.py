"""Sourced execution findings, not trusted facts or authorization.

This boundary is not mounted until persistence can resolve every referenced original
under the current workspace, version, scanner and reviewer policy locks.
"""
from typing import Literal
from pydantic import Field, model_validator

from schemas.acquisition_contract_reviews import ContractReviewRequest, Exact
from schemas.acquisition_contract_terms import ContractTermsDraft


class ExecutionFinding(Exact):
    finding: Literal['confirmed', 'not_confirmed', 'unknown']
    locator: str = Field(strict=True, min_length=1, max_length=1000)
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @model_validator(mode='after')
    def substantive_source(self):
        # Keep exact text for request identity; reject invisible/empty citations.
        if (not self.locator.strip() or any(ord(c) < 32 for c in self.locator)
                or len(self.note.strip()) < 20 or '\x00' in self.note):
            raise ValueError('Document the source and finding without inferring confirmation')
        return self


class ExecutionFindings(Exact):
    """All findings refer to the request's exact returned contract artifact.

Supplemental term sources retain their own immutable original identities. The
repository must resolve these before any reviewer decision can be current.
"""
    seller_signatures: ExecutionFinding
    buyer_signatures: ExecutionFinding
    signing_authority: ExecutionFinding
    complete_agreement: ExecutionFinding
    terms: ContractTermsDraft


class ExecutionReviewRequest(ContractReviewRequest):
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    findings: ExecutionFindings | None

    @model_validator(mode='after')
    def decision_findings(self):
        if self.status == 'approved':
            if self.findings is None:
                raise ValueError('Execution review requires sourced findings')
            for name in ('seller_signatures', 'buyer_signatures', 'signing_authority', 'complete_agreement'):
                if getattr(self.findings, name).finding != 'confirmed':
                    raise ValueError('Unconfirmed findings cannot support an approved execution review')
            if any(source.artifact_version > self.expected_version for source in self.findings.terms.sources):
                raise ValueError('Execution terms cannot reference a future contract version')
        elif self.findings is not None:
            raise ValueError('Withdrawal preserves the original findings without replacing them')
        return self
