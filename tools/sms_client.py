"""
SMS Client — provider-agnostic compliant message delivery.

Enforces Sections 4 & 5 rules:
- Texas allowed hours: 9:00am – 7:00pm CT
- No SMS on weekends (unless inbound-initiated)
- Compliance clearance required before every send
- Approved A2P 10DLC providers: Twilio, Telnyx, MessageBird
- MANDATORY: if compliance is uncertain, do not send

Supported providers: twilio (default), telnyx, messagebird
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from config.settings import settings
from schemas.outreach import APPROVED_SMS_PROVIDERS, OutreachMessage, OutreachStatus

logger = logging.getLogger(__name__)

TEXAS_TZ = "America/Chicago"


def _texas_now() -> datetime:
    try:
        tz = ZoneInfo(settings.texas_timezone)
    except Exception:
        tz = ZoneInfo(TEXAS_TZ)
    return datetime.now(tz=tz)


class SMSClient:
    """
    Provider-agnostic SMS client with mandatory compliance guards.

    Will NOT send if:
    - message.compliance_cleared is False
    - Outside Texas allowed hours (9am–7pm CT)
    - Weekend (Sat/Sun) and not inbound-initiated
    - No valid phone number
    - Provider not in approved A2P 10DLC list

    Supported providers: twilio, telnyx, messagebird
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
            message.status = OutreachStatus.STOPPED
            return False

        # Guard 2: Texas allowed hours (9am–7pm CT)
        if not self._in_allowed_hours():
            now = _texas_now()
            logger.warning(
                f"[SMSClient] BLOCKED msg {message.id}: outside allowed hours "
                f"(current Texas time: {now.strftime('%H:%M %Z')})"
            )
            return False

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
            return False

        # Guard 4: valid phone number
        to_number = to_number.strip()
        if not to_number or len(to_number) < 10:
            logger.error(f"[SMSClient] BLOCKED invalid phone: {to_number!r}")
            return False

        # Missing credentials never count as a send. Twilio stays disabled until
        # carrier approval and controlled delivery acceptance are complete.
        if not self._configured or (self._provider == "twilio" and not settings.sms_live_enabled):
            message.mark_stopped("SMS credentials missing or live sending disabled")
            return False

        return self._dispatch(message, to_number)

    def _dispatch(self, message: OutreachMessage, to_number: str) -> bool:
        """Route to the correct provider SDK."""
        try:
            if self._provider == "twilio":
                return self._send_twilio(message, to_number)
            if self._provider == "telnyx":
                return self._send_telnyx(message, to_number)
            if self._provider == "messagebird":
                return self._send_messagebird(message, to_number)
            logger.error(f"[SMSClient] Unknown provider: {self._provider}")
            return False
        except Exception as exc:
            logger.error(f"[SMSClient] Send failed for msg {message.id}: {exc}")
            return False

    def _send_twilio(self, message: OutreachMessage, to_number: str) -> bool:
        import re
        from twilio.rest import Client
        from tools.crm import get_supabase_client

        if not settings.sms_live_enabled:
            return False
        digits = re.sub(r"\D", "", to_number)
        if len(digits) == 10:
            digits = "1" + digits
        if not re.fullmatch(r"1\d{10}", digits):
            return False
        to_number = "+" + digits
        if settings.sms_allowed_recipients:
            allowed = {number.strip() for number in settings.sms_allowed_recipients.split(',') if number.strip()}
            if to_number not in allowed:
                message.mark_stopped("Recipient outside launch allowlist")
                return False
        base = settings.twilio_webhook_base_url.rstrip("/")
        if not base.startswith("https://") or not settings.twilio_messaging_service_sid:
            return False
        sb = get_supabase_client()
        if sb is None:
            return False
        # This registration covers consented property inquiries only, not owner
        # alerts or buyer-list blasts. Require a matching durable form receipt.
        rows = sb.table("lead_form_submissions").select("raw_answers").eq(
            "lead_id", str(message.lead_id)).order("created_at", desc=True).limit(1).execute().data
        answers = rows[0].get("raw_answers", {}) if rows else {}
        consent = answers.get("_sms_consent", {})
        receipt_phone = re.sub(r"\D", "", str(answers.get("phone", "")))
        if (consent.get("accepted") is not True or consent.get("rendered_disclosure_matches") is not True
                or receipt_phone[-10:] != digits[-10:]):
            message.mark_stopped("No matching property inquiry consent receipt")
            return False
        safety = sb.rpc("intake_phone_status", {"p_phone": to_number,
            "p_lead": str(message.lead_id), "p_property": answers.get("property_address", "")}).execute().data
        if not isinstance(safety, dict) or safety.get("suppressed") is not False:
            message.mark_stopped("Suppression lookup blocked sending")
            return False
        claim = sb.table("sms_events").upsert({"id": str(message.id), "lead_id": str(message.lead_id),
            "provider": "twilio", "direction": "outbound", "phone_number": to_number,
            "body": message.body, "status": "submitting"}, on_conflict="id", ignore_duplicates=True).execute()
        if not claim.data:
            return False  # An earlier attempt may have reached Twilio; never auto-replay.
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        try:
            result = client.messages.create(body=message.body, from_=settings.twilio_from_number,
                messaging_service_sid=settings.twilio_messaging_service_sid, to=to_number,
                status_callback=f"{base}/webhooks/twilio/status?message_id={message.id}")
        except Exception:
            sb.table("sms_events").update({"status": "unknown"}).eq("id", str(message.id)).execute()
            raise
        message.provider_message_id = result.sid
        saved = sb.table("sms_events").update({"status": "accepted",
            "raw_payload": {"provider_sid": result.sid}}).eq("id", str(message.id)).execute()
        if not saved.data:
            raise RuntimeError("Provider accepted SMS but local receipt is unconfirmed; reconcile before retry")
        message.mark_sent()
        message.a2p_provider = "twilio"
        return True

    def _send_telnyx(self, message: OutreachMessage, to_number: str) -> bool:
        import telnyx  # type: ignore

        telnyx.api_key = settings.telnyx_api_key
        if not settings.telnyx_from_number:
            logger.error("[SMSClient] TELNYX_FROM_NUMBER not configured")
            return False
        result = telnyx.Message.create(
            from_=settings.telnyx_from_number,
            to=to_number,
            text=message.body,
        )
        message.mark_sent()
        message.a2p_provider = "telnyx"
        logger.info(f"[SMSClient] Sent via Telnyx | msg={message.id} | ID={result.id}")
        return True

    def _send_messagebird(self, message: OutreachMessage, to_number: str) -> bool:
        import messagebird  # type: ignore

        client = messagebird.Client(settings.messagebird_api_key)
        result = client.message_create(
            settings.messagebird_originator,
            [to_number],
            message.body,
        )
        message.mark_sent()
        message.a2p_provider = "messagebird"
        logger.info(f"[SMSClient] Sent via MessageBird | msg={message.id} | ID={result.id}")
        return True

    def send_batch(
        self,
        messages_with_numbers: list[tuple[OutreachMessage, str]],
    ) -> dict[str, bool]:
        """Send a batch. Returns dict of message_id → success."""
        results: dict[str, bool] = {}
        for msg, number in messages_with_numbers:
            results[str(msg.id)] = self.send(msg, number)
        return results
