"""Bounded WARM-lead SMS delivery with current database eligibility checks."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from string import Formatter
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from tools.crm import get_supabase_client
from tools.sms_client import SMSClient
from tools.facebook_consent import normalize_us_phone
from schemas.outreach import OutreachMessage, OutreachChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


class BulkSMSRequest(BaseModel):
    request_id: UUID
    lead_ids: list[UUID] = Field(min_length=1, max_length=25)
    template: str = Field(
        default="Hi {first_name}, this is Hilltop Home Co following up on your property inquiry at {address}. Would you like Julio to follow up? Reply STOP to opt out.",
        min_length=1, max_length=1600,
    )

    @field_validator("template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        try:
            for _, field, spec, conversion in Formatter().parse(value):
                if field is not None and (field not in {"first_name", "address"} or spec or conversion):
                    raise ValueError("Only {first_name} and {address} placeholders are supported.")
        except ValueError as exc:
            raise ValueError("Use a valid SMS template with only {first_name} and {address} placeholders.") from exc
        return value


def _contact_suppressed(sb, phone: str, lead_id: str | None = None) -> bool:
    """Check the shared suppression registry before sending; query errors fail closed."""
    if lead_id and (sb.table("dnc_registry").select("id").eq("lead_id", lead_id).limit(1).execute().data):
        return True
    digits = re.sub(r"\D", "", phone)
    variants = {phone.strip(), digits, f"+{digits}"}
    if len(digits) == 10:
        variants.update({f"1{digits}", f"+1{digits}"})
    elif len(digits) == 11 and digits.startswith("1"):
        variants.add(digits[1:])
    return bool(sb.table("dnc_registry").select("id").in_("phone_number", list(variants)).limit(1).execute().data)


@router.post("/bulk-sms-warm")
async def bulk_sms_warm(body: BulkSMSRequest) -> dict:
    """Send a selected batch before responding, so failures cannot look queued."""
    return await run_in_threadpool(_process_bulk_sms, body)


def _process_bulk_sms(body: BulkSMSRequest) -> dict:
    sb = get_supabase_client()
    if sb is None:
        raise HTTPException(503, "Database not configured")
    sms = SMSClient()
    lead_ids = list(dict.fromkeys(str(value) for value in body.lead_ids))
    counts = {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "dry_run_count": 0,
              "log_failed_count": 0, "unknown_count": 0, "already_recorded_count": 0}

    for lead_id in lead_ids:
        delivery_recorded = False
        submission_started = False
        try:
            lead = (sb.table("leads").select("id,owner_first_name,property_address,owner_phone_1,status,dnc,ai_calling_paused")
                    .eq("id", lead_id).single().execute().data or {})
            phone = lead.get("owner_phone_1") or ""
            if (not phone or lead.get("dnc") or lead.get("ai_calling_paused")
                    or lead.get("status") in {"dead", "dnc", "closed", "under_contract", "hot", "cold", "qualified_hot", "qualified_cold"}):
                counts["skipped_count"] += 1
                continue
            # The WARM screen can contain an older qualification. Re-read the
            # newest result before acting on its displayed selection.
            qualifications = (sb.table("qualification_results").select("classification")
                              .eq("lead_id", lead_id).order("created_at", desc=True).limit(1).execute().data or [])
            is_warm = (qualifications[0].get("classification") == "WARM" if qualifications
                       else lead.get("status") in {"warm", "qualified_warm"})
            if not is_warm or _contact_suppressed(sb, phone, lead_id):
                counts["skipped_count"] += 1
                continue
            text = body.template.format(
                first_name=lead.get("owner_first_name") or "there",
                address=lead.get("property_address") or "your property",
            )
            if "hilltop home co" not in text.lower():
                text = "Hilltop Home Co: " + text
            if not re.search(r"reply\s+stop\b", text, re.IGNORECASE):
                text += " Reply STOP to opt out."
            phone = normalize_us_phone(phone)
            message_id = str(uuid5(body.request_id, f"warm-sms:{lead_id}"))
            previous = sb.table("sms_events").select("*").eq("id", message_id).limit(1).execute().data
            if previous:
                receipt = previous[0]
                if (receipt.get("provider") != "twilio" or receipt.get("direction") != "outbound"
                        or str(receipt.get("lead_id")) != lead_id or receipt.get("phone_number") != phone
                        or receipt.get("body") != text):
                    counts["failed_count"] += 1  # A reference may not be reused for changed content/recipient.
                elif receipt.get("status") in {"accepted", "queued", "sending", "sent", "delivered", "read"}:
                    counts["sent_count"] += 1
                    counts["already_recorded_count"] += 1
                elif receipt.get("status") in {"failed", "undelivered", "canceled"}:
                    counts["failed_count"] += 1
                    counts["already_recorded_count"] += 1
                else:
                    counts["unknown_count"] += 1
                continue
            # A new campaign reference must not bypass an ambiguous older request,
            # including an attempt for another CRM lead sharing this phone.
            unresolved = sb.table("sms_events").select("id").eq("provider", "twilio").eq(
                "direction", "outbound").eq("phone_number", phone).in_(
                "status", ["submitting", "unknown"]).limit(1).execute().data
            if unresolved:
                counts["unknown_count"] += 1
                continue
            message = OutreachMessage(
                id=message_id, lead_id=lead_id, channel=OutreachChannel.SMS, body=text,
                compliance_cleared=True,
            )
            submission_started = True
            sent = sms.send(message, phone)
            if not sent:
                receipts = sb.table("sms_events").select("status").eq("id", message_id).limit(1).execute().data
                if receipts and receipts[0].get("status") in {"submitting", "unknown"}:
                    counts["unknown_count"] += 1
                    continue
                if receipts and receipts[0].get("status") in {"accepted", "queued", "sending", "sent", "delivered", "read"}:
                    counts["sent_count"] += 1
                    counts["already_recorded_count"] += 1
                    continue
            status = "dry_run" if sent and message.a2p_provider.endswith(":dry-run") else "sent" if sent else "failed"
            counts[f"{status}_count"] += 1
            delivery_recorded = True
            sb.table("outreach_activity").insert({
                "lead_id": lead_id, "channel": "sms", "direction": "outbound",
                "status": status, "message": text,
            }).execute()
            if status == "sent":
                sb.table("leads").update({"last_contact_date": datetime.now(timezone.utc).date().isoformat()}).eq("id", lead_id).execute()
        except Exception:
            counts["log_failed_count" if delivery_recorded else "unknown_count" if submission_started else "failed_count"] += 1
            logger.exception("WARM SMS failed for lead %s", lead_id)

    return {
        "status": "partial" if counts["failed_count"] or counts["log_failed_count"] or counts["unknown_count"] else "complete",
        "request_id": str(body.request_id),
        "target_count": len(lead_ids), "processed_count": len(lead_ids), **counts,
    }
