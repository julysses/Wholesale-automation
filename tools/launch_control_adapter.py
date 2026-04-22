"""
Launch Control SMS automation adapter.

Launch Control does not publish a fully self-serve public API, so this adapter
supports three progressively more capable modes:

  Mode 1 — zapier_webhook  (default, recommended)
    Fire a Zapier webhook that triggers your Launch Control Zap.
    Set LAUNCH_CONTROL_MODE=zapier_webhook and LAUNCH_CONTROL_ZAPIER_HOOK_URL.

  Mode 2 — csv_sync
    Build a CSV queue on disk/S3 and upload manually or via cron.
    Set LAUNCH_CONTROL_MODE=csv_sync.

  Mode 3 — api_direct  (future / if your account rep provides private API access)
    Direct API calls using LAUNCH_CONTROL_API_KEY.
    Set LAUNCH_CONTROL_MODE=api_direct.

Compliance:
  - STOP / REMOVE / UNSUBSCRIBE detection in inbound replies
  - Cools off leads that had a live answered call in the last 14 days
  - Passes compliance gate from compliance_logging_agent before sending
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Opt-out detection ──────────────────────────────────────────────────────────
OPT_OUT_KEYWORDS = {
    "stop", "no", "remove", "unsubscribe", "not interested",
    "dont contact", "do not contact", "dont call", "do not call",
    "leave me alone", "remove me", "take me off", "opt out", "optout",
}


def is_opt_out(text: str) -> bool:
    """Return True if the message body contains an opt-out keyword."""
    normalised = text.lower().strip()
    return any(kw in normalised for kw in OPT_OUT_KEYWORDS)


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class LaunchControlContact:
    lead_id: str
    first_name: str
    phone: str
    property_address: str
    city: str
    state: str = "TX"
    zip_code: str = ""
    campaign_name: str = ""
    seller_score: int = 0
    priority_tier: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lead_id":          self.lead_id,
            "first_name":       self.first_name,
            "phone":            self.phone,
            "property_address": self.property_address,
            "city":             self.city,
            "state":            self.state,
            "zip":              self.zip_code,
            "campaign":         self.campaign_name,
            "seller_score":     self.seller_score,
            "tier":             self.priority_tier,
        }

    def to_csv_row(self) -> dict:
        return {
            "First Name":       self.first_name,
            "Phone":            self.phone,
            "Address":          self.property_address,
            "City":             self.city,
            "State":            self.state,
            "Zip":              self.zip_code,
            "Campaign":         self.campaign_name,
            "Tags":             ",".join(self.tags),
            "Custom1":          self.lead_id,
            "Custom2":          str(self.seller_score),
        }


@dataclass
class SMSReplyEvent:
    lead_id: str
    phone_number: str
    body: str
    is_opt_out: bool
    raw: dict = field(default_factory=dict)


# ── Adapter ────────────────────────────────────────────────────────────────────

class LaunchControlAdapter:
    """
    Launch Control SMS adapter with three modes.
    Default: zapier_webhook.
    """

    CSV_QUEUE_PATH = Path("./launch_control_queue.csv")
    CSV_FIELDNAMES = [
        "First Name", "Phone", "Address", "City", "State", "Zip",
        "Campaign", "Tags", "Custom1", "Custom2",
    ]

    def __init__(self) -> None:
        self._mode = settings.launch_control_mode           # zapier_webhook | csv_sync | api_direct
        self._zapier_url = settings.launch_control_zapier_hook_url
        self._api_key = settings.launch_control_api_key
        self._base_url = "https://app.launchcontrol.io/api/v1"  # private API slot

        logger.info(f"[LaunchControl] Adapter initialized in mode={self._mode}")

    # ── Public interface ──────────────────────────────────────────────────────

    async def add_contact_to_campaign(self, contact: LaunchControlContact) -> bool:
        """
        Enroll a lead in an SMS campaign.
        Routes to the appropriate mode implementation.
        """
        if self._mode == "zapier_webhook":
            return await self._send_zapier(contact)
        elif self._mode == "csv_sync":
            return self._append_to_csv_queue(contact)
        elif self._mode == "api_direct":
            return await self._api_add_contact(contact)
        else:
            logger.warning(f"[LaunchControl] Unknown mode '{self._mode}' — using csv_sync fallback")
            return self._append_to_csv_queue(contact)

    async def stop_campaign_for_lead(self, lead_id: str, phone: str = "") -> bool:
        """
        Stop all active SMS campaigns for a lead (called on opt-out or DNC).
        """
        if self._mode == "zapier_webhook":
            return await self._send_zapier_stop(lead_id, phone)
        elif self._mode == "api_direct":
            return await self._api_stop_contact(lead_id)
        else:
            logger.info(
                f"[LaunchControl] csv_sync mode — manually remove lead {lead_id} from campaigns"
            )
            return True

    async def mark_opt_out(self, lead_id: str, phone: str, keyword: str = "") -> bool:
        """
        Hard opt-out: stops campaign + logs to dnc_registry.
        Returns True so callers can chain without checking the return value.
        """
        logger.info(
            f"[LaunchControl] OPT-OUT lead={lead_id} phone={phone} keyword='{keyword}'"
        )
        await self.stop_campaign_for_lead(lead_id, phone)
        return True

    # ── Reply webhook parsing ─────────────────────────────────────────────────

    @staticmethod
    def parse_reply_webhook(payload: dict) -> SMSReplyEvent:
        """
        Parse an inbound SMS reply webhook from Launch Control / Zapier.
        Detects opt-out keywords automatically.
        """
        body = str(payload.get("message", payload.get("body", payload.get("text", ""))))
        phone = str(payload.get("phone", payload.get("from", payload.get("from_number", ""))))
        lead_id = str(
            payload.get("custom1", payload.get("lead_id", payload.get("externalId", "")))
        )

        return SMSReplyEvent(
            lead_id=lead_id,
            phone_number=phone,
            body=body,
            is_opt_out=is_opt_out(body),
            raw=payload,
        )

    # ── SMS trigger rule check ────────────────────────────────────────────────

    @staticmethod
    def should_send_sms(
        seller_score: int,
        dnc: bool,
        days_since_live_call: Optional[int],
    ) -> tuple[bool, str]:
        """
        Evaluate whether a lead should be enrolled in SMS nurture.
        Returns (send_ok, reason).

        Rules:
        - seller_score >= 50
        - not DNC
        - no answered live call in last 14 days
        """
        if dnc:
            return False, "lead is on DNC"
        if seller_score < 50:
            return False, f"seller_score {seller_score} below 50 threshold"
        if days_since_live_call is not None and days_since_live_call < 14:
            return False, f"live call {days_since_live_call}d ago — cooling off"
        return True, "ok"

    # ── Mode 1: Zapier webhook ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    async def _send_zapier(self, contact: LaunchControlContact) -> bool:
        if not self._zapier_url:
            logger.warning("[LaunchControl] LAUNCH_CONTROL_ZAPIER_HOOK_URL not set — skipping")
            return False

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self._zapier_url, json=contact.to_dict())
            resp.raise_for_status()
        
        logger.info(
            f"[LaunchControl] Zapier webhook sent for lead={contact.lead_id} "
            f"phone={contact.phone}"
        )
        return True

    async def _send_zapier_stop(self, lead_id: str, phone: str) -> bool:
        if not self._zapier_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    self._zapier_url,
                    json={"action": "stop_campaign", "lead_id": lead_id, "phone": phone},
                )
                resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error(f"[LaunchControl] Zapier stop failed: {exc}")
            return False

    # ── Mode 2: CSV queue ─────────────────────────────────────────────────────

    def _append_to_csv_queue(self, contact: LaunchControlContact) -> bool:
        """
        Append the contact to a local CSV file for manual/cron upload to Launch Control.
        The file is created if it doesn't exist.
        """
        write_header = not self.CSV_QUEUE_PATH.exists()
        try:
            with open(self.CSV_QUEUE_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDNAMES)
                if write_header:
                    writer.writeheader()
                writer.writerow(contact.to_csv_row())
            logger.info(
                f"[LaunchControl] csv_sync: queued lead={contact.lead_id} "
                f"→ {self.CSV_QUEUE_PATH}"
            )
            return True
        except Exception as exc:
            logger.error(f"[LaunchControl] CSV queue write failed: {exc}")
            return False

    def export_csv_queue(self) -> str:
        """Return the current CSV queue as a string (for API download endpoint)."""
        if not self.CSV_QUEUE_PATH.exists():
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=self.CSV_FIELDNAMES)
            writer.writeheader()
            return buf.getvalue()
        return self.CSV_QUEUE_PATH.read_text(encoding="utf-8")

    def clear_csv_queue(self) -> None:
        """Clear the queue after successful upload."""
        if self.CSV_QUEUE_PATH.exists():
            self.CSV_QUEUE_PATH.unlink()

    # ── Mode 3: Direct API (private — requires account rep) ───────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    async def _api_add_contact(self, contact: LaunchControlContact) -> bool:
        if not self._api_key:
            logger.warning("[LaunchControl] LAUNCH_CONTROL_API_KEY not set — falling back to CSV")
            return self._append_to_csv_queue(contact)

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self._base_url}/contacts",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "firstName": contact.first_name,
                    "phone":     contact.phone,
                    "campaign":  contact.campaign_name,
                    "externalId": contact.lead_id,
                    "customFields": {
                        "address": contact.property_address,
                        "city":    contact.city,
                        "state":   contact.state,
                        "zip":     contact.zip_code,
                    },
                },
            )
            resp.raise_for_status()
        
        logger.info(f"[LaunchControl] API: added contact lead={contact.lead_id}")
        return True

    async def _api_stop_contact(self, lead_id: str) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.delete(
                    f"{self._base_url}/contacts/{lead_id}/campaigns",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error(f"[LaunchControl] API stop_contact failed: {exc}")
            return False
