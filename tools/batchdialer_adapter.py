"""
BatchDialer adapter.

Handles: pushing leads as contacts, assigning to campaigns, pausing contacts,
and marking DNC. Webhook events from BatchDialer are processed by the
/webhooks/batchdialer/call endpoint in web/api/webhooks.py.

API docs: https://developer.batchdialer.com
Auth: API key via X-API-Key header.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Disposition normalisation map ──────────────────────────────────────────────
# BatchDialer uses its own labels; map them to our canonical set.
DISPOSITION_MAP: dict[str, str] = {
    # No contact
    "no_answer":        "NO_ANSWER",
    "no answer":        "NO_ANSWER",
    "busy":             "NO_ANSWER",
    "voicemail":        "VOICEMAIL",
    "left voicemail":   "VOICEMAIL",
    "vm":               "VOICEMAIL",
    "wrong number":     "WRONG_NUMBER",
    "wrong_number":     "WRONG_NUMBER",
    # DNC
    "do not call":      "DNC",
    "dnc":              "DNC",
    "requested dnc":    "DNC",
    # Not interested
    "not interested":   "NOT_INTERESTED",
    "not_interested":   "NOT_INTERESTED",
    "not_selling":      "NOT_INTERESTED",
    # Interested
    "callback":         "CALLBACK",
    "call back":        "CALLBACK",
    "warm":             "WARM",
    "interested":       "WARM",
    "hot":              "HOT",
    "very interested":  "HOT",
    "appointment":      "APPOINTMENT_SET",
    "appointment_set":  "APPOINTMENT_SET",
    "set appointment":  "APPOINTMENT_SET",
}

# Dispositions that require immediate escalation
HOT_DISPOSITIONS = {"HOT", "APPOINTMENT_SET"}

# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class DialerContact:
    """Lead fields mapped to BatchDialer contact schema."""
    first_name: str
    last_name: str
    phone: str
    secondary_phone: str = ""
    property_address: str = ""
    city: str = ""
    state: str = "TX"
    zip_code: str = ""
    seller_score: int = 0
    priority_tier: str = ""
    tags: list[str] = field(default_factory=list)
    internal_lead_id: str = ""

    def to_payload(self) -> dict:
        payload: dict = {
            "firstName": self.first_name,
            "lastName":  self.last_name,
            "phone":     self.phone,
            "customFields": {
                "property_address": self.property_address,
                "city":             self.city,
                "state":            self.state,
                "zip":              self.zip_code,
                "seller_score":     str(self.seller_score),
                "priority_tier":    self.priority_tier,
                "internal_lead_id": self.internal_lead_id,
            },
        }
        if self.secondary_phone:
            payload["secondaryPhone"] = self.secondary_phone
        if self.tags:
            payload["tags"] = self.tags
        return payload


@dataclass
class CallResultEvent:
    """Normalised call result received from BatchDialer webhook."""
    event_id: str
    lead_id: str
    dialer: str
    agent_id: str
    phone_number: str
    disposition: str           # canonical: NO_ANSWER | VOICEMAIL | WARM | HOT …
    duration_sec: int
    recording_url: str
    notes: str
    occurred_at: str
    raw: dict = field(default_factory=dict)

    @property
    def is_hot(self) -> bool:
        return self.disposition in HOT_DISPOSITIONS

    @property
    def is_dnc(self) -> bool:
        return self.disposition == "DNC"


# ── Adapter ────────────────────────────────────────────────────────────────────

class BatchDialerAdapter:
    """
    BatchDialer REST API adapter.

    Dry-run mode when BATCHDIALER_API_KEY is not configured — all mutating calls
    are logged and skipped rather than raising exceptions.
    """

    BASE_URL = "https://app.batchdialer.com/api/v1"

    def __init__(self) -> None:
        self._api_key = settings.batchdialer_api_key
        if not self._api_key:
            logger.warning(
                "[BatchDialer] BATCHDIALER_API_KEY not set — running in dry-run mode"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _dry_run(self, method: str, **kwargs) -> dict:
        logger.info(f"[BatchDialer] DRY-RUN {method}: {kwargs}")
        return {"dry_run": True, "method": method, **kwargs}

    # ── Campaign management ───────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    async def create_campaign(self, name: str, caller_id: str = "", notes: str = "") -> Optional[str]:
        """Create a new dialer campaign. Returns external campaign_id."""
        if not self._api_key:
            return self._dry_run("create_campaign", name=name).get("id")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/campaigns",
                headers=self._headers(),
                json={"name": name, "callerId": caller_id, "notes": notes},
            )
            resp.raise_for_status()
            data = resp.json()
            campaign_id = str(data.get("id", ""))
            logger.info(f"[BatchDialer] Created campaign '{name}' id={campaign_id}")
            return campaign_id

    # ── Contact management ────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    async def upsert_contact(self, contact: DialerContact) -> Optional[str]:
        """
        Create or update a contact in BatchDialer.
        Returns the external contact_id (str) or None on failure.
        """
        if not self._api_key:
            result = self._dry_run("upsert_contact", phone=contact.phone)
            return result.get("contact_id", f"dry_{contact.internal_lead_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/contacts",
                headers=self._headers(),
                json=contact.to_payload(),
            )
            resp.raise_for_status()
            data = resp.json()
            contact_id = str(data.get("id", ""))
            logger.info(
                f"[BatchDialer] Upserted contact lead={contact.internal_lead_id} "
                f"contact_id={contact_id}"
            )
            return contact_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    async def assign_to_campaign(self, contact_id: str, campaign_id: str) -> bool:
        """Add contact to a campaign list."""
        if not self._api_key:
            self._dry_run("assign_to_campaign", contact_id=contact_id, campaign_id=campaign_id)
            return True

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/campaigns/{campaign_id}/contacts",
                headers=self._headers(),
                json={"contactId": contact_id},
            )
            resp.raise_for_status()
            logger.info(f"[BatchDialer] Assigned contact={contact_id} → campaign={campaign_id}")
            return True

    async def pause_contact(self, contact_id: str) -> bool:
        """Pause a contact (stops it from being called in active campaigns)."""
        if not self._api_key:
            self._dry_run("pause_contact", contact_id=contact_id)
            return True

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(
                f"{self.BASE_URL}/contacts/{contact_id}",
                headers=self._headers(),
                json={"status": "paused"},
            )
            resp.raise_for_status()
            return True

    async def mark_dnc(self, contact_id: str) -> bool:
        """Mark contact as DNC inside BatchDialer."""
        if not self._api_key:
            self._dry_run("mark_dnc", contact_id=contact_id)
            return True

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/contacts/{contact_id}/dnc",
                headers=self._headers(),
            )
            resp.raise_for_status()
            logger.info(f"[BatchDialer] Marked DNC: contact={contact_id}")
            return True

    # ── High-level push ───────────────────────────────────────────────────────

    async def push_lead_to_campaign(
        self,
        lead_id: str,
        first_name: str,
        last_name: str,
        phone: str,
        campaign_id: str,
        secondary_phone: str = "",
        property_address: str = "",
        city: str = "",
        state: str = "TX",
        zip_code: str = "",
        seller_score: int = 0,
        priority_tier: str = "",
        tags: Optional[list[str]] = None,
    ) -> tuple[Optional[str], bool]:
        """
        Convenience method: upsert contact + assign to campaign.
        Returns (contact_id, assigned_ok).
        """
        contact = DialerContact(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            secondary_phone=secondary_phone,
            property_address=property_address,
            city=city,
            state=state,
            zip_code=zip_code,
            seller_score=seller_score,
            priority_tier=priority_tier,
            tags=tags or [],
            internal_lead_id=lead_id,
        )
        contact_id = await self.upsert_contact(contact)
        if not contact_id:
            return None, False

        assigned = await self.assign_to_campaign(contact_id, campaign_id)
        return contact_id, assigned

    # ── Webhook parsing ───────────────────────────────────────────────────────

    @staticmethod
    def parse_call_webhook(payload: dict) -> CallResultEvent:
        """
        Parse an inbound BatchDialer webhook payload into a normalised CallResultEvent.
        BatchDialer sends these when a call is completed.
        """
        raw_dispo = (payload.get("disposition") or payload.get("callDisposition") or "").lower()
        canonical_dispo = DISPOSITION_MAP.get(raw_dispo, raw_dispo.upper() or "NO_ANSWER")

        return CallResultEvent(
            event_id=str(payload.get("id", "")),
            lead_id=str(
                payload.get("customFields", {}).get("internal_lead_id", "")
                or payload.get("leadId", "")
            ),
            dialer="batchdialer",
            agent_id=str(payload.get("agentId", "")),
            phone_number=str(payload.get("phoneNumber", "")),
            disposition=canonical_dispo,
            duration_sec=int(payload.get("duration", 0)),
            recording_url=str(payload.get("recordingUrl", "")),
            notes=str(payload.get("notes", "")),
            occurred_at=str(payload.get("callTime", payload.get("createdAt", ""))),
            raw=payload,
        )
