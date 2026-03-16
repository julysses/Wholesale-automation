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

  POST /webhooks/retell/call
      Retell AI fires this when a call event occurs (call_ended / call_analyzed).
      Persists to ai_call_records, updates lead status, creates hot-lead tasks.

  POST /webhooks/air_ai/call
      Air AI fires this on call completion.
      Same processing as Retell — normalized through AICallingAdapter.parse_webhook().
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from tools.batchdialer_adapter import BatchDialerAdapter, CallResultEvent
from tools.launch_control_adapter import LaunchControlAdapter
from tools.retell_adapter import AICallingAdapter, CallResultEvent as AICallResultEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# ── Optional webhook secret verification ──────────────────────────────────────
BATCHDIALER_WEBHOOK_SECRET = os.getenv("BATCHDIALER_WEBHOOK_SECRET", "")
LAUNCH_CONTROL_WEBHOOK_SECRET = os.getenv("LAUNCH_CONTROL_WEBHOOK_SECRET", "")
RETELL_WEBHOOK_SECRET = os.getenv("RETELL_WEBHOOK_SECRET", "")
AIR_AI_WEBHOOK_SECRET = os.getenv("AIR_AI_WEBHOOK_SECRET", "")

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


# ── AI Calling webhook handlers (Retell AI / Air AI) ─────────────────────────

async def _handle_ai_call_result(event: AICallResultEvent, provider: str) -> None:
    """
    Background task: persist AI call result to ai_call_records, update lead
    status, create acquisition tasks for HOT/APPOINTMENT_SET dispositions.
    """
    logger.info(
        f"[Webhook/{provider}] Call {event.call_id} lead={event.lead_id} "
        f"disposition={event.disposition.value} hot={event.is_hot} "
        f"duration={event.duration_seconds}s"
    )

    supabase_url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

    if not (supabase_url and supabase_key):
        logger.warning(f"[Webhook/{provider}] Supabase not configured — event logged only")
        return

    try:
        from supabase import create_client  # type: ignore[import]
        sb = create_client(supabase_url, supabase_key)

        qual = event.qualification

        # 1. Insert AI call record
        sb.table("ai_call_records").insert({
            "lead_id":           event.lead_id or None,
            "provider":          event.provider.value,
            "call_id":           event.call_id,
            "phone_number":      "",  # populated from lead if needed
            "status":            "completed",
            "disposition":       event.disposition.value,
            "duration_sec":      event.duration_seconds,
            "recording_url":     event.recording_url,
            "transcript":        event.transcript,
            "timeline_to_sell":  qual.timeline_to_sell if qual else None,
            "property_condition":qual.property_condition if qual else None,
            "occupancy":         qual.occupancy if qual else None,
            "mortgage_balance":  qual.mortgage_balance if qual else None,
            "asking_price":      qual.asking_price if qual else None,
            "call_notes":        qual.notes if qual else None,
            "raw_payload":       event.raw_payload,
        }).execute()

        if not event.lead_id:
            logger.warning(f"[Webhook/{provider}] Call {event.call_id} has no lead_id — skipping lead update")
            return

        # 2. Map AI disposition → lead status
        DISP_TO_STATUS = {
            "no_answer":       "no_answer",
            "voicemail":       "voicemail",
            "wrong_number":    "dead",
            "not_interested":  "contacted",
            "callback":        "callback",
            "warm":            "warm",
            "hot":             "hot",
            "appointment_set": "appointment_set",
        }
        new_status = DISP_TO_STATUS.get(event.disposition.value, "contacted")

        # Increment contact_attempts
        lead_resp = (
            sb.table("leads")
            .select("contact_attempts")
            .eq("id", event.lead_id)
            .single()
            .execute()
        )
        current_attempts = (lead_resp.data or {}).get("contact_attempts", 0)

        sb.table("leads").update({
            "status":           new_status,
            "last_contact_date": datetime.now(timezone.utc).date().isoformat(),
            "contact_attempts": current_attempts + 1,
        }).eq("id", event.lead_id).execute()

        # 3. Create urgent task for HOT / APPOINTMENT_SET
        if event.is_hot:
            disposition_label = event.disposition.value.replace("_", " ").title()
            notes_parts = []
            if qual:
                if qual.timeline_to_sell:
                    notes_parts.append(f"Timeline: {qual.timeline_to_sell}")
                if qual.property_condition:
                    notes_parts.append(f"Condition: {qual.property_condition}")
                if qual.occupancy:
                    notes_parts.append(f"Occupancy: {qual.occupancy}")
                if qual.mortgage_balance:
                    notes_parts.append(f"Mortgage: ${qual.mortgage_balance:,.0f}")
                if qual.asking_price:
                    notes_parts.append(f"Asking: ${qual.asking_price:,.0f}")
                if qual.notes:
                    notes_parts.append(f"Summary: {qual.notes}")

            sb.table("tasks").insert({
                "lead_id":     event.lead_id,
                "title":       f"🔥 {disposition_label} — AI Call Result",
                "description": "\n".join(notes_parts) if notes_parts else "Follow up with seller immediately.",
                "priority":    "high",
                "status":      "pending",
                "type":        "acquisition_review",
            }).execute()

            # Insert acquisition alert notification
            sb.table("app_notifications").insert({
                "recipient_role": "admin",
                "type":           "hot_lead" if event.disposition.value == "hot" else "appointment_set",
                "title":          f"{'🔥 Hot Lead' if event.disposition.value == 'hot' else '📅 Appointment Set'}",
                "body":           (
                    f"AI call completed. {disposition_label}. "
                    + (f"Seller asking: ${qual.asking_price:,.0f}" if qual and qual.asking_price else "")
                ).strip(),
                "action_url":     f"/leads?status={new_status}",
                "lead_id":        event.lead_id,
            }).execute()

        logger.info(f"[Webhook/{provider}] Lead {event.lead_id} → {new_status}")

    except Exception as exc:
        logger.error(f"[Webhook/{provider}] Processing failed: {exc}")


@router.post("/retell/call")
async def retell_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
) -> dict:
    """
    Receive a call event from Retell AI (call_ended or call_analyzed).
    Responds immediately with 200; all Supabase writes happen in the background.
    """
    if RETELL_WEBHOOK_SECRET and x_webhook_secret != RETELL_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid webhook secret")

    payload = await request.json()
    event = AICallingAdapter.parse_webhook(payload, provider="retell")

    if event is None:
        # Non-final event (call_started, etc.) — acknowledge and ignore
        return {"status": "ignored", "reason": "non-final event"}

    background_tasks.add_task(_handle_ai_call_result, event, "retell")

    return {
        "status": "accepted",
        "call_id": event.call_id,
        "disposition": event.disposition.value,
        "lead_id": event.lead_id,
        "is_hot": event.is_hot,
    }


@router.post("/air_ai/call")
async def air_ai_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
) -> dict:
    """
    Receive a call completion event from Air AI.
    """
    if AIR_AI_WEBHOOK_SECRET and x_webhook_secret != AIR_AI_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid webhook secret")

    payload = await request.json()
    event = AICallingAdapter.parse_webhook(payload, provider="air_ai")

    if event is None:
        return {"status": "ignored", "reason": "unparseable payload"}

    background_tasks.add_task(_handle_ai_call_result, event, "air_ai")

    return {
        "status": "accepted",
        "call_id": event.call_id,
        "disposition": event.disposition.value,
        "lead_id": event.lead_id,
        "is_hot": event.is_hot,
    }
