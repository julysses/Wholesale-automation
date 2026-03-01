"""
SMS Client — wraps Twilio (or any provider) for compliant message delivery.
Checks compliance clearance before every send. Logs every attempt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import settings
from schemas.outreach import OutreachMessage, OutreachStatus

logger = logging.getLogger(__name__)


class SMSClient:
    """
    Sends SMS messages via Twilio.
    Will not send if:
    - message is not compliance_cleared
    - TCPA quiet hours are active
    - Twilio credentials are not configured
    """

    def __init__(self) -> None:
        self._twilio_configured = bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_from_number
        )
        if not self._twilio_configured:
            logger.warning("[SMSClient] Twilio credentials not configured — running in dry-run mode")

    def _in_quiet_hours(self) -> bool:
        now_hour = datetime.now(tz=timezone.utc).hour
        start = settings.tcpa_quiet_hours_start
        end = settings.tcpa_quiet_hours_end
        if start > end:  # overnight window
            return now_hour >= start or now_hour < end
        return start <= now_hour < end

    def send(
        self,
        message: OutreachMessage,
        to_number: str,
    ) -> bool:
        """
        Attempt to send an SMS. Returns True if sent (or dry-run simulated).
        Mutates message status in place.
        """
        # Guard: compliance clearance required
        if not message.compliance_cleared:
            logger.error(
                f"[SMSClient] Blocked send for msg {message.id}: not compliance cleared"
            )
            message.status = OutreachStatus.STOPPED
            return False

        # Guard: TCPA quiet hours
        if self._in_quiet_hours():
            logger.warning(
                f"[SMSClient] Blocked send for msg {message.id}: TCPA quiet hours active"
            )
            return False

        # Guard: valid phone number (basic)
        to_number = to_number.strip()
        if not to_number or len(to_number) < 10:
            logger.error(f"[SMSClient] Invalid phone number: {to_number!r}")
            return False

        if not self._twilio_configured:
            # Dry-run mode: log and simulate
            logger.info(
                f"[SMSClient][DRY-RUN] Would send to {to_number}: {message.body[:60]}..."
            )
            message.mark_sent()
            return True

        try:
            from twilio.rest import Client  # type: ignore

            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            twilio_msg = client.messages.create(
                body=message.body,
                from_=settings.twilio_from_number,
                to=to_number,
            )
            message.mark_sent()
            logger.info(
                f"[SMSClient] Sent msg {message.id} → {to_number} "
                f"(Twilio SID: {twilio_msg.sid})"
            )
            return True

        except Exception as exc:
            logger.error(f"[SMSClient] Send failed for {message.id}: {exc}")
            return False

    def send_batch(
        self,
        messages_with_numbers: list[tuple[OutreachMessage, str]],
    ) -> dict[str, bool]:
        """Send a batch of messages. Returns dict of message_id → success."""
        results: dict[str, bool] = {}
        for msg, number in messages_with_numbers:
            results[str(msg.id)] = self.send(msg, number)
        return results
