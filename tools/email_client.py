"""
Email Client — provider-agnostic notification and alert delivery.

Supported providers: sendgrid (default), mailgun
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID, uuid4

import httpx
from config.settings import settings

logger = logging.getLogger(__name__)


class EmailClient:
    """
    Provider-agnostic Email client for internal alerts and seller nurture.

    Supported providers: sendgrid, mailgun
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        self._provider = (provider or settings.email_provider).lower()
        self._from_email = settings.from_email.strip()
        self._configured = self._check_provider_credentials()
        self.message_id = None
        self._provider_message_id = None

        if not self._configured:
            logger.warning(
                f"[EmailClient] Provider '{self._provider}' credentials not configured — "
                "running in dry-run mode"
            )

    def _check_provider_credentials(self) -> bool:
        if self._provider == "sendgrid":
            return bool(settings.sendgrid_api_key and self._from_email)
        if self._provider == "mailgun":
            return bool(settings.mailgun_api_key and self._from_email)
        return False

    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> bool:
        """
        Attempt to send an email. Returns True only for provider acceptance.
        """
        if not to_email:
            logger.error("[EmailClient] BLOCKED invalid to_email: empty")
            return False

        if not settings.email_live_enabled:
            logger.info("[EmailClient] BLOCKED: email sending disabled")
            return False
        to_email = to_email.strip().lower()
        allowed = {
            address.strip().lower()
            for address in settings.email_allowed_recipients.split(",")
            if address.strip()
        }
        if settings.email_allowed_recipients and to_email not in allowed:
            logger.info("[EmailClient] BLOCKED: recipient outside launch allowlist")
            return False

        if not self._configured:
            logger.info(
                f"[EmailClient][DRY-RUN] Provider={self._provider} | "
                f"To={to_email} | Subject={subject} | Body={body[:60]}..."
            )
            return False

        try:
            self.message_id = str(UUID(message_id)) if message_id else str(uuid4())
            if not self._claim(to_email, subject):
                return False
        except Exception:
            logger.exception("[EmailClient] BLOCKED: durable claim unavailable")
            return False
        self._provider_message_id = None
        accepted = self._dispatch(to_email, subject, body, html_body)
        needs_review = not accepted
        try:
            # Never blindly retry an ambiguous provider outcome. Reusing the ID
            # cannot claim another send, even if this final status write fails.
            from tools.crm import get_supabase_client
            sb = get_supabase_client()
            saved = sb.table('email_messages').update({
                'status': 'accepted' if accepted else 'unknown',
                'provider_message_id': self._provider_message_id,
            }).eq('id', self.message_id).execute().data
            if not saved:
                raise RuntimeError('Email outcome persistence unconfirmed')
        except Exception:
            needs_review = True
            logger.exception('[EmailClient] Outcome persistence failed; inspect claim before retry')
        if needs_review and self._provider == 'sendgrid':
            try:
                from tools.operational_alerts import record_provider_alert
                record_provider_alert(sb, 'sendgrid', self.message_id, 'unknown')
            except Exception:
                logger.exception('[EmailClient] Reconciliation alert persistence failed')
        return accepted

    def _claim(self, recipient: str, subject: str) -> bool:
        from tools.crm import get_supabase_client
        sb = get_supabase_client()
        if sb is None:
            return False
        data = sb.rpc('claim_email_message', {
            'p_id': self.message_id, 'p_email': recipient,
            'p_subject': subject, 'p_provider': self._provider,
        }).execute().data
        return isinstance(data, dict) and data.get('claimed') is True

    def _dispatch(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """Route to the correct provider API."""
        try:
            if self._provider == "sendgrid":
                return self._send_sendgrid(to_email, subject, body, html_body)
            if self._provider == "mailgun":
                return self._send_mailgun(to_email, subject, body, html_body)
            logger.error(f"[EmailClient] Unknown provider: {self._provider}")
            return False
        except Exception as exc:
            logger.error(f"[EmailClient] Send failed to {to_email}: {exc}")
            return False

    def _send_sendgrid(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {settings.sendgrid_api_key}",
            "Content-Type": "application/json",
        }
        # SendGrid V3 API payload
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": self._from_email},
            "subject": subject,
            "custom_args": {"app_message_id": self.message_id},
            "content": [
                {"type": "text/plain", "value": body},
            ],
        }
        if html_body:
            payload["content"].append({"type": "text/html", "value": html_body})
        
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            self._provider_message_id = resp.headers.get('X-Message-Id')
        logger.info(f"[EmailClient] Sent via SendGrid | To={to_email} | Subject={subject}")
        return True

    def _send_mailgun(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        # Mailgun domain is usually separate from API key, assuming we extract it from from_email
        domain = self._from_email.split("@")[-1]
        url = f"https://api.mailgun.net/v3/{domain}/messages"
        auth = ("api", settings.mailgun_api_key)
        data = {
            "from": self._from_email,
            "to": to_email,
            "subject": subject,
            "text": body,
        }
        if html_body:
            data["html"] = html_body

        with httpx.Client(timeout=15) as client:
            resp = client.post(url, auth=auth, data=data)
            resp.raise_for_status()
        logger.info(f"[EmailClient] Sent via Mailgun | To={to_email} | Subject={subject}")
        return True
