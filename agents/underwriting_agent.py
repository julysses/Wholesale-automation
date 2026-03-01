"""Underwriting Agent — conservative financial analysis for each deal."""

from __future__ import annotations

import logging
from uuid import UUID

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from schemas.deal import ARVRange, DealStrategy, RehabRange, UnderwritingReport
from schemas.property import PropertyLead
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class UnderwritingInput(BaseModel):
    lead_id: str
    address: str
    city: str
    state: str = "TX"
    zip_code: str
    beds: int = 0
    baths: float = 0.0
    sqft: int = 0
    year_built: int = 0
    lot_size_sqft: int = 0
    property_type: str = "single_family"
    condition_notes: str = ""
    tax_assessed_value: float = 0.0
    owner_equity_estimate_pct: float = 0.0
    comp_data: list[dict] = Field(default_factory=list)  # comps if available
    additional_notes: str = ""


class UnderwritingAgent(BaseAgent):
    name = "underwriting_agent"
    system_prompt = SystemPrompts.UNDERWRITING

    def underwrite(
        self, lead: PropertyLead, uw_input: UnderwritingInput
    ) -> UnderwritingReport:
        """Run conservative underwriting on a property lead."""
        prompt = f"""
Underwrite this Texas property conservatively.

Property details:
- Address: {uw_input.address}, {uw_input.city}, TX {uw_input.zip_code}
- Type: {uw_input.property_type}
- Beds/Baths: {uw_input.beds}/{uw_input.baths}
- Sqft: {uw_input.sqft}
- Year Built: {uw_input.year_built}
- Lot size: {uw_input.lot_size_sqft} sqft
- Condition notes: {uw_input.condition_notes}
- Tax assessed value: ${uw_input.tax_assessed_value:,.0f}
- Estimated owner equity: {uw_input.owner_equity_estimate_pct:.0%}
- Available comps: {uw_input.comp_data if uw_input.comp_data else "None provided — use market knowledge"}
- Additional notes: {uw_input.additional_notes}

Instructions:
- Produce ARV low/mid/high range
- Produce rehab low/mid/high range
- Calculate MAO = (ARV_low × 0.70) − Rehab_high
- Choose strategy: wholesale | wholetail | close_and_rehab | too_risky
- If deal is weak, list specific reasons in weak_deal_reasons
- comp_count = number of comps used (0 if none)
- Return lead_id as "{lead.id}"
- address_full as "{uw_input.address}, {uw_input.city}, TX {uw_input.zip_code}"
"""
        report = self._call_structured(prompt, UnderwritingReport)
        report.lead_id = lead.id

        # Recalculate MAO deterministically
        report.mao = UnderwritingReport.calculate_mao(
            report.arv.low, report.rehab.high
        )

        logger.info(
            f"[{self.name}] Lead {lead.id} underwritten: "
            f"ARV={report.arv.low}–{report.arv.high}, "
            f"MAO={report.mao}, "
            f"strategy={report.strategy.value}"
        )
        return report

    def run(
        self, leads_with_inputs: list[tuple[PropertyLead, UnderwritingInput]]
    ) -> list[UnderwritingReport]:
        """Underwrite multiple leads. Skip and log failures."""
        reports: list[UnderwritingReport] = []
        for lead, uw_input in leads_with_inputs:
            try:
                report = self.underwrite(lead, uw_input)
                if report.strategy != DealStrategy.TOO_RISKY:
                    reports.append(report)
                else:
                    logger.info(
                        f"[{self.name}] Lead {lead.id} marked too_risky: "
                        f"{report.weak_deal_reasons}"
                    )
            except Exception as exc:
                logger.error(f"[{self.name}] Underwriting failed for {lead.id}: {exc}")
        return reports
