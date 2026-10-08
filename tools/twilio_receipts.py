"""Reconcile a verified Twilio outcome against one durable outbound claim."""
from __future__ import annotations

import re

PROGRESS = {"accepted": 0, "scheduled": 1, "queued": 2, "sending": 3, "sent": 4,
            "delivered": 5, "read": 6}
FAILURES = {"failed", "undelivered", "canceled"}
SUCCESS = {"delivered", "read"}


def reconcile_twilio_receipt(sb, reference: str, phone: str, sid: str, outcome: str) -> str:
    """CAS status and SID together; never let late API acceptance regress delivery.

    Caller must verify the provider callback signature, or supply the SID returned
    by the authenticated Twilio create request. No provider requests happen here.
    """
    if not re.fullmatch(r"SM[0-9a-fA-F]{32}", sid) or outcome not in PROGRESS.keys() | FAILURES:
        raise ValueError("Invalid Twilio outcome")
    for _ in range(3):
        rows = sb.table("sms_events").select("*").eq("id", reference).limit(1).execute().data
        if not rows:
            raise RuntimeError("Twilio outbound claim is missing")
        row = rows[0]
        if row.get("provider") != "twilio" or row.get("direction") != "outbound" or row.get("phone_number") != phone:
            raise ValueError("Twilio outcome does not match the outbound claim")
        metadata = row.get("raw_payload") or {}
        known_sid = metadata.get("provider_sid") or metadata.get("MessageSid")
        if known_sid and known_sid != sid:
            raise ValueError("Twilio SID does not match the outbound claim")
        old = row.get("status")
        conflict = metadata.get("delivery_conflict") is True or (
            old in SUCCESS and outcome in FAILURES or old in FAILURES and outcome in SUCCESS
        )
        if conflict:
            status = "unknown"  # Contradictory terminal receipts require operator review.
        elif old in FAILURES:
            status = old
        elif old in PROGRESS:
            status = outcome if outcome in FAILURES or PROGRESS[outcome] > PROGRESS[old] else old
        elif old in {"submitting", "unknown"}:
            status = outcome
        else:
            raise ValueError("Unexpected Twilio claim state")
        merged = {**metadata, "provider_sid": sid}
        if conflict:
            merged["delivery_conflict"] = True
        if old == status and merged == metadata:
            return status
        update = sb.table("sms_events").update({"status": status, "raw_payload": merged}).eq(
            "id", reference).eq("status", old).eq("provider", "twilio").eq(
            "direction", "outbound").eq("phone_number", phone)
        # The null comparison prevents two different early SIDs from both binding
        # an unbound claim, even when both report the same status.
        bound = metadata.get("provider_sid")
        update = update.eq("raw_payload->>provider_sid", bound) if bound else update.is_("raw_payload->>provider_sid", "null")
        if update.execute().data:
            return status
    raise RuntimeError("Twilio receipt changed concurrently; retry reconciliation")


def reconcile_twilio_callback(sb, payload: dict) -> tuple[str | None, str | None]:
    reference = payload.get("app_message_id")
    if not reference:
        rows = sb.table("sms_events").select("id").eq("provider", "twilio").eq(
            "direction", "outbound").eq("phone_number", payload["To"]).eq(
            "raw_payload->>provider_sid", payload["MessageSid"]).limit(2).execute().data
        if not rows:
            return None, None  # Archive unlinked events without inventing a claim.
        if len(rows) != 1:
            raise RuntimeError("Twilio SID has ambiguous outbound claims")
        reference = rows[0]["id"]
    status = reconcile_twilio_receipt(sb, reference, payload["To"], payload["MessageSid"], payload["MessageStatus"])
    return reference, status
