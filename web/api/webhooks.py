"""
Inbound webhook handlers for dialer call results and SMS replies.

Routes:
  POST /webhooks/batchdialer/call
      BatchDialer fires this when a call is completed.
      Updates lead status, creates tasks for hot leads, enforces DNC.

  POST /webhooks/launch_control/reply
      Launch Control (or its Zapier bridge) fires this when a seller replies.
      Detects opt-out keywords and suppresses the lead.

  GET  /webhooks/launch_control/csv-queue
      Returns the current CSV queue for manual upload to Launch Control.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from tools.batchdialer_adapter import BatchDialerAdapter, CallResultEvent
from tools.launch_control_adapter import LaunchControlAdapter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# ── Optional webhook secret verification ──────────────────────────────────────
BATCHDIALER_WEBHOOK_SECRET = os.getenv("BATCHDIALER_WEBHOOK_SECRET", "")
LAUNCH_CONTROL_WEBHOOK_SECRET = os.getenv("LAUNCH_CONTROL_WEBHOOK_SECRET", "")

# ── Dispositions that need immediate hot-lead routing ─────────────────────────
HOT_DISPOSITIONS = {"HOT", "APPOINTMENT_SET"}


# ── Pydantic request bodies ───────────────────────────────────────────────────

class CallWebhookBody(BaseModel):
    """Accept any shape from BatchDialer — we parse it with the adapter."""
    model_config = {"extra": "allow"}


class SMSReplyBody(BaseModel):
    model_config = {"extra": "allow"}


# ── Background tasks ──────────────────────────────────────────────────────────

async def _handle_call_result(event: CallResultEvent) -> None:
    """
    Background task: persist call event + update lead status in Supabase.

    We import supabase lazily to avoid module-level failures when the
    frontend env isn't configured (e.g. running CLI-only).
    """
    try:
        from frontend.src.lib import supabase as _sb  # type: ignore[import]
    except ImportError:
        _sb = None

    logger.info(
        f"[Webhook] Call result lead={event.lead_id} "
        f"disposition={event.disposition} duration={event.duration_sec}s"
    )

    # Map call disposition to lead status
    DISPOSITION_TO_STATUS: dict[str, str] = {
        "NO_ANSWER":       "contacted",
        "VOICEMAIL":       "contacted",
        "WRONG_NUMBER":    "dead",
        "DNC":             "dnc",
        "NOT_INTERESTED":  "contacted",
        "CALLBACK":        "responding",
        "WARM":            "qualified_warm",
        "HOT":             "qualified_hot",
        "APPOINTMENT_SET": "qualified_hot",
    }
    new_status = DISPOSITION_TO_STATUS.get(event.disposition, "contacted")
    is_dnc = event.disposition == "DNC"
    is_hot = event.disposition in HOT_DISPOSITIONS

    # Persist via Supabase (server-side using service role key if available)
    supabase_url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

    if supabase_url and supabase_key and event.lead_id:
        try:
            from supabase import create_client  # type: ignore[import]
            sb = create_client(supabase_url, supabase_key)

            # 1. Insert call event
            sb.table("call_events").insert({
                "lead_id":       event.lead_id,
                "dialer":        event.dialer,
                "agent_id":      event.agent_id,
                "phone_number":  event.phone_number,
                "disposition":   event.disposition,
                "duration_sec":  event.duration_sec,
                "recording_url": event.recording_url,
                "notes":         event.notes,
                "raw_payload":   event.raw,
                "occurred_at":   event.occurred_at or datetime.now(timezone.utc).isoformat(),
            }).execute()

            # 2. Update lead status
            update_payload: dict = {
                "status":             new_status,
                "last_contact_date":  datetime.now(timezone.utc).date().isoformat(),
                "contact_attempts":   sb.rpc(  # type: ignore[assignment]
                    "increment_contact_attempts", {"lead_id": event.lead_id}
                ),
            }
            if is_dnc:
                update_payload["dnc"] = True
                update_payload["sms_sequence_active"] = False
                update_payload["email_sequence_active"] = False

            # Use a simpler update without RPC for contact_attempts
            lead_resp = sb.table("leads").select("contact_attempts").eq("id", event.lead_id).single().execute()
            current_attempts = (lead_resp.data or {}).get("contact_attempts", 0)
            sb.table("leads").update({
                "status":              new_status,
                "last_contact_date":   datetime.now(timezone.utc).date().isoformat(),
                "contact_attempts":    current_attempts + 1,
                "dnc":                 is_dnc or None,
                "sms_sequence_active": False if is_dnc else None,
            }).eq("id", event.lead_id).execute()

            # 3. Log to vendor_sync_logs
            sb.table("vendor_sync_logs").insert({
                "vendor":           "batchdialer",
                "direction":        "webhook",
                "entity_type":      "call_event",
                "entity_id":        event.lead_id,
                "status":           "success",
                "records_affected": 1,
            }).execute()

            # 4. If hot lead: create acquisition task
            if is_hot:
                sb.table("tasks").insert({
                    "lead_id":     event.lead_id,
                    "title":       f"HOT LEAD — {event.disposition.replace('_', ' ').title()}",
                    "description": (
                        f"Caller disposition: {event.disposition}\n"
                        f"Agent: {event.agent_id}\n"
                        f"Notes: {event.notes}\n"
                        f"Recording: {event.recording_url}"
                    ),
                    "priority":    "high",
                    "status":      "pending",
                    "type":        "acquisition_review",
                }).execute()

            # 5. If DNC: log to dnc_registry
            if is_dnc and event.phone_number:
                sb.table("dnc_registry").insert({
                    "phone_number": event.phone_number,
                    "lead_id":      event.lead_id,
                    "reason":       "call_disposition_dnc",
                    "source":       "batchdialer",
                }).execute()

            logger.info(f"[Webhook] Lead {event.lead_id} updated → {new_status}")

        except Exception as exc:
            logger.error(f"[Webhook] Supabase update failed: {exc}")
    else:
        logger.warning("[Webhook] Supabase not configured — call result logged only")


async def _handle_sms_reply(lead_id: str, phone: str, body: str, is_opt_out: bool) -> None:
    """Background task: persist SMS reply + enforce opt-out."""
    logger.info(
        f"[Webhook] SMS reply lead={lead_id} phone={phone} "
        f"opt_out={is_opt_out} body={body[:60]!r}"
    )

    supabase_url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

    if not (supabase_url and supabase_key):
        logger.warning("[Webhook] Supabase not configured — SMS reply logged only")
        return

    try:
        from supabase import create_client  # type: ignore[import]
        sb = create_client(supabase_url, supabase_key)

        # 1. Insert SMS event
        sb.table("sms_events").insert({
            "lead_id":      lead_id or None,
            "provider":     "launch_control",
            "direction":    "inbound",
            "phone_number": phone,
            "body":         body,
            "status":       "replied",
            "opt_out":      is_opt_out,
        }).execute()

        if is_opt_out and lead_id:
            # 2. Mark lead DNC + stop sequences
            sb.table("leads").update({
                "dnc":                  True,
                "status":               "dnc",
                "sms_sequence_active":  False,
                "email_sequence_active": False,
            }).eq("id", lead_id).execute()

            # 3. Log to dnc_registry (immutable)
            if phone:
                sb.table("dnc_registry").insert({
                    "phone_number":   phone,
                    "lead_id":        lead_id,
                    "reason":         "opt_out",
                    "source":         "sms_reply",
                    "opt_out_keyword": body[:100],
                }).execute()

            # 4. Stop Launch Control campaign
            lc = LaunchControlAdapter()
            lc.mark_opt_out(lead_id, phone, keyword=body[:50])

            logger.info(f"[Webhook] DNC applied for lead={lead_id} phone={phone}")

        elif lead_id:
            # Non-opt-out reply: move to responding
            sb.table("leads").update({"status": "responding"}).eq("id", lead_id).execute()

    except Exception as exc:
        logger.error(f"[Webhook] SMS reply processing failed: {exc}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/batchdialer/call")
async def batchdialer_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
) -> dict:
    """
    Receive a call completion event from BatchDialer.
    Responds immediately with 200 so BatchDialer doesn't retry.
    All processing happens in the background.
    """
    if BATCHDIALER_WEBHOOK_SECRET and x_webhook_secret != BATCHDIALER_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid webhook secret")

    payload = await request.json()

    # Save raw payload to audit table asap (best-effort — non-blocking)
    logger.debug(f"[Webhook] BatchDialer raw payload: {str(payload)[:200]}")

    event = BatchDialerAdapter.parse_call_webhook(payload)
    background_tasks.add_task(_handle_call_result, event)

    return {"status": "accepted", "disposition": event.disposition, "lead_id": event.lead_id}


@router.post("/launch_control/reply")
async def launch_control_reply_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
) -> dict:
    """
    Receive an inbound SMS reply from Launch Control (or Zapier bridge).
    Detects opt-out keywords and suppresses the lead.
    """
    if LAUNCH_CONTROL_WEBHOOK_SECRET and x_webhook_secret != LAUNCH_CONTROL_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid webhook secret")

    payload = await request.json()
    event = LaunchControlAdapter.parse_reply_webhook(payload)

    background_tasks.add_task(
        _handle_sms_reply,
        event.lead_id,
        event.phone_number,
        event.body,
        event.is_opt_out,
    )

    return {
        "status": "accepted",
        "is_opt_out": event.is_opt_out,
        "lead_id": event.lead_id,
    }


@router.get("/launch_control/csv-queue")
def get_launch_control_csv_queue() -> dict:
    """
    Return the pending Launch Control CSV upload queue.
    Use this to download and manually upload to Launch Control when in csv_sync mode.
    """
    lc = LaunchControlAdapter()
    csv_content = lc.export_csv_queue()
    return {"csv": csv_content, "mode": lc._mode}
