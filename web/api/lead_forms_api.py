"""
Lead Forms & Lead Generation Engine API.

Public (no auth):
  GET  /api/forms/{form_id}          → return active form config
  POST /api/forms/{form_id}/submit   → submit lead form, create lead, run qualification

Authenticated:
  GET  /api/lead-gen/campaigns                    → list ad campaigns
  POST /api/lead-gen/campaigns                    → create campaign
  PATCH /api/lead-gen/campaigns/{id}              → update campaign
  GET  /api/lead-gen/creatives/{campaign_id}      → list creatives for campaign
  POST /api/lead-gen/creatives                    → create creative
  PATCH /api/lead-gen/creatives/{id}              → update creative
  GET  /api/lead-gen/forms                        → list form configs
  POST /api/lead-gen/forms                        → create form config
  PATCH /api/lead-gen/forms/{id}                  → update form config
  GET  /api/lead-gen/submissions                  → list recent submissions
  GET  /api/lead-gen/kpis                         → KPI stats for dashboard
  POST /api/ai/lead-gen/optimize                  → run AI optimization analysis
  POST /api/ai/lead-gen/copy-variants             → generate copy variants
  POST /api/lead-gen/campaigns/{id}/sync-facebook → sync insights from FB API
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Optional
from uuid import UUID, NAMESPACE_URL, uuid5

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Lead Generation"])

# ── Supabase client (lazy import to avoid circular deps) ───────────────────────
def _get_supabase():
    from tools.crm import get_supabase_client
    client = get_supabase_client()
    if client is None:
        raise HTTPException(503, "Form service is temporarily unavailable")
    return client


def _validate_answers(questions: list[dict], answers: dict) -> dict:
    """Validate configured fields on the server, including checkbox consent."""
    cleaned = {}
    for question in questions:
        field = question["field_name"]
        value = answers.get(field, "")
        if not isinstance(value, (str, bool, int, float)):
            raise HTTPException(422, f"Invalid value for {question['label']}")
        kind = question.get("type", "text")
        if kind == "checkbox":
            value = "true" if value is True or value == "true" else ""
        else:
            value = str(value).strip()
        if question.get("required") and not value:
            raise HTTPException(422, f"{question['label']} is required")
        if len(value) > 5000:
            raise HTTPException(422, f"{question['label']} is too long")
        if value and kind == "tel" and not re.fullmatch(r"1?\d{10}", re.sub(r"\D", "", value)):
            raise HTTPException(422, "Enter a valid US phone number")
        if value and kind == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise HTTPException(422, "Enter a valid email address")
        if value and kind == "radio" and value not in {str(o["value"]) for o in question.get("options", [])}:
            raise HTTPException(422, f"Choose a valid option for {question['label']}")
        if value and kind == "number":
            try:
                valid_number = math.isfinite(float(value)) and float(value) >= 0
            except ValueError:
                valid_number = False
            if not valid_number:
                raise HTTPException(422, f"Enter a valid number for {question['label']}")
        cleaned[field] = value
    return cleaned


# ── Score mapping helpers ──────────────────────────────────────────────────────

MOTIVATION_SCORES: dict[str, int] = {
    "foreclosure": 3,
    "divorce": 3,
    "inherited": 3,
    "tired_landlord": 3,
    "relocation": 2,
    "repairs": 2,
    "other": 1,
}

TIMELINE_SCORES: dict[str, int] = {
    "asap": 3,
    "1_3mo": 2,
    "3_6mo": 1,
    "flexible": 1,
}

CONDITION_SCORES: dict[str, int] = {
    "major_repairs": 3,
    "cosmetic": 2,
    "good": 1,
}

MOTIVATION_TAGS: dict[str, str] = {
    "foreclosure": "Pre-Foreclosure",
    "divorce": "Divorce",
    "inherited": "Probate/Inherited",
    "tired_landlord": "Tired Landlord",
    "relocation": "Relocation",
    "repairs": "Distressed Property",
    "other": "Other",
}


def _compute_scores_from_answers(answers: dict) -> dict:
    """Map form answers to lead score fields."""
    motivation = answers.get("motivation", "other")
    timeline = answers.get("timeline", "flexible")
    condition = answers.get("condition", "good")
    occupancy = answers.get("occupancy", "owner")

    score_motivation = MOTIVATION_SCORES.get(motivation, 1)
    score_timeline = TIMELINE_SCORES.get(timeline, 1)
    score_condition = CONDITION_SCORES.get(condition, 1)
    # Default equity=2, flexibility=2 for inbound (unknown until skip-trace)
    score_equity = 2
    score_flexibility = 2

    # Vacancy bonus
    if occupancy == "vacant":
        score_motivation = min(3, score_motivation + 1)

    total = score_motivation + score_timeline + score_equity + score_condition + score_flexibility

    # Tier: A>=13, B>=8, C otherwise
    if total >= 13:
        priority_tier = "A"
    elif total >= 8:
        priority_tier = "B"
    else:
        priority_tier = "C"

    return {
        "score_motivation": score_motivation,
        "score_timeline": score_timeline,
        "score_equity": score_equity,
        "score_condition": score_condition,
        "score_flexibility": score_flexibility,
        "priority_tier": priority_tier,
        "motivation_tag": MOTIVATION_TAGS.get(motivation, "Other"),
    }


# ── Public form endpoints ──────────────────────────────────────────────────────

def _load_active_form(supabase, form_id: str) -> dict:
    """A missing row is a 404; a failed database lookup is a retryable outage."""
    try:
        UUID(form_id)
        field = "id"
    except ValueError:
        field = "slug"
    try:
        response = (supabase.table("lead_form_configs").select("*")
                    .eq(field, form_id).eq("active", True).limit(1).execute())
    except Exception:
        logger.exception("[lead_forms] active configuration lookup failed")
        raise HTTPException(503, "Form service is temporarily unavailable. Please try again.",
                            headers={"Retry-After": "30"}) from None
    if not response.data:
        raise HTTPException(404, "Form not found or inactive")
    return response.data[0]


@router.get("/api/forms/{form_id}")
async def get_form_config(form_id: str):
    return _load_active_form(_get_supabase(), form_id)


class FormSubmitRequest(BaseModel):
    answers: dict[str, Any]
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/api/forms/{form_id}/submit")
async def submit_form(
    form_id: str,
    body: FormSubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Public — submit lead qualification form.
    Creates a lead_form_submission, then in background:
    - creates a leads row
    - persists the deterministic form qualification scores and classification
    """
    supabase = _get_supabase()

    form_config = _load_active_form(supabase, form_id)

    answers = _validate_answers(form_config.get("questions", []), body.answers)
    scores = _compute_scores_from_answers(answers)

    # Insert submission record
    submission_data = {
        "form_id": form_config["id"],
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "utm_source": body.utm_source,
        "utm_medium": body.utm_medium,
        "utm_campaign": body.utm_campaign,
        "raw_answers": answers,
        "computed_motivation_tag": scores.get("motivation_tag"),
        "computed_timeline": answers.get("timeline"),
        "computed_condition": answers.get("condition"),
        "processing_status": "pending",
    }
    try:
        sub_resp = supabase.table("lead_form_submissions").insert(submission_data).execute()
        submission_id = sub_resp.data[0]["id"] if sub_resp.data else None
    except Exception as exc:
        logger.error(f"Failed to insert form submission: {exc}")
        raise HTTPException(503, "We could not save your inquiry. Please try again.")

    if not submission_id:
        raise HTTPException(503, "We could not save your inquiry. Please try again.")

    # Finish durable CRM work before acknowledging the inquiry.
    await _process_form_submission(
        form_config=form_config,
        answers=answers,
        scores=scores,
        submission_id=submission_id,
        utm_campaign=body.utm_campaign,
    )

    return {
        "success": True,
        "message": form_config.get("thank_you_message", "Thank you! We'll be in touch shortly."),
        "redirect_url": form_config.get("redirect_url"),
    }


async def _process_form_submission(
    form_config: dict,
    answers: dict,
    scores: dict,
    submission_id: Optional[str],
    utm_campaign: Optional[str],
    deliver_notifications: bool = True,
):
    """Persist lead and task atomically, then attempt optional notifications."""
    supabase = _get_supabase()

    # Build lead record from answers
    address_parts = answers.get("property_address", "").split(",")
    property_address = address_parts[0].strip() if address_parts else answers.get("property_address", "")
    city = address_parts[1].strip() if len(address_parts) > 1 else ""
    state_zip = address_parts[2].strip() if len(address_parts) > 2 else ""
    state = state_zip.split()[0] if state_zip else "TX"
    zip_code = state_zip.split()[-1] if state_zip and len(state_zip.split()) > 1 else ""

    # Phone normalization
    phone = answers.get("phone", "").strip()
    digits = re.sub(r"\D", "", phone)
    if re.fullmatch(r"1?\d{10}", digits):
        phone = "+1" + digits[-10:]

    asking_price = None
    raw_price = answers.get("asking_price")
    if raw_price:
        try:
            asking_price = float(str(raw_price).replace(",", "").replace("$", ""))
        except (ValueError, TypeError):
            pass

    total_score = sum(scores[field] for field in (
        "score_motivation", "score_timeline", "score_equity",
        "score_condition", "score_flexibility",
    ))
    classification = "hot" if total_score >= 13 else "warm" if total_score >= 8 else "cold"

    lead_data = {
        "property_address": property_address or answers.get("property_address", "Unknown"),
        "city": city or "",
        "state": state or "TX",
        "zip_code": zip_code or "",
        "owner_first_name": answers.get("first_name", ""),
        "owner_last_name": answers.get("last_name", ""),
        "owner_phone_1": phone,
        "owner_email": answers.get("email", ""),
        "source": "web_form",
        "inbound_channel": "web_form",
        "status": f"qualified_{classification}",
        "precision_tier": {"hot": 1, "warm": 2, "cold": 3}[classification],
        "ai_qualification_summary": (
            f"Form-answer qualification: {classification.upper()} ({total_score}/15). "
            f"Motivation: {answers.get('motivation', 'not provided')}; "
            f"timeline: {answers.get('timeline', 'not provided')}; "
            f"condition: {answers.get('condition', 'not provided')}. "
            "Equity and flexibility use neutral defaults pending verification."
        ),
        "score_motivation": scores["score_motivation"],
        "score_timeline": scores["score_timeline"],
        "score_equity": scores["score_equity"],
        "score_condition": scores["score_condition"],
        "score_flexibility": scores["score_flexibility"],
        "priority_tier": scores["priority_tier"],
        "motivation_tag": scores["motivation_tag"],
        "asking_price": asking_price,
        "contact_attempts": 0,
        "sms_sequence_active": False,
        "email_sequence_active": False,
        "dnc": False,
    }
    if submission_id:
        lead_data["form_submission_id"] = submission_id
    if form_config.get("campaign_id"):
        lead_data["ad_campaign_id"] = form_config["campaign_id"]

    created = True
    try:
        if submission_id:
            result = supabase.rpc("finalize_form_submission", {
                "p_submission_id": submission_id, "p_lead": lead_data,
            }).execute().data
            lead_id = result.get("lead_id") if isinstance(result, dict) else None
            created = bool(result.get("created")) if isinstance(result, dict) else False
        else:
            lead_resp = supabase.table("leads").insert(lead_data).execute()
            lead_id = lead_resp.data[0]["id"] if lead_resp.data else None
        if not lead_id:
            raise RuntimeError("Lead finalization returned no saved lead")
    except Exception:
        logger.exception("Failed to finalize saved form inquiry %s", submission_id)
        # The pending receipt remains recoverable; do not advise a duplicate submission.
        raise HTTPException(503, "Your inquiry was saved, but follow-up is delayed. Please contact us before resubmitting.") from None

    if not deliver_notifications or not created:
        return lead_id

    # Speed-to-lead SMS: confirmation text to the seller (if opted in) plus an
    # immediate internal alert to the owner, on every new web-form lead —
    # not gated on score, unlike the HOT-lead escalation below. Runs first,
    # right after the lead exists, so it isn't delayed by the agent calls.
    if lead_id:
        try:
            _send_lead_pipeline_sms(
                lead_id=lead_id,
                answers={**answers, "sms_opt_in": answers.get("sms_opt_in") if form_config.get("send_confirmation_sms", True) else False},
                phone=phone,
                property_address=property_address,
            )
        except Exception as exc:
            logger.error(f"Speed-to-lead SMS failed for lead {lead_id}: {exc}")

    # Form answers are scored above by _compute_scores_from_answers. Transcript
    # qualification and the separate distress-stacking agent require different
    # inputs; neither exposes a run(lead_id=...) method.

    # HOT lead notification (A-tier or score >= 13)
    if total_score >= 13 and lead_id:
        try:
            _send_hot_lead_notification(lead_id, answers, total_score)
        except Exception as exc:
            logger.error(f"HOT lead notification failed: {exc}")

    logger.info(f"Form submission processed → lead {lead_id} (score={total_score}, tier={scores['priority_tier']})")
    return lead_id


from tools.email_client import EmailClient
from tools.sms_client import SMSClient
from schemas.outreach import OutreachChannel, OutreachMessage


def _send_lead_pipeline_sms(
    lead_id: str,
    answers: dict,
    phone: str,
    property_address: str,
    source: str = "web_form",
):
    """Persist an operator alert before attempting optional SMS delivery.

    Delivery outcomes are retained for manual reconciliation, never auto-replayed:
    a provider exception can mean delivery succeeded but its response was lost.
    """
    from config.settings import settings

    supabase = _get_supabase()
    notification_id = str(uuid5(NAMESPACE_URL, f"wholesaleos:intake-alert:{lead_id}"))
    notification = {
        "id": notification_id, "recipient_role": "admin", "type": "pipeline_step",
        "title": "New inquiry — follow-up required",
        "body": f"{property_address} — source: {source}. Review the lead and assign follow-up.",
        "action_url": "/leads", "lead_id": lead_id,
        "metadata": {"source": source, "seller_sms": "unresolved", "owner_sms": "unresolved"},
    }
    claim = supabase.table("app_notifications").upsert(
        notification, on_conflict="id", ignore_duplicates=True,
    ).execute()
    if not claim.data:
        # A prior attempt may have sent externally. Never resend on ambiguous receipt.
        existing = supabase.table("app_notifications").select("id").eq("id", notification_id).limit(1).execute()
        if existing.data:
            return
        raise RuntimeError("Intake notification persistence was not confirmed")

    outcomes = notification["metadata"].copy()
    name = str(answers.get("first_name") or "").strip() or "there"
    sms_client = SMSClient()

    def _send(to_number: str, body: str) -> str:
        if not to_number:
            return "not_configured"
        message = OutreachMessage(lead_id=lead_id, channel=OutreachChannel.SMS,
                                  body=body, is_inbound_reply=True, compliance_cleared=True)
        try:
            accepted = sms_client.send(message, to_number)
        except Exception:
            logger.exception("[lead_forms] SMS outcome unknown for lead %s", lead_id)
            return "unknown"
        if message.a2p_provider.endswith(":dry-run"):
            return "dry_run"
        return "accepted" if accepted else "failed_or_blocked"

    # Preserve uncertainty: a failed duplicate/suppression lookup must not enable a send.
    seller_allowed = False
    is_duplicate = False
    raw_consent = answers.get("sms_opt_in")
    opted_in = raw_consent is True or str(raw_consent).strip().lower() in {
        "1", "true", "yes", "on", "agree", "agreed", "opted_in",
    }
    if opted_in and phone:
        try:
            current = supabase.table("leads").select("dnc").eq("id", lead_id).single().execute()
            status = supabase.rpc("intake_phone_status", {
                "p_phone": phone, "p_lead": lead_id, "p_property": property_address,
            }).execute().data
            if not isinstance(status, dict) or not all(isinstance(status.get(key), bool) for key in ("suppressed", "duplicate")):
                raise RuntimeError("Suppression status was not confirmed")
            is_duplicate = status["duplicate"]
            seller_allowed = bool(current.data and current.data.get("dnc") is False
                                  and not status["suppressed"] and not is_duplicate)
            outcomes["seller_sms"] = "suppressed_or_duplicate" if not seller_allowed else "not_attempted"
        except Exception:
            outcomes["seller_sms"] = "suppression_check_failed"
            logger.exception("[lead_forms] seller SMS blocked: safety lookup failed for %s", lead_id)
    else:
        outcomes["seller_sms"] = "no_consent_or_phone"

    # Internal notification is already saved even when this SMS is blocked after hours.
    prefix = "Repeat inquiry" if is_duplicate else "New lead"
    outcomes["owner_sms"] = _send(settings.owner_alert_phone_number,
                                 f"{prefix}: {name} — {property_address} — {phone}. Source: {source}.")
    if seller_allowed:
        outcomes["seller_sms"] = _send(
            phone, f"Hi {name}, thanks for reaching out to Hilltop Home Co. about "
            f"{property_address}. We'll be in touch shortly. Reply STOP to opt out.",
        )
    summary = (f"{property_address} — source: {source}. "
               f"Owner SMS: {outcomes['owner_sms']}; seller SMS: {outcomes['seller_sms']}. "
               "Review the lead and assign follow-up. Accepted does not confirm delivery.")
    saved = supabase.table("app_notifications").update(
        {"metadata": outcomes, "body": summary},
    ).eq("id", notification_id).execute()
    if not saved.data:
        raise RuntimeError("Intake SMS outcome persistence was not confirmed; reconcile before retry")


def _send_hot_lead_notification(lead_id: str, answers: dict, score: int):
    """Send in-app notification and email alert for HOT inbound lead."""
    from config.settings import settings
    supabase = _get_supabase()
    name = f"{answers.get('first_name', '')} {answers.get('last_name', '')}".strip() or "Unknown"
    address = answers.get('property_address', 'Unknown address')
    body = (
        f"Score {score}/15 | {answers.get('motivation', 'unknown')} | "
        f"{answers.get('timeline', 'unknown')} | {address}"
    )

    try:
        supabase.table("app_notifications").insert({
            "recipient_role": "admin",
            "type": "hot_lead",
            "title": f"🔥 HOT Inbound Lead — {name}",
            "body": body,
            "action_url": "/acquisitions",
            "lead_id": lead_id,
        }).execute()
    except Exception as exc:
        logger.warning(f"Could not insert HOT lead notification: {exc}")

    # Email Alert (Immediate)
    if settings.notification_email:
        try:
            email_client = EmailClient()
            subject = f"🔥 HOT INBOUND LEAD — {address}"
            accepted = email_client.send(
                to_email=settings.notification_email,
                subject=subject,
                body=f"{subject}\n\n{body}\n\nView Lead: https://wholesale-automation.vercel.app/acquisitions?lead={lead_id}",
                html_body=f"<h2>{escape(subject)}</h2><p>{escape(body)}</p><p><a href='https://wholesale-automation.vercel.app/acquisitions?lead={lead_id}'>View Lead in Dashboard</a></p>",
            )
            logger.info("HOT lead email alert provider acceptance: %s", accepted)
        except Exception as exc:
            logger.error(f"HOT lead email alert failed: {exc}")


# ── Authenticated campaign/creative/form endpoints ─────────────────────────────

@router.get("/api/lead-gen/campaigns")
async def list_campaigns():
    supabase = _get_supabase()
    resp = supabase.table("ad_campaigns").select("*").order("created_at", desc=True).execute()
    return resp.data or []


class CreateCampaignRequest(BaseModel):
    name: str
    platform: str = "facebook"
    status: str = "draft"
    campaign_objective: str = "lead_generation"
    daily_budget: Optional[float] = None
    target_zip_codes: Optional[list[str]] = None
    target_audience_notes: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/api/lead-gen/campaigns")
async def create_campaign(body: CreateCampaignRequest):
    supabase = _get_supabase()
    data = body.model_dump(exclude_none=True)
    resp = supabase.table("ad_campaigns").insert(data).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/lead-gen/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, body: dict):
    supabase = _get_supabase()
    resp = supabase.table("ad_campaigns").update(body).eq("id", campaign_id).execute()
    return resp.data[0] if resp.data else {}


@router.get("/api/lead-gen/creatives/{campaign_id}")
async def list_creatives(campaign_id: str):
    supabase = _get_supabase()
    resp = supabase.table("ad_creatives").select("*").eq("campaign_id", campaign_id).order("created_at", desc=True).execute()
    return resp.data or []


class CreateCreativeRequest(BaseModel):
    campaign_id: str
    name: str
    headline: Optional[str] = None
    primary_text: Optional[str] = None
    cta_text: str = "Get My Cash Offer"
    pain_point_angle: Optional[str] = None
    image_url: Optional[str] = None


@router.post("/api/lead-gen/creatives")
async def create_creative(body: CreateCreativeRequest):
    supabase = _get_supabase()
    data = body.model_dump(exclude_none=True)
    resp = supabase.table("ad_creatives").insert(data).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/lead-gen/creatives/{creative_id}")
async def update_creative(creative_id: str, body: dict):
    supabase = _get_supabase()
    resp = supabase.table("ad_creatives").update(body).eq("id", creative_id).execute()
    return resp.data[0] if resp.data else {}


@router.get("/api/lead-gen/forms")
async def list_forms():
    supabase = _get_supabase()
    resp = supabase.table("lead_form_configs").select("*").order("created_at", desc=True).execute()
    return resp.data or []


class CreateFormRequest(BaseModel):
    name: str
    slug: str
    campaign_id: Optional[str] = None
    headline: str = "Get a Fair Cash Offer"
    subheadline: Optional[str] = None
    brand_color: str = "#1B3A5C"
    thank_you_message: Optional[str] = None
    send_confirmation_sms: bool = True
    active: bool = True
    questions: list = []
    redirect_url: Optional[str] = None


@router.post("/api/lead-gen/forms")
async def create_form(body: CreateFormRequest):
    supabase = _get_supabase()
    data = body.model_dump(exclude_none=True)
    resp = supabase.table("lead_form_configs").insert(data).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/lead-gen/forms/{form_id}")
async def update_form(form_id: str, body: dict):
    supabase = _get_supabase()
    resp = supabase.table("lead_form_configs").update(body).eq("id", form_id).execute()
    return resp.data[0] if resp.data else {}


@router.post("/api/lead-gen/submissions/{submission_id}/recover")
async def recover_form_submission(submission_id: UUID, request: Request):
    """Admin recovery creates CRM records only; never replays provider sends."""
    supabase = _get_supabase()
    user_id = getattr(request.state, "user_id", None)
    profile = supabase.table("profiles").select("role,status").eq("id", user_id).limit(1).execute().data if user_id else []
    if not profile or profile[0].get("role") != "admin" or profile[0].get("status") != "approved":
        raise HTTPException(403, "Administrator access required")
    rows = supabase.table("lead_form_submissions").select("*").eq("id", str(submission_id)).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Submission not found")
    receipt = rows[0]
    answers = receipt.get("raw_answers") or {}
    # Process the stored, previously validated receipt even if its form was disabled.
    lead_id = await _process_form_submission({}, answers, _compute_scores_from_answers(answers),
        str(submission_id), receipt.get("utm_campaign"), deliver_notifications=False)
    return {"success": True, "lead_id": lead_id, "provider_messages_replayed": False}


@router.get("/api/lead-gen/submissions")
async def list_submissions(limit: int = 50, form_id: Optional[str] = None):
    supabase = _get_supabase()
    query = supabase.table("lead_form_submissions").select(
        "*, lead_form_configs(name, slug), leads(status, priority_tier)"
    ).order("created_at", desc=True).limit(limit)
    if form_id:
        query = query.eq("form_id", form_id)
    resp = query.execute()
    return resp.data or []


@router.get("/api/lead-gen/kpis")
async def get_lead_gen_kpis():
    """Return KPI summary for the Lead Engine dashboard."""
    supabase = _get_supabase()

    from datetime import date, timedelta
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    try:
        # Leads today (inbound only)
        today_resp = supabase.table("leads").select("id", count="exact").not_.is_("inbound_channel", "null").gte("created_at", today).execute()
        leads_today = today_resp.count or 0

        # Leads this week
        week_resp = supabase.table("leads").select("id", count="exact").not_.is_("inbound_channel", "null").gte("created_at", week_ago).execute()
        leads_week = week_resp.count or 0

        # HOT inbound leads (A tier)
        hot_resp = supabase.table("leads").select("id", count="exact").not_.is_("inbound_channel", "null").eq("priority_tier", "A").execute()
        hot_leads = hot_resp.count or 0

        # Total campaign spend
        campaigns_resp = supabase.table("ad_campaigns").select("total_spend, leads_count").execute()
        total_spend = sum(float(c.get("total_spend") or 0) for c in (campaigns_resp.data or []))
        total_campaign_leads = sum(int(c.get("leads_count") or 0) for c in (campaigns_resp.data or []))
        avg_cpl = total_spend / total_campaign_leads if total_campaign_leads > 0 else 0

        # Avg lead quality from inbound leads
        quality_resp = supabase.table("leads").select("seller_score").not_.is_("inbound_channel", "null").not_.is_("seller_score", "null").execute()
        scores = [float(r["seller_score"]) for r in (quality_resp.data or []) if r.get("seller_score")]
        avg_quality = sum(scores) / len(scores) if scores else 0

        return {
            "leads_today": leads_today,
            "leads_week": leads_week,
            "hot_leads": hot_leads,
            "avg_cpl": round(avg_cpl, 2),
            "avg_lead_quality": round(avg_quality, 1),
            "total_spend": round(total_spend, 2),
            "cost_per_contract_est": round(avg_cpl * 125, 2) if avg_cpl > 0 else 0,
        }
    except Exception as exc:
        logger.error(f"get_lead_gen_kpis error: {exc}")
        return {"leads_today": 0, "leads_week": 0, "hot_leads": 0, "avg_cpl": 0, "avg_lead_quality": 0, "total_spend": 0, "cost_per_contract_est": 0}


# ── AI endpoints ───────────────────────────────────────────────────────────────

@router.post("/api/ai/lead-gen/optimize")
async def run_optimization():
    """Run AI optimization analysis on current campaigns and creatives."""
    supabase = _get_supabase()

    campaigns_resp = supabase.table("ad_campaigns").select("*").execute()
    creatives_resp = supabase.table("ad_creatives").select("*").execute()

    from agents.lead_generation_agent import LeadGenerationAgent
    agent = LeadGenerationAgent()
    report = agent.analyze_campaign_performance(
        campaigns=campaigns_resp.data or [],
        creatives=creatives_resp.data or [],
    )
    return report.model_dump()


class CopyVariantsRequest(BaseModel):
    pain_point_angle: str
    market: str = "Texas"
    num_variants: int = 5


@router.post("/api/ai/lead-gen/copy-variants")
async def generate_copy_variants(body: CopyVariantsRequest):
    """Generate HomeVestors-style ad copy variants."""
    from agents.lead_generation_agent import LeadGenerationAgent
    agent = LeadGenerationAgent()
    variants = agent.generate_ad_copy_variants(
        pain_point_angle=body.pain_point_angle,
        market=body.market,
        num_variants=body.num_variants,
    )
    return {"variants": [v.model_dump() for v in variants]}


@router.post("/api/lead-gen/campaigns/{campaign_id}/sync-facebook")
async def sync_campaign_from_facebook(campaign_id: str):
    """Sync campaign insights from Facebook Marketing API."""
    supabase = _get_supabase()

    # Get campaign to get external_campaign_id
    resp = supabase.table("ad_campaigns").select("*").eq("id", campaign_id).single().execute()
    campaign = resp.data
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    external_id = campaign.get("external_campaign_id")
    if not external_id:
        raise HTTPException(status_code=400, detail="Campaign has no external_campaign_id set")

    from config.settings import settings
    from tools.facebook_ads_adapter import FacebookAdsAdapter
    adapter = FacebookAdsAdapter(
        app_secret=settings.facebook_app_secret,
        access_token=settings.facebook_access_token,
        webhook_verify_token=settings.facebook_webhook_verify_token,
        ad_account_id=settings.facebook_ad_account_id,
    )
    insights = adapter.sync_campaign_insights(external_id)
    if not insights:
        raise HTTPException(status_code=502, detail="Failed to fetch insights from Facebook")

    update_data = {
        "impressions": insights["impressions"],
        "clicks": insights["clicks"],
        "total_spend": insights["spend"],
        "leads_count": insights["leads_count"],
    }
    supabase.table("ad_campaigns").update(update_data).eq("id", campaign_id).execute()
    return {"synced": True, **update_data}
