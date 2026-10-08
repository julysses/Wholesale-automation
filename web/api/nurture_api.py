"""Operator-reviewed, finite SMS follow-up with durable no-replay claims."""
from datetime import datetime, timedelta, timezone
import hmac
import os
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from config.settings import settings
from schemas.outreach import OutreachMessage, OutreachChannel
from tools.crm import get_supabase_client
from tools.facebook_consent import normalize_us_phone
from tools.sms_client import SMSClient, sms_consent_blocker
from tools.operational_alerts import record_provider_alert

router = APIRouter(tags=["SMS nurture"])
TEMPLATE = "Hi {name}, Hilltop Home Co following up on your property inquiry at {address}. Would you like Julio to follow up? Reply STOP to opt out."
SUCCESS = {"accepted", "scheduled", "queued", "sending", "sent", "delivered", "read"}

class Enrollment(BaseModel):
    request_id: UUID
    acknowledged: bool = False


def _db():
    sb = get_supabase_client()
    if sb is None:
        raise HTTPException(503, "Database not configured")
    return sb


def _readiness(sb, lead_id):
    rows = sb.table("leads").select("*").eq("id", str(lead_id)).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lead not found")
    lead, blockers, phone = rows[0], [], None
    try:
        phone = normalize_us_phone(lead.get("owner_phone_1"))
    except ValueError:
        blockers.append("A valid US phone number is required")
    if lead.get("dnc") is not False or lead.get("status") in {"dead","dnc","closed","under_contract","responding","hot","qualified_hot"}:
        blockers.append("Lead is suppressed, already responding, or no longer eligible for nurture")
    if not settings.sms_nurture_enabled:
        blockers.append("Scheduled SMS nurture is disabled pending controlled acceptance")
    sms = SMSClient()
    if settings.sms_provider != "twilio" or not settings.sms_live_enabled or not sms._configured:
        blockers.append("Twilio live SMS is not configured")
    allowed = {p.strip() for p in settings.sms_allowed_recipients.split(",") if p.strip()}
    if not allowed or phone not in allowed:
        blockers.append("Recipient is outside the finite launch allowlist")
    if not os.getenv("CRON_SECRET"):
        blockers.append("Scheduled worker secret is not configured")
    events = []
    if phone:
        consent = sms_consent_blocker(sb, str(lead_id), phone)
        if consent:
            blockers.append(consent)
        events = sb.table("sms_events").select("id,direction,status,raw_payload,created_at").eq("provider","twilio").eq("phone_number",phone).gte("created_at",(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()).execute().data or []
        attempts = [e for e in events if e.get("direction") == "outbound" and "MessageSid" not in (e.get("raw_payload") or {})]
        if any(e.get("status") in {"submitting","unknown"} for e in attempts):
            blockers.append("An uncertain earlier SMS needs reconciliation")
        if len(attempts) >= min(2, settings.max_outreach_attempts):
            blockers.append("The recipient has reached the 30-day SMS attempt limit")
        if any(e.get("direction") == "inbound" for e in events):
            blockers.append("A recent seller reply requires personal follow-up")
    consent_disclosure = None
    receipts = sb.table("lead_form_submissions").select("raw_answers").eq("lead_id",str(lead_id)).order("created_at",desc=True).limit(1).execute().data or []
    if receipts:
        consent_disclosure = (receipts[0].get("raw_answers",{}).get("_sms_consent") or {}).get("disclosure")
    elif phone and not any("consent" in blocker.lower() for blocker in blockers):
        from tools.facebook_consent import SMS_DISCLOSURE
        consent_disclosure = SMS_DISCLOSURE
    jobs = sb.table("sms_nurture_jobs").select("*").eq("lead_id",str(lead_id)).order("created_at",desc=True).limit(1).execute().data or []
    text = TEMPLATE.format(name=lead.get("owner_first_name") or "there",address=lead.get("property_address") or "your property")
    if len(text) > 1600:
        blockers.append("Property inquiry details exceed the SMS length limit")
    return {"phone_number":phone,"blockers":blockers,"can_enroll":not blockers,"body":text,
            "schedule":"One follow-up after three days, during weekday Texas business hours. Stops on any reply or opt-out.",
            "consent_disclosure":consent_disclosure,"job":jobs[0] if jobs else None}

@router.get("/api/nurture/lead/{lead_id}")
async def readiness(lead_id: UUID):
    return await run_in_threadpool(_readiness, _db(), lead_id)


def _enroll(sb, lead_id, body, user_id):
    previous = sb.table("sms_nurture_jobs").select("*").eq("id",str(body.request_id)).limit(1).execute().data or []
    if previous:
        if str(previous[0]["lead_id"]) != str(lead_id):
            raise HTTPException(409,"Enrollment reference belongs to another lead")
        return previous[0]
    if not body.acknowledged:
        raise HTTPException(400,"Review the saved consent and follow-up before enrolling")
    state = _readiness(sb, lead_id)
    if state["blockers"]:
        raise HTTPException(409,"; ".join(state["blockers"]))
    try:
        saved = sb.table("sms_nurture_jobs").insert({"id":str(body.request_id),"lead_id":str(lead_id),
            "requested_by":user_id,"phone_number":state["phone_number"],"body":state["body"],
            "due_at":(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()}).execute().data
    except Exception as exc:
        raise HTTPException(409,"Enrollment could not be confirmed. Refresh before retrying; a recipient may already be enrolled.") from exc
    if not saved:
        raise HTTPException(503,"Enrollment was not confirmed; refresh before retrying")
    return saved[0]

@router.post("/api/nurture/lead/{lead_id}")
async def enroll(lead_id: UUID, body: Enrollment, request: Request):
    return await run_in_threadpool(_enroll,_db(),lead_id,body,request.state.user_id)

@router.post("/api/nurture/{job_id}/cancel")
async def cancel(job_id: UUID):
    saved = _db().table("sms_nurture_jobs").update({"status":"canceled","reason":"Canceled by operator"}).eq("id",str(job_id)).eq("status","scheduled").execute().data
    if not saved:
        raise HTTPException(409,"Job is already claimed or stopped; cancellation was not confirmed")
    return saved[0]


def _finish(sb, job, status, reason):
    saved = sb.table("sms_nurture_jobs").update({"status":status,"reason":reason}).eq("id",job["id"]).eq("status","processing").execute().data
    if not saved:
        raise RuntimeError("Nurture result was not confirmed; do not repeat sending")


def _drain(sb):
    # Never reclaim processing jobs. A crash after provider dispatch could have
    # reached the seller. Park aged claims for operator review instead.
    aged = sb.table("sms_nurture_jobs").update({"status":"review","reason":"Worker outcome unconfirmed; reconcile before retry"}).eq("status","processing").lt("claimed_at",(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()).execute().data or []
    for job in aged:
        record_provider_alert(sb,"twilio",job["id"],"unknown",job["lead_id"])
    sms = SMSClient()
    if not settings.sms_nurture_enabled or not sms._in_allowed_hours() or (settings.sms_weekend_blocked and sms._is_weekend()):
        return {"processed":0,"deferred":True,"aged_review":len(aged)}
    jobs = sb.rpc("claim_sms_nurture",{"p_limit":3}).execute().data
    if not isinstance(jobs,list):
        raise RuntimeError("Nurture claims could not be confirmed")
    for job in jobs:
        try:
            state = _readiness(sb,job["lead_id"])
            blockers = state["blockers"]
            if state["phone_number"] != job["phone_number"]:
                blockers.append("Recipient changed after enrollment")
            if state.get("body") != job["body"]:
                blockers.append("Property inquiry details changed after enrollment")
            if blockers:
                _finish(sb,job,"stopped","; ".join(blockers))
                continue
            message = OutreachMessage(id=job["id"],lead_id=job["lead_id"],channel=OutreachChannel.SMS,
                body=job["body"],compliance_cleared=True,is_followup=True,attempt_number=2)
            sms.send(message,job["phone_number"])
            rows = sb.table("sms_events").select("status").eq("id",job["id"]).limit(1).execute().data or []
            outcome = rows[0].get("status") if rows else None
            if outcome in SUCCESS:
                _finish(sb,job,"accepted","Provider accepted; delivery confirmed separately")
            elif outcome in {"submitting","unknown"}:
                _finish(sb,job,"review","Provider outcome uncertain; no automatic retry")
                record_provider_alert(sb,"twilio",job["id"],"unknown",job["lead_id"])
            else:
                _finish(sb,job,"stopped",message.compliance_notes or f"SMS was not accepted: {outcome or 'blocked'}")
        except Exception:
            # A failed database write remains processing and is parked on the
            # next run; it never makes the job eligible for another dispatch.
            record_provider_alert(sb,"twilio",job["id"],"unknown",job["lead_id"])
            raise
    return {"processed":len(jobs),"deferred":False,"aged_review":len(aged)}

@router.get("/webhooks/_worker/sms-nurture")
async def drain(request: Request):
    secret = os.getenv("CRON_SECRET","")
    if not secret:
        raise HTTPException(503,"Worker secret not configured")
    authorization = request.headers.get("authorization","")
    if not hmac.compare_digest(authorization,"Bearer "+secret):
        raise HTTPException(401,"Unauthorized")
    return await run_in_threadpool(_drain,_db())
