"""
Inbound webhook handlers.

Routes:
  POST /webhooks/retell
      Primary Retell AI webhook — handles all 4 event types:
        retell.call.started     → log call initiation
        retell.call.answered    → mark call as answered, update lead status
        retell.call.transcript  → store real-time transcript chunk
        retell.call.completed   → run qualification, trigger HOT/WARM automation

  POST /webhooks/batchdialer/call
      BatchDialer call completion webhook.

  POST /webhooks/launch_control/reply
      Launch Control / Zapier SMS reply webhook (opt-out enforcement).

  GET  /webhooks/launch_control/csv-queue
      CSV export for manual Launch Control upload.

  POST /webhooks/air_ai/call
      Air AI call completion (same processing path as Retell completed).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from tools.batchdialer_adapter import BatchDialerAdapter, CallResultEvent
from tools.launch_control_adapter import LaunchControlAdapter
from tools.retell_adapter import (
    AICallingAdapter,
    CallResultEvent as AICallResultEvent,
    parse_transcript,
    extract_lead_signals,
    transcript_to_text,
)
from tools.vapi_adapter import (
    VapiAdapter,
    VapiCallResult,
    extract_vapi_lead_signals,
    _turns_to_text as vapi_turns_to_text,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# ── Optional webhook secret verification ──────────────────────────────────────
BATCHDIALER_WEBHOOK_SECRET = os.getenv("BATCHDIALER_WEBHOOK_SECRET", "")
LAUNCH_CONTROL_WEBHOOK_SECRET = os.getenv("LAUNCH_CONTROL_WEBHOOK_SECRET", "")
RETELL_WEBHOOK_SECRET = os.getenv("RETELL_WEBHOOK_SECRET", "")
AIR_AI_WEBHOOK_SECRET = os.getenv("AIR_AI_WEBHOOK_SECRET", "")
VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "")

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

    sb = _get_supabase()
    if sb and event.lead_id:
        try:

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

    sb = _get_supabase()
    if not sb:
        logger.warning("[Webhook] Supabase not configured — SMS reply logged only")
        return

    try:

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

    sb = _get_supabase()
    if not sb:
        logger.warning(f"[Webhook/{provider}] Supabase not configured — event logged only")
        return

    try:

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


@router.post("/retell")
async def retell_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_retell_signature: str = Header(default=""),
) -> dict:
    """
    Primary Retell AI webhook — handles all 4 event types:

    retell.call.started    → persist ai_call_records row, update lead status = in_dialer
    retell.call.answered   → update ai_call_records.status = answered
    retell.call.transcript → append transcript chunk to call_transcripts
    retell.call.completed  → run LLM qualification, trigger HOT/WARM automation

    Retell expects 200 immediately; all processing is backgrounded.
    """
    if RETELL_WEBHOOK_SECRET and x_retell_signature != RETELL_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid Retell webhook signature")

    payload = await request.json()
    event_type = payload.get("event") or payload.get("event_type", "")
    call_data  = payload.get("call", {})
    call_id    = call_data.get("call_id", "")
    metadata   = call_data.get("metadata", {})
    lead_id    = metadata.get("lead_id", "")

    logger.info(f"[retell] Webhook event={event_type!r} call={call_id} lead={lead_id}")

    # ── Event: call started ───────────────────────────────────────────────────
    if event_type in ("call_started", "retell.call.started"):
        background_tasks.add_task(_retell_call_started, call_id, lead_id, metadata, payload)
        return {"status": "accepted", "event": "call_started"}

    # ── Event: call answered (seller picked up) ───────────────────────────────
    if event_type in ("call_answered", "retell.call.answered"):
        background_tasks.add_task(_retell_call_answered, call_id, lead_id)
        return {"status": "accepted", "event": "call_answered"}

    # ── Event: real-time transcript chunk ─────────────────────────────────────
    if event_type in ("call_transcript", "retell.call.transcript"):
        transcript_chunk = call_data.get("transcript", [])
        background_tasks.add_task(_retell_transcript_chunk, call_id, lead_id, transcript_chunk)
        return {"status": "accepted", "event": "call_transcript"}

    # ── Event: call completed (final) ────────────────────────────────────────
    if event_type in (
        "call_ended", "call_analyzed",
        "retell.call.completed", "retell.call.analyzed",
    ):
        event = AICallingAdapter.parse_webhook(payload, provider="retell")
        if event:
            background_tasks.add_task(_retell_call_completed, event, payload)
        return {
            "status": "accepted",
            "event": "call_completed",
            "call_id": call_id,
            "lead_id": lead_id,
        }

    logger.debug(f"[retell] Unhandled event type {event_type!r}")
    return {"status": "ignored", "event": event_type}


async def _retell_call_started(
    call_id: str,
    lead_id: str,
    metadata: dict,
    raw_payload: dict,
) -> None:
    """Create ai_call_records row and set lead status to in_dialer_campaign."""
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("ai_call_records").insert({
            "call_id":      call_id,
            "lead_id":      lead_id or None,
            "provider":     "retell",
            "phone_number": metadata.get("to_number", ""),
            "status":       "initiated",
            "raw_payload":  raw_payload,
        }).execute()

        if lead_id:
            sb.table("leads").update({
                "status": "in_dialer_campaign",
            }).eq("id", lead_id).execute()

        _audit(sb, "call", call_id, "call_started", metadata={"lead_id": lead_id})
    except Exception as exc:
        logger.error(f"[retell] call_started persistence failed: {exc}")


async def _retell_call_answered(call_id: str, lead_id: str) -> None:
    """Mark call as answered in ai_call_records."""
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("ai_call_records").update({
            "status": "answered",
        }).eq("call_id", call_id).execute()

        if lead_id:
            sb.table("leads").update({"status": "contacted"}).eq("id", lead_id).execute()

        _audit(sb, "call", call_id, "call_answered")
    except Exception as exc:
        logger.error(f"[retell] call_answered persistence failed: {exc}")


async def _retell_transcript_chunk(
    call_id: str,
    lead_id: str,
    transcript_chunk: Any,
) -> None:
    """Append/upsert transcript chunk into call_transcripts."""
    sb = _get_supabase()
    if not sb:
        return
    try:
        turns = parse_transcript(transcript_chunk)
        text  = transcript_to_text(turns)
        # Upsert by call_id (conflict → update raw_transcript with latest full version)
        sb.table("call_transcripts").upsert({
            "call_id":        call_id,
            "lead_id":        lead_id or None,
            "provider":       "retell",
            "raw_transcript": text,
            "formatted":      [{"role": t.role, "content": t.content} for t in turns],
        }, on_conflict="call_id").execute()
    except Exception as exc:
        logger.error(f"[retell] transcript_chunk persistence failed: {exc}")


async def _retell_call_completed(event: AICallResultEvent, raw_payload: dict) -> None:
    """
    Full processing pipeline for a completed Retell call:
    1. Store final transcript in call_transcripts
    2. Run LLM qualification analysis (extract_lead_signals)
    3. Persist qualification_results
    4. Update ai_call_records with qual_score + classification
    5. Update lead status
    6. HOT automation: create task, pause dialing, trigger SMS, send notification
    7. WARM automation: enroll in Launch Control Day-1 sequence
    8. Write audit log
    """
    sb = _get_supabase()

    # 1. Store final transcript
    call_data = raw_payload.get("call", {})
    raw_transcript = call_data.get("transcript")
    metadata = call_data.get("metadata", {})
    property_address = metadata.get("property_address", "")
    owner_name = metadata.get("owner_name", "")

    if sb and raw_transcript and event.lead_id:
        try:
            turns = parse_transcript(raw_transcript)
            text  = transcript_to_text(turns) if turns else (
                raw_transcript if isinstance(raw_transcript, str) else ""
            )
            sb.table("call_transcripts").upsert({
                "call_id":        event.call_id,
                "lead_id":        event.lead_id or None,
                "provider":       "retell",
                "raw_transcript": text,
                "formatted":      [{"role": t.role, "content": t.content} for t in turns] if turns else [],
            }, on_conflict="call_id").execute()
        except Exception as exc:
            logger.error(f"[retell] final transcript store failed: {exc}")

    # 2. Run LLM qualification
    qual = None
    try:
        qual = extract_lead_signals(
            raw_transcript or "",
            property_address=property_address,
            owner_name=owner_name,
        )
        logger.info(
            f"[retell] Qualification: score={qual.qualification_score} "
            f"class={qual.classification} sentiment={qual.sentiment}"
        )
    except Exception as exc:
        logger.error(f"[retell] Qualification analysis failed: {exc}")

    # 3 & 4. Persist qualification_results + update ai_call_records
    qual_record_id = None
    if sb and qual:
        try:
            qual_resp = sb.table("qualification_results").insert({
                "call_id":             event.call_id,
                "lead_id":             event.lead_id or None,
                "timeline":            qual.timeline,
                "condition":           qual.condition,
                "occupancy":           qual.occupancy,
                "asking_price":        qual.asking_price,
                "mortgage_balance":    qual.mortgage_balance,
                "sentiment":           qual.sentiment,
                "expressed_no_interest": qual.expressed_no_interest,
                "hung_up":             qual.hung_up,
                "named_price":         qual.named_price,
                "qualification_score": qual.qualification_score,
                "classification":      qual.classification,
                "score_breakdown":     qual.score_breakdown,
                "offer_range_low":     qual.offer_range_low,
                "offer_range_high":    qual.offer_range_high,
                "summary":             qual.summary,
                "key_quotes":          qual.key_quotes,
            }).execute()
            qual_record_id = (qual_resp.data or [{}])[0].get("id")

            # Update ai_call_records
            sb.table("ai_call_records").update({
                "status":          "completed",
                "disposition":     event.disposition.value,
                "duration_sec":    event.duration_seconds,
                "recording_url":   event.recording_url,
                "qual_score":      qual.qualification_score,
                "classification":  qual.classification,
                "sentiment":       qual.sentiment,
                "offer_range_low": qual.offer_range_low,
                "offer_range_high":qual.offer_range_high,
                "call_notes":      qual.summary,
                "qual_result_id":  qual_record_id,
            }).eq("call_id", event.call_id).execute()
        except Exception as exc:
            logger.error(f"[retell] Qual persistence failed: {exc}")

    if not sb or not event.lead_id:
        return

    try:
        # 5. Update lead status
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

        lead_resp = sb.table("leads").select("contact_attempts,property_address,owner_first_name,owner_last_name,estimated_arv,mao").eq("id", event.lead_id).single().execute()
        lead_data = lead_resp.data or {}
        current_attempts = lead_data.get("contact_attempts", 0)

        update_payload: dict = {
            "status":           new_status,
            "last_contact_date": datetime.now(timezone.utc).date().isoformat(),
            "contact_attempts": current_attempts + 1,
        }
        if qual:
            if qual.classification == "HOT":
                update_payload["ai_calling_paused"] = True
        sb.table("leads").update(update_payload).eq("id", event.lead_id).execute()

        address = lead_data.get("property_address") or property_address
        owner   = f"{lead_data.get('owner_first_name', '')} {lead_data.get('owner_last_name', '')}".strip() or owner_name
        arv     = lead_data.get("estimated_arv")
        mao     = lead_data.get("mao")

        # 6. HOT automation
        if qual and qual.is_hot:
            _trigger_hot_lead_automation(
                sb=sb,
                lead_id=event.lead_id,
                call_id=event.call_id,
                address=address,
                owner=owner,
                qual=qual,
                arv=arv,
                mao=mao,
            )

        # 7. WARM automation — enroll in Launch Control Day-1 SMS sequence
        elif qual and qual.is_warm and event.lead_id:
            try:
                lc = LaunchControlAdapter()
                from tools.launch_control_adapter import LaunchControlContact
                lc.add_contact_to_campaign(LaunchControlContact(
                    lead_id=event.lead_id,
                    first_name=owner.split()[0] if owner else "",
                    last_name=" ".join(owner.split()[1:]) if owner else "",
                    phone=event.raw_payload.get("call", {}).get("to_number", ""),
                    property_address=address,
                    campaign_name=settings.launch_control_default_campaign,
                ))
                logger.info(f"[retell] WARM lead {event.lead_id} enrolled in Launch Control")
            except Exception as exc:
                logger.error(f"[retell] Launch Control enrollment failed: {exc}")

        # 8. Audit log
        _audit(sb, "call", event.call_id, "call_completed", new_value={
            "disposition": event.disposition.value,
            "qualification_score": qual.qualification_score if qual else None,
            "classification": qual.classification if qual else None,
        })

    except Exception as exc:
        logger.error(f"[retell] call_completed processing failed: {exc}")


def _trigger_hot_lead_automation(
    sb: Any,
    lead_id: str,
    call_id: str,
    address: str,
    owner: str,
    qual: Any,
    arv: Optional[float],
    mao: Optional[float],
) -> None:
    """
    HOT lead automation actions:
    1. Create acquisition task (high priority)
    2. Pause AI dialing for this lead
    3. Trigger SMS follow-up via Launch Control
    4. Send push notification to admin
    """
    # 1. Create acquisition task
    asking_str = f"${qual.asking_price:,.0f}" if qual.asking_price else "Unknown"
    offer_str  = (
        f"${qual.offer_range_low:,.0f}–${qual.offer_range_high:,.0f}"
        if qual.offer_range_low and qual.offer_range_high
        else (f"${mao:,.0f}" if mao else "TBD")
    )
    arv_str = f"${arv:,.0f}" if arv else "Unknown"

    task_description = (
        f"🔥 HOT LEAD — Qualification Score: {qual.qualification_score}\n\n"
        f"Property:    {address}\n"
        f"Owner:       {owner}\n"
        f"Timeline:    {qual.timeline.replace('_', ' ').title()}\n"
        f"Condition:   {qual.condition.replace('_', ' ').title()}\n"
        f"Occupancy:   {qual.occupancy.replace('_', ' ').title()}\n"
        f"Asking:      {asking_str}\n"
        f"Est. Value:  {arv_str}\n"
        f"Offer Range: {offer_str}\n"
        f"Sentiment:   {qual.sentiment.title()}\n\n"
        f"Summary: {qual.summary}\n\n"
        + (f"Key quotes:\n" + "\n".join(f'  • "{q}"' for q in qual.key_quotes[:3]) if qual.key_quotes else "")
    )
    try:
        sb.table("tasks").insert({
            "lead_id":     lead_id,
            "title":       f"🔥 HOT LEAD — {address}",
            "description": task_description,
            "priority":    "high",
            "status":      "pending",
            "type":        "acquisition_review",
        }).execute()
    except Exception as exc:
        logger.error(f"[retell] HOT task creation failed: {exc}")

    # 2. Pause AI dialing (already set on lead — confirm here)
    try:
        sb.table("leads").update({"ai_calling_paused": True}).eq("id", lead_id).execute()
    except Exception as exc:
        logger.error(f"[retell] Pause dialing update failed: {exc}")

    # 3. Trigger SMS (immediate — Day 1)
    try:
        from tools.launch_control_adapter import LaunchControlAdapter, LaunchControlContact
        lc = LaunchControlAdapter()
        hot_campaign = settings.launch_control_default_campaign + " HOT"
        lc.add_contact_to_campaign(LaunchControlContact(
            lead_id=lead_id,
            first_name=owner.split()[0] if owner else "",
            last_name=" ".join(owner.split()[1:]) if owner else "",
            phone="",  # fetched from lead record
            property_address=address,
            campaign_name=hot_campaign,
        ))
    except Exception as exc:
        logger.error(f"[retell] HOT SMS trigger failed: {exc}")

    # 4. Push notification (DB insert — picked up by useNotifications real-time)
    try:
        sb.table("app_notifications").insert({
            "recipient_role": "admin",
            "type":           "hot_lead",
            "title":          f"🔥 HOT Lead — {address}",
            "body":           (
                f"Qual score {qual.qualification_score} · "
                f"Timeline: {qual.timeline.replace('_', ' ')} · "
                f"Asking: {asking_str}"
            ),
            "action_url":     f"/acquisitions?lead={lead_id}",
            "lead_id":        lead_id,
            "metadata": {
                "qualification_score": qual.qualification_score,
                "classification":      qual.classification,
                "asking_price":        qual.asking_price,
                "offer_range_low":     qual.offer_range_low,
                "offer_range_high":    qual.offer_range_high,
            },
        }).execute()
    except Exception as exc:
        logger.error(f"[retell] HOT notification insert failed: {exc}")

    logger.info(f"[retell] HOT automation complete for lead {lead_id}")


def _get_supabase() -> Optional[Any]:
    """Return a Supabase client or None if not configured."""
    url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    if not (url and key):
        logger.warning("[webhook] Supabase not configured")
        return None
    try:
        from supabase import create_client  # type: ignore[import]
        return create_client(url, key)
    except Exception as exc:
        logger.error(f"[webhook] Supabase client init failed: {exc}")
        return None


def _audit(
    sb: Any,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Insert a row into audit_logs (best-effort, non-blocking)."""
    try:
        sb.table("audit_logs").insert({
            "entity_type": entity_type,
            "entity_id":   entity_id,
            "action":      action,
            "actor":       "ai_agent",
            "old_value":   old_value,
            "new_value":   new_value,
            "metadata":    metadata,
        }).execute()
    except Exception:
        pass  # audit log failures must never break the main flow


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


# ── VAPI webhook ───────────────────────────────────────────────────────────────

@router.post("/vapi")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_vapi_secret: str = Header(default=""),
) -> dict:
    """
    VAPI.ai call webhook — handles all event types:

    call-started         → acknowledge (non-final)
    transcript           → acknowledge (real-time, non-final)
    function-call        → acknowledge (tool invocation, non-final)
    call-ended           → run 4-Pillar qualification, trigger HOT/WARM automation
    end-of-call-report   → alias for call-ended

    VAPI expects 200 immediately; all Supabase writes are backgrounded.
    Configure the VAPI webhook URL in your VAPI dashboard:
      Server URL: https://<your-domain>/webhooks/vapi
      Secret:     set VAPI_WEBHOOK_SECRET in your .env
    """
    if VAPI_WEBHOOK_SECRET and x_vapi_secret != VAPI_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid VAPI webhook secret")

    payload = await request.json()

    # VAPI wraps events under payload["message"]
    msg = payload.get("message", payload)
    msg_type = msg.get("type", "") or payload.get("type", "")
    call = msg.get("call", {})
    call_id = call.get("id", "") or msg.get("callId", "")
    metadata = call.get("metadata", {}) or msg.get("metadata", {})
    lead_id = metadata.get("lead_id", "")

    logger.info(f"[vapi] Webhook type={msg_type!r} call={call_id} lead={lead_id}")

    # ── Non-final events: acknowledge immediately ─────────────────────────────
    NON_FINAL = {
        "call-started", "transcript", "function-call",
        "assistant-request", "speech-update", "conversation-update", "tool-calls",
    }
    if msg_type in NON_FINAL:
        return {"status": "accepted", "event": msg_type}

    # ── Final event: call-ended / end-of-call-report ──────────────────────────
    if msg_type in ("call-ended", "end-of-call-report", ""):
        result = VapiAdapter.parse_webhook(payload)
        if result is None:
            return {"status": "ignored", "reason": "unparseable payload"}

        background_tasks.add_task(_handle_vapi_call_result, result)

        return {
            "status": "accepted",
            "call_id": result.call_id,
            "disposition": result.disposition.value,
            "lead_id": result.lead_id,
            "is_hot": result.is_hot,
        }

    logger.debug(f"[vapi] Unhandled message type {msg_type!r}")
    return {"status": "ignored", "event": msg_type}


async def _handle_vapi_call_result(result: VapiCallResult) -> None:
    """
    Background task for a completed VAPI call:

    1. Store transcript in call_transcripts
    2. Run LLM qualification (same qualification_agent as Retell)
    3. Persist qualification_results
    4. Insert / update ai_call_records
    5. Update lead status
    6. HOT automation: task + notification + SMS
    7. WARM automation: Launch Control enrollment
    8. DNC: enforce opt-out if disposition == DNC
    """
    sb = _get_supabase()
    qual_obj = result.qualification  # VapiQualification (pre-extracted by VAPI analysis)
    provider = "vapi"

    logger.info(
        f"[{provider}] Processing call {result.call_id} lead={result.lead_id} "
        f"disposition={result.disposition.value} hot={result.is_hot} "
        f"duration={result.duration_seconds}s"
    )

    # ── 1. Store transcript ───────────────────────────────────────────────────
    if sb and result.transcript and result.lead_id:
        try:
            sb.table("call_transcripts").upsert({
                "call_id":        result.call_id,
                "lead_id":        result.lead_id,
                "provider":       provider,
                "raw_transcript": result.transcript,
            }, on_conflict="call_id").execute()
        except Exception as exc:
            logger.error(f"[{provider}] transcript store failed: {exc}")

    # ── 2. Run LLM qualification ──────────────────────────────────────────────
    qual = None
    property_address = result.raw_payload.get("message", result.raw_payload).get(
        "call", {}
    ).get("metadata", {}).get("property_address", "")
    owner_name = result.raw_payload.get("message", result.raw_payload).get(
        "call", {}
    ).get("metadata", {}).get("owner_name", "")

    try:
        qual = extract_vapi_lead_signals(
            result.transcript or "",
            property_address=property_address,
            owner_name=owner_name,
        )
        logger.info(
            f"[{provider}] Qualification: score={qual.qualification_score} "
            f"class={qual.classification}"
        )
    except Exception as exc:
        logger.error(f"[{provider}] Qualification analysis failed: {exc}")

    # ── 3 & 4. Persist qualification_results + upsert ai_call_records ─────────
    if sb and result.lead_id:
        try:
            if qual:
                sb.table("qualification_results").insert({
                    "call_id":              result.call_id,
                    "lead_id":              result.lead_id,
                    "timeline":             qual.timeline,
                    "condition":            qual.condition,
                    "occupancy":            qual.occupancy,
                    "asking_price":         qual.asking_price,
                    "mortgage_balance":     qual.mortgage_balance,
                    "sentiment":            qual.sentiment,
                    "expressed_no_interest": qual.expressed_no_interest,
                    "hung_up":              qual.hung_up,
                    "named_price":          qual.named_price,
                    "qualification_score":  qual.qualification_score,
                    "classification":       qual.classification,
                    "offer_range_low":      qual.offer_range_low,
                    "offer_range_high":     qual.offer_range_high,
                    "raw_signals":          qual.raw_signals if hasattr(qual, "raw_signals") else {},
                }).execute()

            # VAPI-specific 4-Pillar fields from pre-extracted qual_obj
            pillar_data: dict = {}
            if qual_obj:
                pillar_data = {
                    "motivation":          qual_obj.motivation,
                    "is_urgent":           qual_obj.is_urgent,
                    "timeline_to_sell":    qual_obj.timeline_to_sell,
                    "property_condition":  qual_obj.property_condition,
                    "occupancy":           qual_obj.occupancy,
                    "asking_price":        qual_obj.asking_price,
                    "mortgage_balance":    qual_obj.mortgage_balance,
                    "call_notes":          qual_obj.notes,
                }

            sb.table("ai_call_records").upsert({
                "call_id":              result.call_id,
                "lead_id":              result.lead_id,
                "provider":             provider,
                "status":               "completed",
                "disposition":          result.disposition.value,
                "duration_sec":         result.duration_seconds,
                "recording_url":        result.recording_url,
                "transcript":           result.transcript,
                "qualification_score":  qual.qualification_score if qual else None,
                "classification":       qual.classification if qual else None,
                "raw_payload":          result.raw_payload,
                **pillar_data,
            }, on_conflict="call_id").execute()

        except Exception as exc:
            logger.error(f"[{provider}] qualification persist failed: {exc}")

    # ── 5. Update lead status ─────────────────────────────────────────────────
    DISP_TO_STATUS = {
        "no_answer":       "no_answer",
        "voicemail":       "voicemail",
        "wrong_number":    "dead",
        "not_interested":  "contacted",
        "dnc":             "dnc",
        "callback":        "callback",
        "warm":            "warm",
        "hot":             "hot",
        "appointment_set": "appointment_set",
    }
    new_status = DISP_TO_STATUS.get(result.disposition.value, "contacted")

    if sb and result.lead_id:
        try:
            lead_resp = (
                sb.table("leads")
                .select("contact_attempts, owner_first_name, owner_last_name, property_address, estimated_arv, mao")
                .eq("id", result.lead_id)
                .single()
                .execute()
            )
            lead_data = lead_resp.data or {}
            current_attempts = lead_data.get("contact_attempts", 0)

            update: dict[str, Any] = {
                "status":             new_status,
                "last_contact_date":  datetime.now(timezone.utc).date().isoformat(),
                "contact_attempts":   current_attempts + 1,
            }
            if result.is_dnc:
                update["dnc"] = True
                update["sms_sequence_active"] = False

            sb.table("leads").update(update).eq("id", result.lead_id).execute()

            # ── 6. HOT automation ─────────────────────────────────────────────
            if result.is_hot and qual:
                owner = (
                    f"{lead_data.get('owner_first_name', '')} "
                    f"{lead_data.get('owner_last_name', '')}".strip()
                )
                address = lead_data.get("property_address", property_address)
                _trigger_hot_lead_automation(
                    sb=sb,
                    lead_id=result.lead_id,
                    call_id=result.call_id,
                    address=address,
                    owner=owner,
                    qual=qual,
                    arv=lead_data.get("estimated_arv"),
                    mao=lead_data.get("mao"),
                )

            # ── 7. WARM automation ────────────────────────────────────────────
            elif qual and qual.is_warm and result.lead_id:
                try:
                    from tools.launch_control_adapter import LaunchControlAdapter, LaunchControlContact
                    owner = (
                        f"{lead_data.get('owner_first_name', '')} "
                        f"{lead_data.get('owner_last_name', '')}".strip()
                    )
                    lc = LaunchControlAdapter()
                    lc.add_contact_to_campaign(LaunchControlContact(
                        lead_id=result.lead_id,
                        first_name=lead_data.get("owner_first_name", ""),
                        last_name=lead_data.get("owner_last_name", ""),
                        phone=result.raw_payload.get("message", {}).get("call", {}).get(
                            "customer", {}
                        ).get("number", ""),
                        property_address=lead_data.get("property_address", ""),
                        campaign_name=settings.launch_control_default_campaign,
                    ))
                    logger.info(f"[{provider}] WARM lead {result.lead_id} enrolled in Launch Control")
                except Exception as exc:
                    logger.error(f"[{provider}] Launch Control enrollment failed: {exc}")

            # ── 8. DNC enforcement ─────────────────────────────────────────────
            if result.is_dnc:
                phone = result.raw_payload.get("message", {}).get("call", {}).get(
                    "customer", {}
                ).get("number", "")
                if phone:
                    try:
                        sb.table("dnc_registry").insert({
                            "phone_number": phone,
                            "lead_id":      result.lead_id,
                            "reason":       "call_disposition_dnc",
                            "source":       provider,
                        }).execute()
                    except Exception as exc:
                        logger.error(f"[{provider}] DNC registry insert failed: {exc}")

        except Exception as exc:
            logger.error(f"[{provider}] lead update failed: {exc}")

    _audit(sb, "call", result.call_id, "vapi_call_completed", new_value={
        "disposition": result.disposition.value,
        "qualification_score": qual.qualification_score if qual else None,
        "classification": qual.classification if qual else None,
    }) if sb else None

    logger.info(f"[{provider}] Call {result.call_id} lead {result.lead_id} → {new_status}")


# ── Facebook Lead Ads webhooks ─────────────────────────────────────────────────

FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")
FACEBOOK_WEBHOOK_VERIFY_TOKEN = os.getenv("FACEBOOK_WEBHOOK_VERIFY_TOKEN", "")


@router.get("/facebook/lead")
async def facebook_lead_webhook_verify(
    hub_mode: str = "",
    hub_verify_token: str = "",
    hub_challenge: str = "",
):
    """
    Facebook webhook verification challenge (GET).
    Facebook sends this when you first subscribe to the leadgen event.
    """
    from tools.facebook_ads_adapter import FacebookAdsAdapter
    adapter = FacebookAdsAdapter(
        app_secret=FACEBOOK_APP_SECRET,
        access_token="",
        webhook_verify_token=FACEBOOK_WEBHOOK_VERIFY_TOKEN,
    )
    challenge = adapter.verify_webhook_challenge(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    # Facebook expects a plain text integer response
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(challenge)


@router.post("/facebook/lead")
async def facebook_lead_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """
    Facebook Lead Ads webhook receiver (POST).
    Receives leadgen events, fetches field_data from Graph API,
    and creates a lead in the pipeline.
    """
    payload_bytes = await request.body()

    # Verify HMAC signature
    if FACEBOOK_APP_SECRET:
        from tools.facebook_ads_adapter import FacebookAdsAdapter
        adapter = FacebookAdsAdapter(
            app_secret=FACEBOOK_APP_SECRET,
            access_token=os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
            webhook_verify_token=FACEBOOK_WEBHOOK_VERIFY_TOKEN,
            ad_account_id=os.getenv("FACEBOOK_AD_ACCOUNT_ID", ""),
        )
        sig = x_hub_signature_256 or ""
        if not adapter.verify_webhook_signature(payload_bytes, sig):
            raise HTTPException(status_code=403, detail="Invalid Facebook signature")
    else:
        # Import adapter for parsing even without signature check
        from tools.facebook_ads_adapter import FacebookAdsAdapter
        adapter = FacebookAdsAdapter(
            app_secret="",
            access_token=os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
            webhook_verify_token=FACEBOOK_WEBHOOK_VERIFY_TOKEN,
            ad_account_id=os.getenv("FACEBOOK_AD_ACCOUNT_ID", ""),
        )

    import json as _json
    try:
        payload = _json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    entries = adapter.parse_lead_webhook(payload)
    if not entries:
        return {"received": True, "leads": 0}

    for entry in entries:
        if entry.leadgen_id:
            background_tasks.add_task(_process_facebook_lead, entry, adapter)

    return {"received": True, "leads": len(entries)}


async def _process_facebook_lead(entry: Any, adapter: Any) -> None:
    """
    Background task: fetch FB lead field_data → create lead → run qualification.
    """
    from tools.facebook_ads_adapter import normalize_facebook_fields
    from web.api.lead_forms_api import (
        _compute_scores_from_answers, _send_hot_lead_notification
    )
    from tools.crm import get_supabase_client

    logger.info(f"[Facebook] Processing leadgen_id={entry.leadgen_id}")

    lead_data_raw = adapter.fetch_lead_form_data(entry.leadgen_id)
    if not lead_data_raw:
        logger.error(f"[Facebook] Could not fetch lead data for {entry.leadgen_id}")
        return

    fields = normalize_facebook_fields(lead_data_raw.fields)
    scores = _compute_scores_from_answers(fields)

    supabase = get_supabase_client()

    # Build lead record
    lead_payload = {
        "owner_first_name": fields.get("first_name", ""),
        "owner_last_name": fields.get("last_name", ""),
        "owner_phone_1": fields.get("phone", ""),
        "owner_email": fields.get("email", ""),
        "property_address": fields.get("property_address", "Unknown"),
        "city": fields.get("city", ""),
        "state": fields.get("state", "TX"),
        "zip_code": fields.get("zip_code", ""),
        "source": "facebook_lead_ad",
        "inbound_channel": "facebook_lead_ad",
        "status": "new",
        "score_motivation": scores["score_motivation"],
        "score_timeline": scores["score_timeline"],
        "score_equity": scores["score_equity"],
        "score_condition": scores["score_condition"],
        "score_flexibility": scores["score_flexibility"],
        "priority_tier": scores["priority_tier"],
        "motivation_tag": scores["motivation_tag"],
        "contact_attempts": 0,
        "sms_sequence_active": False,
        "email_sequence_active": False,
        "dnc": False,
        "internal_notes": f"FB leadgen_id={entry.leadgen_id}",
    }

    # Try to link to a campaign by external_campaign_id
    if entry.campaign_id:
        try:
            camp = supabase.table("ad_campaigns").select("id").eq(
                "external_campaign_id", entry.campaign_id
            ).single().execute()
            if camp.data:
                lead_payload["ad_campaign_id"] = camp.data["id"]
        except Exception:
            pass

    try:
        resp = supabase.table("leads").insert(lead_payload).execute()
        lead_id = resp.data[0]["id"] if resp.data else None
    except Exception as exc:
        logger.error(f"[Facebook] Lead insert failed: {exc}")
        return

    if not lead_id:
        return

    # Update campaign lead count
    if lead_payload.get("ad_campaign_id"):
        try:
            supabase.rpc("increment_campaign_leads", {
                "campaign_id": lead_payload["ad_campaign_id"]
            }).execute()
        except Exception:
            pass

    # Run qualification agent
    try:
        from agents.qualification_agent import QualificationAgent
        QualificationAgent().run(lead_id=lead_id)
    except Exception as exc:
        logger.error(f"[Facebook] Qualification failed for {lead_id}: {exc}")

    # HOT lead alert
    total_score = sum([
        scores["score_motivation"], scores["score_timeline"],
        scores["score_equity"], scores["score_condition"], scores["score_flexibility"],
    ])
    if total_score >= 13:
        _send_hot_lead_notification(lead_id, fields, total_score)

    logger.info(f"[Facebook] Lead {lead_id} created (score={total_score}, tier={scores['priority_tier']})")
