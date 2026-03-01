"""Compliance & Logging Agent — TCPA, DNC, audit trail, ethical gating."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from config.prompts import SystemPrompts
from config.settings import settings
from schemas.compliance import AuditLogEntry, ComplianceCheck, ComplianceFlag, ComplianceStatus
from schemas.outreach import OutreachMessage, OutreachStatus
from schemas.property import PropertyLead
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ComplianceLoggingAgent(BaseAgent):
    name = "compliance_logging_agent"
    system_prompt = SystemPrompts.COMPLIANCE_LOGGING

    def __init__(self) -> None:
        super().__init__()
        self._audit_log: list[AuditLogEntry] = []

    # ── Outreach pre-flight checks ────────────────────────────────────────────

    def check_outreach(
        self,
        message: OutreachMessage,
        lead: PropertyLead,
        existing_attempt_count: int,
    ) -> ComplianceCheck:
        """
        Run all compliance checks before allowing a message to be sent.
        Returns a ComplianceCheck; if not clear, caller must halt.
        """
        flags: dict[ComplianceFlag, str] = {}

        # 1. Max attempts check
        if existing_attempt_count >= settings.max_outreach_attempts:
            flags[ComplianceFlag.MAX_ATTEMPTS_EXCEEDED] = (
                f"Attempt {existing_attempt_count + 1} exceeds "
                f"max {settings.max_outreach_attempts}"
            )

        # 2. TCPA quiet hours check (UTC approximation; real impl needs tz lookup)
        if settings.dnc_check_enabled:
            now_hour = datetime.now(tz=timezone.utc).hour
            qh_start = settings.tcpa_quiet_hours_start
            qh_end = settings.tcpa_quiet_hours_end
            if qh_start > qh_end:  # overnight window (e.g. 21–8)
                in_quiet = now_hour >= qh_start or now_hour < qh_end
            else:
                in_quiet = qh_start <= now_hour < qh_end
            if in_quiet:
                flags[ComplianceFlag.TCPA_QUIET_HOURS] = (
                    f"Current UTC hour {now_hour} is within quiet window "
                    f"{qh_start}–{qh_end}"
                )

        # 3. Phone validation (basic)
        if not lead.phone_numbers:
            flags[ComplianceFlag.INVALID_PHONE] = "No phone number on file"

        # 4. Message pre-cleared by outreach agent?
        if not message.compliance_cleared:
            flags[ComplianceFlag.HIGH_PRESSURE_LANGUAGE] = (
                "Message not cleared by outreach agent"
            )

        status = (
            ComplianceStatus.CLEARED
            if not flags
            else ComplianceStatus.BLOCKED
            if any(
                f in flags
                for f in [
                    ComplianceFlag.MAX_ATTEMPTS_EXCEEDED,
                    ComplianceFlag.TCPA_QUIET_HOURS,
                    ComplianceFlag.HIGH_PRESSURE_LANGUAGE,
                ]
            )
            else ComplianceStatus.FLAGGED
        )

        check = ComplianceCheck(
            entity_id=message.id,
            entity_type="outreach",
            status=status,
            flags=list(flags.keys()),
            flag_details={f.value: detail for f, detail in flags.items()},
            auto_halted=status == ComplianceStatus.BLOCKED,
        )

        self.log_action(
            agent=self.name,
            action="outreach_compliance_check",
            entity_id=message.id,
            entity_type="outreach",
            input_summary=f"lead={lead.id}, attempt={existing_attempt_count + 1}",
            output_summary=f"status={status.value}, flags={[f.value for f in check.flags]}",
            status=status.value,
        )

        if check.auto_halted:
            logger.warning(
                f"[{self.name}] Outreach BLOCKED for lead {lead.id}: "
                f"{[f.value for f in check.flags]}"
            )

        return check

    def review_message_tone(self, message_body: str) -> ComplianceCheck:
        """Use Claude to review a draft message for tone compliance."""
        from uuid import uuid4

        prompt = f"""
Review this outreach message draft for compliance with ethical seller communication standards.

Message:
---
{message_body}
---

Check for:
- High-pressure language
- False urgency ("act now", "expires", "limited time")
- Misleading claims
- Harassment-adjacent tone

Return:
- compliance_status: "cleared" | "flagged" | "blocked"
- flags: list of violation types found (use: high_pressure_language, false_urgency, missing_required_data)
- flag_details: dict explaining each flag
- entity_id: "draft"
- entity_type: "message_draft"
- auto_halted: true if blocked
"""
        check = self._call_structured(prompt, ComplianceCheck)
        check.entity_id = uuid4()
        return check

    # ── Audit logging ─────────────────────────────────────────────────────────

    def log_action(
        self,
        agent: str,
        action: str,
        entity_id: Optional[UUID] = None,
        entity_type: str = "",
        input_summary: str = "",
        output_summary: str = "",
        status: str = "success",
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            agent=agent,
            action=action,
            entity_id=entity_id,
            entity_type=entity_type,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            metadata=metadata or {},
        )
        self._audit_log.append(entry)
        logger.info(
            f"[AUDIT] {entry.timestamp.isoformat()} | {agent} | {action} | "
            f"{entity_type}={entity_id} | {status}"
        )
        return entry

    def export_audit_log(self) -> list[dict[str, Any]]:
        """Return the full audit log as a list of dicts (for persistence)."""
        return [entry.model_dump(mode="json") for entry in self._audit_log]

    def get_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def run(self, *args: Any, **kwargs: Any) -> list[AuditLogEntry]:
        """Return current audit log."""
        return self.get_log()
