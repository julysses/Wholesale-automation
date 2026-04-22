"""
Master Orchestrator — controls agent flow, enforces compliance gates,
and maintains the full deal pipeline from data ingestion to disposition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from agents import (
    BuyerQualificationAgent,
    BuyerSourcingAgent,
    ComplianceLoggingAgent,
    DataSourceAgent,
    DispoMatchingAgent,
    DistressScoringAgent,
    SellerOutreachAgent,
    UnderwritingAgent,
)
from agents.buyer_qualification_agent import QualificationEvent
from agents.buyer_sourcing_agent import BuyerResearchRequest
from agents.dispo_matching_agent import DispoMatchResult
from agents.distress_scoring_agent import DistressScoreResult
from agents.seller_score_agent import SellerScoreAgent, SellerScoreResult
from agents.underwriting_agent import UnderwritingInput
from config.prompts import SystemPrompts
from config.settings import settings
from schemas.buyer import BuyerProfile, BuyerQualification
from schemas.compliance import AuditLogEntry
from schemas.deal import Deal, DealStatus, UnderwritingReport
from schemas.outreach import OutreachChannel, OutreachMessage
from schemas.property import DataSource, DistressSignal, PropertyLead
from tools.batchdata_adapter import BatchDataAdapter, SkipTracePayload, SkipTraceResult
from tools.batchdialer_adapter import BatchDialerAdapter
from tools.launch_control_adapter import LaunchControlAdapter, LaunchControlContact

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """Mutable pipeline state passed across agent calls."""
    raw_leads: list[PropertyLead] = field(default_factory=list)
    scored_leads: list[tuple[PropertyLead, DistressScoreResult]] = field(default_factory=list)
    # Skip trace results keyed by lead_id
    skip_trace_results: dict[str, SkipTraceResult] = field(default_factory=dict)
    # Blueprint seller scores keyed by lead_id
    seller_scores: dict[str, SellerScoreResult] = field(default_factory=dict)
    underwriting_reports: list[UnderwritingReport] = field(default_factory=list)
    active_deals: list[Deal] = field(default_factory=list)
    outreach_messages: list[OutreachMessage] = field(default_factory=list)
    buyer_profiles: list[BuyerProfile] = field(default_factory=list)
    buyer_qualifications: list[BuyerQualification] = field(default_factory=list)
    dispo_results: list[DispoMatchResult] = field(default_factory=list)
    audit_log: list[AuditLogEntry] = field(default_factory=list)


class MasterOrchestrator:
    """
    Controls the full wholesaling pipeline.

    Pipeline steps:
    1. Data ingestion
    2. Distress scoring (threshold gate)
    3. Underwriting (viability gate)
    4. Compliance pre-check
    5. Seller outreach (draft)
    6. Buyer matching (when deal is under contract)
    """

    def __init__(self) -> None:
        # Instantiate all agents
        self.data_source = DataSourceAgent()
        self.distress_scoring = DistressScoringAgent()
        self.seller_score = SellerScoreAgent()
        self.underwriting = UnderwritingAgent()
        self.seller_outreach = SellerOutreachAgent()
        self.buyer_sourcing = BuyerSourcingAgent()
        self.buyer_qualification = BuyerQualificationAgent()
        self.dispo_matching = DispoMatchingAgent()
        self.compliance = ComplianceLoggingAgent()

        # External adapters (dry-run when API keys not configured)
        self.batchdata = BatchDataAdapter()
        self.batchdialer = BatchDialerAdapter()
        self.launch_control = LaunchControlAdapter()

        self.state = PipelineState()
        logger.info("[Orchestrator] Initialized with all agents + adapters")

    # ── Step 1: Data Ingestion ────────────────────────────────────────────────

    def ingest_leads(
        self,
        records: list[dict[str, Any]],
        source: DataSource,
    ) -> list[PropertyLead]:
        """Normalize raw records into PropertyLeads."""
        self.compliance.log_action(
            agent="orchestrator",
            action="ingest_leads_start",
            input_summary=f"source={source.value}, count={len(records)}",
        )
        leads = self.data_source.run(records, source)
        self.state.raw_leads.extend(leads)

        self.compliance.log_action(
            agent="orchestrator",
            action="ingest_leads_complete",
            output_summary=f"normalized={len(leads)} leads",
        )
        logger.info(f"[Orchestrator] Ingested {len(leads)} leads from {source.value}")
        return leads

    # ── Step 2: Distress Scoring ──────────────────────────────────────────────

    def score_leads(
        self, leads: Optional[list[PropertyLead]] = None
    ) -> list[tuple[PropertyLead, DistressScoreResult]]:
        """Score leads and return those above the distress threshold."""
        if leads is None:
            leads = self.state.raw_leads

        self.compliance.log_action(
            agent="orchestrator",
            action="distress_scoring_start",
            input_summary=f"count={len(leads)}",
        )

        passing = self.distress_scoring.run(leads)
        self.state.scored_leads.extend(passing)

        self.compliance.log_action(
            agent="orchestrator",
            action="distress_scoring_complete",
            output_summary=f"passed={len(passing)}/{len(leads)}",
        )
        logger.info(f"[Orchestrator] {len(passing)}/{len(leads)} leads passed distress threshold")
        return passing

    # ── Step 2b: Skip Trace ───────────────────────────────────────────────────

    def skip_trace_leads(
        self,
        leads: Optional[list[PropertyLead]] = None,
    ) -> dict[str, SkipTraceResult]:
        """
        Skip trace all leads via BatchData.
        Enriches phone numbers and emails; updates phone_numbers on the lead.
        Returns a dict of lead_id → SkipTraceResult.
        """
        if leads is None:
            leads = self.state.raw_leads

        self.compliance.log_action(
            agent="orchestrator",
            action="skip_trace_start",
            input_summary=f"count={len(leads)}",
        )

        results: dict[str, SkipTraceResult] = {}
        for lead in leads:
            payload = SkipTracePayload(
                owner_name=lead.owner_name,
                property_address=lead.address.street,
                city=lead.address.city,
                state=lead.address.state,
                zip_code=lead.address.zip_code,
            )
            result = self.batchdata.skip_trace_property(payload, lead_id=str(lead.id))
            results[str(lead.id)] = result

            # Enrich lead phone list with skip-trace results
            if result.phones:
                enriched = [p.number for p in result.phones if p.number]
                # Merge with existing phones (deduplicate)
                existing = set(lead.phone_numbers)
                lead.phone_numbers = list(existing | set(enriched))

        self.state.skip_trace_results.update(results)
        enriched_count = sum(1 for r in results.values() if r.phones)

        self.compliance.log_action(
            agent="orchestrator",
            action="skip_trace_complete",
            output_summary=f"enriched={enriched_count}/{len(leads)}",
        )
        logger.info(
            f"[Orchestrator] Skip trace complete — "
            f"{enriched_count}/{len(leads)} leads enriched with phone data"
        )
        return results

    # ── Step 2c: Seller Scoring (blueprint formula) ───────────────────────────

    def apply_seller_scores(
        self,
        leads: Optional[list[PropertyLead]] = None,
    ) -> dict[str, SellerScoreResult]:
        """
        Apply the blueprint additive scoring formula to all leads.
        Returns a dict of lead_id → SellerScoreResult with tier (A/B/C/D).
        """
        if leads is None:
            leads = self.state.raw_leads

        self.compliance.log_action(
            agent="orchestrator",
            action="seller_scoring_start",
            input_summary=f"count={len(leads)}",
        )

        results: dict[str, SellerScoreResult] = {}
        for lead in leads:
            result = self.seller_score.score_property_lead(lead)
            results[str(lead.id)] = result

        self.state.seller_scores.update(results)
        tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for r in results.values():
            tier_counts[r.priority_tier] += 1

        self.compliance.log_action(
            agent="orchestrator",
            action="seller_scoring_complete",
            output_summary=(
                f"A={tier_counts['A']} B={tier_counts['B']} "
                f"C={tier_counts['C']} D={tier_counts['D']}"
            ),
        )
        logger.info(f"[Orchestrator] Seller scores: {tier_counts}")
        return results

    # ── Step 2d: Route leads to dialer / SMS / suppress ───────────────────────

    async def route_leads(
        self,
        leads: Optional[list[PropertyLead]] = None,
        dialer_campaign_id: str = "",
    ) -> dict[str, list[PropertyLead]]:
        """
        Route scored leads:
          A/B → BatchDialer (if auto_push_to_dialer=True)
          C   → Launch Control SMS nurture (if auto_enroll_sms_nurture=True)
          D   → suppressed

        Returns dict keyed by routing action: {"dialer": [...], "sms_nurture": [...], "suppress": [...]}
        """
        if leads is None:
            leads = self.state.raw_leads

        routed: dict[str, list[PropertyLead]] = {"dialer": [], "sms_nurture": [], "suppress": []}
        campaign_id = dialer_campaign_id or settings.batchdialer_default_campaign_id

        for lead in leads:
            score_result = self.state.seller_scores.get(str(lead.id))
            if not score_result:
                routed["suppress"].append(lead)
                continue

            routed[score_result.routing_action].append(lead)

            # Auto-push to BatchDialer
            if (
                score_result.routing_action == "dialer"
                and settings.auto_push_to_dialer
                and campaign_id
            ):
                skip = self.state.skip_trace_results.get(str(lead.id))
                best_phone = skip.best_phone if skip else None
                phone = best_phone.number if best_phone else (
                    lead.phone_numbers[0] if lead.phone_numbers else ""
                )
                if phone:
                    name_parts = lead.owner_name.split(" ", 1)
                    contact_id, ok = await self.batchdialer.push_lead_to_campaign(
                        lead_id=str(lead.id),
                        first_name=name_parts[0],
                        last_name=name_parts[1] if len(name_parts) > 1 else "",
                        phone=phone,
                        campaign_id=campaign_id,
                        property_address=lead.address.street,
                        city=lead.address.city,
                        state=lead.address.state,
                        zip_code=lead.address.zip_code,
                        seller_score=score_result.seller_score,
                        priority_tier=score_result.priority_tier,
                        tags=[score_result.priority_tier, lead.source.value],
                    )
                    if ok:
                        logger.info(
                            f"[Orchestrator] Pushed lead {lead.id} to BatchDialer "
                            f"contact={contact_id} campaign={campaign_id}"
                        )

            # Auto-enroll in Launch Control SMS
            elif (
                score_result.routing_action == "sms_nurture"
                and settings.auto_enroll_sms_nurture
            ):
                skip = self.state.skip_trace_results.get(str(lead.id))
                best_phone = skip.best_phone if skip else None
                phone = best_phone.number if best_phone else (
                    lead.phone_numbers[0] if lead.phone_numbers else ""
                )
                if phone and not lead.flagged:
                    name_parts = lead.owner_name.split(" ", 1)
                    contact = LaunchControlContact(
                        lead_id=str(lead.id),
                        first_name=name_parts[0],
                        phone=phone,
                        property_address=lead.address.street,
                        city=lead.address.city,
                        state=lead.address.state,
                        zip_code=lead.address.zip_code,
                        campaign_name=settings.launch_control_default_campaign,
                        seller_score=score_result.seller_score,
                        priority_tier=score_result.priority_tier,
                    )
                    ok = await self.launch_control.add_contact_to_campaign(contact)
                    if ok:
                        logger.info(
                            f"[Orchestrator] Enrolled lead {lead.id} in "
                            f"Launch Control SMS campaign"
                        )

        logger.info(
            f"[Orchestrator] Routing complete — "
            f"dialer={len(routed['dialer'])} "
            f"sms={len(routed['sms_nurture'])} "
            f"suppress={len(routed['suppress'])}"
        )
        return routed

    # ── Step 3: Underwriting ──────────────────────────────────────────────────

    def underwrite_leads(
        self,
        scored_leads: Optional[list[tuple[PropertyLead, DistressScoreResult]]] = None,
        uw_inputs: Optional[dict[str, UnderwritingInput]] = None,
    ) -> list[UnderwritingReport]:
        """
        Underwrite leads that passed distress scoring.
        uw_inputs: dict mapping lead_id str → UnderwritingInput (optional extra data)
        """
        if scored_leads is None:
            scored_leads = self.state.scored_leads

        uw_inputs = uw_inputs or {}
        pairs: list[tuple[PropertyLead, UnderwritingInput]] = []

        for lead, score_result in scored_leads:
            uw_in = uw_inputs.get(str(lead.id)) or UnderwritingInput(
                lead_id=str(lead.id),
                address=lead.address.street,
                city=lead.address.city,
                zip_code=lead.address.zip_code,
                tax_assessed_value=lead.assessed_value or 0.0,
                owner_equity_estimate_pct=lead.estimated_equity_pct or 0.0,
                additional_notes=f"Distress score: {score_result.score}. "
                                 f"Signals: {score_result.signals_present}",
            )
            pairs.append((lead, uw_in))

        self.compliance.log_action(
            agent="orchestrator",
            action="underwriting_start",
            input_summary=f"count={len(pairs)}",
        )

        reports = self.underwriting.run(pairs)
        self.state.underwriting_reports.extend(reports)

        # Create Deal records for viable properties
        for report in reports:
            deal = Deal(lead_id=report.lead_id, underwriting_id=report.id)
            self.state.active_deals.append(deal)

        self.compliance.log_action(
            agent="orchestrator",
            action="underwriting_complete",
            output_summary=f"viable_deals={len(reports)}",
        )
        logger.info(f"[Orchestrator] {len(reports)} viable deals after underwriting")
        return reports

    # ── Step 4 + 5: Compliance Gate + Seller Outreach ────────────────────────

    def prepare_outreach(
        self,
        leads: Optional[list[PropertyLead]] = None,
        channel: OutreachChannel = OutreachChannel.SMS,
    ) -> list[OutreachMessage]:
        """
        Draft outreach messages for leads that passed underwriting.
        Each message goes through compliance pre-check before being cleared.
        """
        if leads is None:
            # Build from deals that match scored leads
            lead_ids = {str(r.lead_id) for r in self.state.underwriting_reports}
            leads = [
                lead
                for lead, _ in self.state.scored_leads
                if str(lead.id) in lead_ids
            ]

        cleared_messages: list[OutreachMessage] = []

        for lead in leads:
            # Count prior outreach attempts for this lead
            prior_attempts = sum(
                1 for m in self.state.outreach_messages if m.lead_id == lead.id
            )

            # Draft the message
            if channel == OutreachChannel.SMS:
                msg = self.seller_outreach.draft_sms(lead, attempt_number=prior_attempts + 1)
            else:
                msg = self.seller_outreach.draft_email(lead, attempt_number=prior_attempts + 1)

            # Compliance gate
            check = self.compliance.check_outreach(msg, lead, prior_attempts)

            if check.is_clear:
                cleared_messages.append(msg)
                self.state.outreach_messages.append(msg)
            else:
                logger.warning(
                    f"[Orchestrator] Outreach blocked for lead {lead.id}: "
                    f"{[f.value for f in check.flags]}"
                )

        logger.info(
            f"[Orchestrator] {len(cleared_messages)}/{len(leads)} messages cleared for outreach"
        )
        return cleared_messages

    # ── Buyer Pipeline ────────────────────────────────────────────────────────

    def add_buyers(
        self, requests: list[BuyerResearchRequest]
    ) -> list[tuple[BuyerProfile, BuyerQualification]]:
        """Source and qualify new buyers."""
        self.compliance.log_action(
            agent="orchestrator",
            action="buyer_sourcing_start",
            input_summary=f"requests={len(requests)}",
        )

        profiles = self.buyer_sourcing.run(requests)
        qualifications = self.buyer_qualification.run(profiles)

        self.state.buyer_profiles.extend(profiles)
        self.state.buyer_qualifications.extend(qualifications)

        pairs = list(zip(profiles, qualifications))

        self.compliance.log_action(
            agent="orchestrator",
            action="buyer_sourcing_complete",
            output_summary=f"buyers_added={len(pairs)}",
        )
        return pairs

    def update_buyer_event(
        self, buyer_id: UUID, event: QualificationEvent
    ) -> Optional[BuyerQualification]:
        """Apply a qualification event (ghost/lowball/close) to a buyer."""
        qual = next(
            (q for q in self.state.buyer_qualifications if q.buyer_id == buyer_id),
            None,
        )
        if qual is None:
            logger.warning(f"[Orchestrator] Buyer {buyer_id} not found in qualifications")
            return None

        updated = self.buyer_qualification.update_qualification(qual, event)
        self.compliance.log_action(
            agent="orchestrator",
            action="buyer_qualification_update",
            entity_id=buyer_id,
            entity_type="buyer",
            input_summary=f"event={event.event_type}",
            output_summary=f"new_score={updated.reliability_score:.0f}",
        )
        return updated

    # ── Disposition ───────────────────────────────────────────────────────────

    def run_disposition(
        self,
        deals: Optional[list[Deal]] = None,
        reports: Optional[list[UnderwritingReport]] = None,
    ) -> list[DispoMatchResult]:
        """Match active deals to the qualified buyer pool."""
        if deals is None:
            deals = self.state.active_deals
        if reports is None:
            reports = self.state.underwriting_reports

        # Build deal → report map
        report_map = {r.lead_id: r for r in reports}
        deal_report_pairs = [
            (deal, report_map[deal.lead_id])
            for deal in deals
            if deal.lead_id in report_map
        ]

        buyers = list(zip(self.state.buyer_profiles, self.state.buyer_qualifications))

        self.compliance.log_action(
            agent="orchestrator",
            action="dispo_matching_start",
            input_summary=f"deals={len(deal_report_pairs)}, buyers={len(buyers)}",
        )

        results = self.dispo_matching.run(deal_report_pairs, buyers)
        self.state.dispo_results.extend(results)

        self.compliance.log_action(
            agent="orchestrator",
            action="dispo_matching_complete",
            output_summary=f"matches_produced={len(results)}",
        )
        return results

    # ── Full Pipeline ─────────────────────────────────────────────────────────

    async def run_full_pipeline(
        self,
        raw_records: list[dict[str, Any]],
        source: DataSource,
        buyer_requests: Optional[list[BuyerResearchRequest]] = None,
    ) -> PipelineState:
        """
        Execute the complete pipeline end-to-end.
        Returns the final PipelineState.
        """
        logger.info("[Orchestrator] Starting full pipeline run")

        # 1. Ingest
        leads = self.ingest_leads(raw_records, source)
        if not leads:
            logger.warning("[Orchestrator] No clean leads after ingestion — stopping")
            return self.state

        # 2. Score (distress-based filter gate)
        scored = self.score_leads(leads)
        if not scored:
            logger.warning("[Orchestrator] No leads passed distress threshold — stopping")
            return self.state

        # 2b. Skip trace (enrich phone/email)
        if settings.auto_skip_trace:
            self.skip_trace_leads(leads)

        # 2c. Apply blueprint seller score + A/B/C/D tiers
        self.apply_seller_scores(leads)

        # 2d. Route to dialer / SMS / suppress
        await self.route_leads(leads)

        # 3. Underwrite
        reports = self.underwrite_leads(scored)
        if not reports:
            logger.warning("[Orchestrator] No viable deals after underwriting — stopping")
            return self.state

        # 4+5. Compliance gate + Outreach drafts
        _ = self.prepare_outreach()

        # 6. Buyer pipeline (if requests provided)
        if buyer_requests:
            self.add_buyers(buyer_requests)

        # 7. Disposition matching (if we have buyers)
        if self.state.buyer_profiles:
            self.run_disposition()

        logger.info(
            f"[Orchestrator] Pipeline complete — "
            f"leads={len(leads)}, "
            f"viable_deals={len(reports)}, "
            f"dispo_results={len(self.state.dispo_results)}"
        )
        return self.state

    def export_audit_log(self) -> list[dict[str, Any]]:
        """Return the full immutable audit log."""
        return self.compliance.export_audit_log()
