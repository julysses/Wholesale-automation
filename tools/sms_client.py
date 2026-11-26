"""
SMS Client — provider-agnostic compliant message delivery.

Enforces Sections 4 & 5 rules:
- Texas allowed hours: 9:00am – 7:00pm CT
- No SMS on weekends (unless inbound-initiated)
- Compliance clearance required before every send
- Approved A2P 10DLC providers: Twilio, Telnyx, MessageBird
- MANDATORY: if compliance is uncertain, do not send

Live dispatch: Twilio only. Legacy Telnyx/MessageBird providers remain disabled
until equivalent consent, suppression, durable claims and receipt checks exist.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import NAMESPACE_URL, uuid5

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from config.settings import settings
from schemas.outreach import APPROVED_SMS_PROVIDERS, OutreachMessage
from tools.facebook_consent import matching_native_consent, normalize_us_phone
from tools.operational_alerts import record_provider_alert
from tools.twilio_receipts import reconcile_twilio_receipt

logger = logging.getLogger(__name__)

TEXAS_TZ = "America/Chicago"
CONFIRMED_SUPPRESSION = "Confirmed phone or lead suppression"
SMS_OUTCOME_REASONS = {
    "compliance_not_cleared": "Compliance review has not cleared this message",
    "outside_contact_hours": "Outside configured contact hours",
    "weekend_contact_blocked": "Weekend contact is blocked for this message",
    "invalid_phone": "The recipient phone number is invalid",
    "credentials_missing": "SMS credentials are not configured",
    "sending_disabled": "Live SMS sending is paused",
    "provider_not_ready": "The selected provider has not completed delivery setup",
    "recipient_not_allowed": "The recipient is outside the approved launch list",
    "sender_route_not_configured": "The SMS sender route or callback is not configured",
    "receipt_store_unavailable": "The message receipt store is unavailable",
    "confirmed_suppression": "The phone or lead has a confirmed suppression",
    "consent_or_suppression_hold": "Consent or suppression checks require review",
    "dispatch_claim_unconfirmed": "Dispatch claim was not confirmed; review before retry",
    "dispatch_unconfirmed": "Provider outcome is unconfirmed; reconcile before retry",
    "provider_failed": "The provider reported a delivery failure",
    "provider_receipt_unconfirmed": "The provider receipt requires reconciliation",
    "provider_accepted": "The provider accepted the message; delivery is tracked separately",
}


def _sms_outcome(message: OutreachMessage, outcome: str, reason: str) -> bool:
    message.sms_outcome = outcome
    message.sms_reason = reason
    if outcome == "blocked":
        message.mark_stopped(SMS_OUTCOME_REASONS[reason])
    return outcome == "accepted"



def _texas_now() -> datetime:
    try:
        tz = ZoneInfo(settings.texas_timezone)
    except Exception:
        tz = ZoneInfo(TEXAS_TZ)
    return datetime.now(tz=tz)


def sms_consent_blocker(sb, lead_id: str, to_number: str) -> str | None:
    # This registration covers consented property inquiries only, not owner
    # alerts or buyer-list blasts. Require a matching durable form receipt.
    rows = sb.table("lead_form_submissions").select("raw_answers").eq(
        "lead_id", str(lead_id)).order("created_at", desc=True).limit(1).execute().data
    answers = rows[0].get("raw_answers", {}) if rows else {}
    authorized = False
    if rows:
        # A recorded website refusal must never fall back to older consent.
        consent = answers.get("_sms_consent", {})
        try:
            authorized = (consent.get("accepted") is True and consent.get("rendered_disclosure_matches") is True
                          and normalize_us_phone(answers.get("phone")) == to_number)
        except ValueError:
            pass
    else:
        leads = sb.table("leads").select("source,internal_notes,owner_phone_1,property_address,dnc").eq(
            "id", str(lead_id)).limit(1).execute().data
        lead = leads[0] if leads else {}
        if lead.get("source") == "facebook_lead_ad" and lead.get("dnc") is False:
            native = sb.table("facebook_lead_submissions").select("raw_answers").eq(
                "lead_id", str(lead_id)).limit(2).execute().data or []
            notice_id = str(uuid5(NAMESPACE_URL, f"wholesaleos:intake-alert:{lead_id}"))
            notices = sb.table("app_notifications").select("metadata").eq("id", notice_id).limit(1).execute().data
            metadata = notices[0].get("metadata", {}) if notices else {}
            if native:
                # New native inquiries use immutable evidence, never editable alert metadata.
                authorized = len(native) == 1 and matching_native_consent(
                    native[0].get("raw_answers", {}).get("_facebook_consent"), to_number, lead, "sms")
            else:
                # Preserve historical direct-Twilio consent; this cannot enqueue
                # a new Retell job without an immutable native submission.
                authorized = (metadata.get("source") == "facebook_lead_ad"
                              and matching_native_consent(metadata.get("consent_receipt"), to_number, lead, "sms"))
            answers = {"property_address": lead.get("property_address", "")}
    if not authorized:
        return "No matching property inquiry consent receipt"
    safety = sb.rpc("intake_phone_status", {"p_phone": to_number,
        "p_lead": str(lead_id), "p_property": answers.get("property_address", "")}).execute().data
    if isinstance(safety, dict) and safety.get("suppressed") is True:
        return CONFIRMED_SUPPRESSION
    if not isinstance(safety, dict) or safety.get("suppressed") is not False:
        return "Suppression lookup blocked sending"
    return None


class SMSClient:
    """
    Provider-agnostic SMS client with mandatory compliance guards.

    Will NOT send if:
    - message.compliance_cleared is False
    - Outside Texas allowed hours (9am–7pm CT)
    - Weekend (Sat/Sun) and not inbound-initiated
    - No valid phone number
    - Provider not in approved A2P 10DLC list

    Live provider: twilio. Other provider configurations fail closed.
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        self._provider = (provider or settings.sms_provider).lower()

        if self._provider not in APPROVED_SMS_PROVIDERS:
            logger.error(
                f"[SMSClient] Provider '{self._provider}' is not an approved A2P 10DLC provider. "
                f"Approved: {sorted(APPROVED_SMS_PROVIDERS)}. Running in dry-run mode."
            )
            self._configured = False
        else:
            self._configured = self._check_provider_credentials()

        if not self._configured:
            logger.warning(
                f"[SMSClient] Provider '{self._provider}' credentials not configured — "
                "running in dry-run mode"
            )

    def _check_provider_credentials(self) -> bool:
        if self._provider == "twilio":
            return bool(
                settings.twilio_account_sid
                and settings.twilio_auth_token
                and settings.twilio_from_number
            )
        if self._provider == "telnyx":
            return bool(settings.telnyx_api_key)
        if self._provider == "messagebird":
            return bool(settings.messagebird_api_key)
        return False

    # ── Texas scheduling checks (Section 5) ──────────────────────────────────

    def _in_allowed_hours(self) -> bool:
        """9:00am – 7:00pm Texas CT."""
        now = _texas_now()
        return settings.tcpa_allowed_start_hour <= now.hour < settings.tcpa_allowed_end_hour

    def _is_weekend(self) -> bool:
        """Saturday (5) or Sunday (6) in Texas local time."""
        return _texas_now().weekday() >= 5

    # ── Send ──────────────────────────────────────────────────────────────────

    def send(
        self,
        message: OutreachMessage,
        to_number: str,
    ) -> bool:
        """
        Attempt to send an SMS. Returns True only when the provider accepts the message.
        All compliance guards are enforced before sending.
        """
        # Guard 1: compliance clearance
        if not message.compliance_cleared:
            logger.error(
                f"[SMSClient] BLOCKED msg {message.id}: not compliance cleared"
            )
            return _sms_outcome(message, "blocked", "compliance_not_cleared")

        # Guard 2: Texas allowed hours (9am–7pm CT)
        if not self._in_allowed_hours():
            now = _texas_now()
            logger.warning(
                f"[SMSClient] BLOCKED msg {message.id}: outside allowed hours "
                f"(current Texas time: {now.strftime('%H:%M %Z')})"
            )
            return _sms_outcome(message, "blocked", "outside_contact_hours")

        # Guard 3: weekend SMS block (unless inbound-initiated)
        if (
            settings.sms_weekend_blocked
            and self._is_weekend()
            and not message.is_inbound_reply
        ):
            logger.warning(
                f"[SMSClient] BLOCKED msg {message.id}: weekend SMS blocked "
                f"({_texas_now().strftime('%A')}). Only allowed if seller initiated."
            )
            return _sms_outcome(message, "blocked", "weekend_contact_blocked")

        # Guard 4: valid phone number
        to_number = to_number.strip()
        if not to_number or len(to_number) < 10:
            logger.error(f"[SMSClient] BLOCKED invalid phone: {to_number!r}")
            return _sms_outcome(message, "blocked", "invalid_phone")

        # Missing credentials never count as a send. Twilio stays disabled until
        # carrier approval and controlled delivery acceptance are complete.
        if not self._configured:
            return _sms_outcome(message, "blocked", "credentials_missing")
        if not settings.sms_live_enabled:
            return _sms_outcome(message, "blocked", "sending_disabled")

        if self._provider != "twilio":
            return _sms_outcome(message, "blocked", "provider_not_ready")

        return self._dispatch(message, to_number)

    def _dispatch(self, message: OutreachMessage, to_number: str) -> bool:
        """Route to the correct provider SDK."""
        try:
            if self._provider == "twilio":
                return self._send_twilio(message, to_number)
            logger.error(f"[SMSClient] Unknown provider: {self._provider}")
            return _sms_outcome(message, "blocked", "provider_not_ready")
        except Exception as exc:
            logger.error("[SMSClient] Dispatch outcome unconfirmed for msg %s (%s)", message.id, type(exc).__name__)
            return _sms_outcome(message, "unknown", "dispatch_unconfirmed")

    def _send_twilio(self, message: OutreachMessage, to_number: str) -> bool:
        from twilio.rest import Client
        from twilio.http.http_client import TwilioHttpClient
        from tools.crm import get_supabase_client

        if not settings.sms_live_enabled:
            return _sms_outcome(message, "blocked", "sending_disabled")
        try:
            to_number = normalize_us_phone(to_number)
        except ValueError:
            return _sms_outcome(message, "blocked", "invalid_phone")
        if settings.sms_allowed_recipients:
            allowed = {number.strip() for number in settings.sms_allowed_recipients.split(',') if number.strip()}
            if to_number not in allowed:
                return _sms_outcome(message, "blocked", "recipient_not_allowed")
        base = settings.twilio_webhook_base_url.rstrip("/")
        if not base.startswith("https://") or not settings.twilio_messaging_service_sid:
            return _sms_outcome(message, "blocked", "sender_route_not_configured")
        sb = get_supabase_client()
        if sb is None:
            return _sms_outcome(message, "blocked", "receipt_store_unavailable")
        blocker = sms_consent_blocker(sb, str(message.lead_id), to_number)
        if blocker:
            return _sms_outcome(message, "blocked", "confirmed_suppression" if blocker == CONFIRMED_SUPPRESSION else "consent_or_suppression_hold")
        claim = sb.rpc("claim_twilio_sms", {"p_id": str(message.id), "p_lead": str(message.lead_id),
            "p_phone": to_number, "p_body": message.body}).execute().data
        if not isinstance(claim, dict) or claim.get("claimed") is not True:
            return _sms_outcome(message, "unknown", "dispatch_claim_unconfirmed")  # Never replay an ambiguous or duplicate attempt.
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token,
            http_client=TwilioHttpClient(timeout=5, max_retries=0))
        try:
            result = client.messages.create(body=message.body, from_=settings.twilio_from_number,
                messaging_service_sid=settings.twilio_messaging_service_sid, to=to_number,
                status_callback=f"{base}/webhooks/twilio/status?message_id={message.id}")
        except Exception:
            # A delivery callback may have arrived while the HTTP request timed
            # out. Only an untouched submitting claim becomes unknown.
            parked = sb.table("sms_events").update({"status": "unknown"}).eq("id", str(message.id)).eq("status", "submitting").execute()
            if not parked.data:
                rows = sb.table("sms_events").select("status,raw_payload").eq("id", str(message.id)).limit(1).execute().data
                receipt = rows[0] if rows else {}
                sid = (receipt.get("raw_payload") or {}).get("provider_sid")
                if sid and receipt.get("status") in {"accepted", "scheduled", "queued", "sending", "sent", "delivered", "read"}:
                    message.provider_message_id = sid
                    message.mark_sent()
                    message.a2p_provider = "twilio"
                    return _sms_outcome(message, "accepted", "provider_accepted")  # Verified callback confirms acceptance.
                if sid and receipt.get("status") in {"failed", "undelivered", "canceled"}:
                    message.provider_message_id = sid
                    return _sms_outcome(message, "failed", "provider_failed")
            record_provider_alert(sb, 'twilio', str(message.id), 'unknown', message.lead_id)
            raise
        message.provider_message_id = result.sid
        try:
            outcome = reconcile_twilio_receipt(sb, str(message.id), to_number, result.sid, "accepted")
        except Exception:
            record_provider_alert(sb, 'twilio', str(message.id), 'unknown', message.lead_id)
            raise RuntimeError("Provider accepted SMS but local receipt is unconfirmed; reconcile before retry")
        if outcome in {"failed", "undelivered", "canceled"}:
            return _sms_outcome(message, "failed", "provider_failed")
        if outcome == "unknown":
            return _sms_outcome(message, "unknown", "provider_receipt_unconfirmed")
        message.mark_sent()
        message.a2p_provider = "twilio"
        return _sms_outcome(message, "accepted", "provider_accepted")

    def send_batch(
        self,
        messages_with_numbers: list[tuple[OutreachMessage, str]],
    ) -> dict[str, bool]:
        """Send a batch. Returns dict of message_id → success."""
        results: dict[str, bool] = {}
        for msg, number in messages_with_numbers:
            results[str(msg.id)] = self.send(msg, number)
        return results
