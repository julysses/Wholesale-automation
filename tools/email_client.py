"""
Email Client — provider-agnostic notification and alert delivery.

Supported providers: sendgrid (default), mailgun
"""

from __future__ import annotations

import logging
from typing import Optional

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
        self._from_email = settings.from_email or "alerts@wholesale-os.com"
        self._configured = self._check_provider_credentials()

        if not self._configured:
            logger.warning(
                f"[EmailClient] Provider '{self._provider}' credentials not configured — "
                "running in dry-run mode"
            )

    def _check_provider_credentials(self) -> bool:
        if self._provider == "sendgrid":
            return bool(settings.sendgrid_api_key)
        if self._provider == "mailgun":
            return bool(settings.mailgun_api_key)
        return False

    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Attempt to send an email. Returns True if sent (or dry-run simulated).
        """
        if not to_email:
            logger.error("[EmailClient] BLOCKED invalid to_email: empty")
            return False

        if not self._configured:
            logger.info(
                f"[EmailClient][DRY-RUN] Provider={self._provider} | "
                f"To={to_email} | Subject={subject} | Body={body[:60]}..."
            )
            return True

        return self._dispatch(to_email, subject, body, html_body)

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
            "content": [
                {"type": "text/plain", "value": body},
            ],
        }
        if html_body:
            payload["content"].append({"type": "text/html", "value": html_body})
        
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
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
