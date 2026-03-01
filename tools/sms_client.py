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
        Attempt to send an SMS. Returns True if sent (or dry-run simulated).
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

        # Guard 5: dry-run mode (no credentials)
        if not self._configured:
            logger.info(
                f"[SMSClient][DRY-RUN] Provider={self._provider} | "
                f"To={to_number[:6]}*** | Body={message.body[:60]}..."
            )
            message.mark_sent()
            message.a2p_provider = f"{self._provider}:dry-run"
            return True

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
        from twilio.rest import Client  # type: ignore

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        result = client.messages.create(
            body=message.body,
            from_=settings.twilio_from_number,
            to=to_number,
        )
        message.mark_sent()
        message.a2p_provider = "twilio"
        logger.info(f"[SMSClient] Sent via Twilio | msg={message.id} | SID={result.sid}")
        return True

    def _send_telnyx(self, message: OutreachMessage, to_number: str) -> bool:
        import telnyx  # type: ignore

        telnyx.api_key = settings.telnyx_api_key
        result = telnyx.Message.create(
            from_="+1XXXXXXXXXX",  # configure from number in settings
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
            "Texas Wholesale",
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
