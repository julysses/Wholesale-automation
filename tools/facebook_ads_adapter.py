"""
Facebook Ads / Lead Ads adapter.

Handles:
- Webhook challenge verification (GET hub.verify)
- Webhook HMAC signature verification (POST X-Hub-Signature-256)
- Parsing Facebook Lead Ads webhook payloads
- Fetching lead form field_data from Graph API
- Syncing campaign insights (impressions, clicks, spend, leads)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


@dataclass
class FacebookLeadEntry:
    """Parsed entry from a Facebook Lead Ads webhook payload."""
    leadgen_id: str
    page_id: str
    ad_id: Optional[str]
    campaign_id: Optional[str]
    adgroup_id: Optional[str]
    form_id: Optional[str]
    created_time: Optional[int]


@dataclass
class FacebookLeadFormData:
    """Parsed field_data returned by the Graph API for a leadgen_id."""
    leadgen_id: str
    created_time: Optional[int]
    fields: dict[str, str] = field(default_factory=dict)
    # Raw list in case caller needs original structure
    raw_field_data: list[dict] = field(default_factory=list)


class FacebookAdsAdapter:
    """Wraps the Facebook Marketing / Leadgen Graph API."""

    def __init__(
        self,
        app_secret: str,
        access_token: str,
        webhook_verify_token: str,
        ad_account_id: str = "",
    ) -> None:
        self._app_secret = app_secret
        self._access_token = access_token
        self._verify_token = webhook_verify_token
        self._ad_account_id = ad_account_id

    # ── Webhook helpers ────────────────────────────────────────────────────────

    def verify_webhook_challenge(
        self, hub_mode: str, hub_verify_token: str, hub_challenge: str
    ) -> Optional[str]:
        """
        Called on GET /webhooks/facebook/lead.
        Returns the challenge string if the verify token matches, None otherwise.
        """
        if hub_mode == "subscribe" and hub_verify_token == self._verify_token:
            return hub_challenge
        logger.warning("Facebook webhook challenge failed — token mismatch")
        return None

    def verify_webhook_signature(
        self, payload_bytes: bytes, signature_header: str
    ) -> bool:
        """
        Verify X-Hub-Signature-256: sha256=<hex_digest>
        Uses app_secret as the HMAC key.
        Returns True if valid.
        """
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected_hex = signature_header[len("sha256="):]
        computed = hmac.new(
            self._app_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, expected_hex)

    def parse_lead_webhook(self, payload: dict) -> list[FacebookLeadEntry]:
        """
        Parse entry[].changes[].value for leadgen events.
        Returns a list of FacebookLeadEntry objects.
        """
        entries: list[FacebookLeadEntry] = []
        for entry in payload.get("entry", []):
            page_id = entry.get("id", "")
            for change in entry.get("changes", []):
                if change.get("field") != "leadgen":
                    continue
                val = change.get("value", {})
                entries.append(
                    FacebookLeadEntry(
                        leadgen_id=str(val.get("leadgen_id", "")),
                        page_id=page_id,
                        ad_id=val.get("ad_id"),
                        campaign_id=val.get("campaign_id"),
                        adgroup_id=val.get("adgroup_id"),
                        form_id=val.get("form_id"),
                        created_time=val.get("created_time"),
                    )
                )
        return entries

    # ── Graph API calls ────────────────────────────────────────────────────────

    def fetch_lead_form_data(self, leadgen_id: str) -> Optional[FacebookLeadFormData]:
        """
        GET /{leadgen_id}?fields=field_data&access_token=...
        Returns normalized FacebookLeadFormData or None on failure.
        """
        if not leadgen_id or not self._access_token:
            logger.warning("fetch_lead_form_data called without leadgen_id or token")
            return None

        url = f"{GRAPH_BASE}/{leadgen_id}"
        params = {
            "fields": "field_data,created_time,ad_id,campaign_id,adgroup_id,form_id",
            "access_token": self._access_token,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error(f"fetch_lead_form_data error for {leadgen_id}: {exc}")
            return None

        raw_fields: list[dict] = data.get("field_data", [])
        fields_map: dict[str, str] = {}
        for fld in raw_fields:
            name = fld.get("name", "")
            values = fld.get("values", [])
            fields_map[name] = values[0] if values else ""

        return FacebookLeadFormData(
            leadgen_id=leadgen_id,
            created_time=data.get("created_time"),
            fields=fields_map,
            raw_field_data=raw_fields,
        )

    def sync_campaign_insights(
        self, campaign_id: str, date_preset: str = "last_30d"
    ) -> Optional[dict[str, Any]]:
        """
        GET /{campaign_id}/insights — impressions, clicks, spend, lead counts.
        date_preset: today | yesterday | last_7d | last_30d | this_month | this_year
        Returns a dict with impressions, clicks, spend, leads or None on failure.
        """
        if not campaign_id or not self._access_token:
            return None

        url = f"{GRAPH_BASE}/{campaign_id}/insights"
        params = {
            "fields": "impressions,clicks,spend,actions",
            "date_preset": date_preset,
            "access_token": self._access_token,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error(f"sync_campaign_insights error for {campaign_id}: {exc}")
            return None

        insights = data.get("data", [{}])[0] if data.get("data") else {}
        # Extract lead count from actions
        leads_count = 0
        for action in insights.get("actions", []):
            if action.get("action_type") == "lead":
                leads_count = int(action.get("value", 0))
                break

        return {
            "impressions": int(insights.get("impressions", 0)),
            "clicks": int(insights.get("clicks", 0)),
            "spend": float(insights.get("spend", 0.0)),
            "leads_count": leads_count,
        }

    def sync_all_campaigns(self) -> list[dict[str, Any]]:
        """
        GET /act_{id}/campaigns?fields=id,name,status,daily_budget,insights
        Returns list of campaign dicts or empty list on failure.
        """
        if not self._ad_account_id or not self._access_token:
            logger.warning("sync_all_campaigns: missing ad_account_id or access_token")
            return []

        account_id = self._ad_account_id
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"

        url = f"{GRAPH_BASE}/{account_id}/campaigns"
        params = {
            "fields": "id,name,status,daily_budget,objective",
            "access_token": self._access_token,
            "limit": 50,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error(f"sync_all_campaigns error: {exc}")
            return []

        campaigns = []
        for c in data.get("data", []):
            campaigns.append({
                "external_campaign_id": c.get("id", ""),
                "name": c.get("name", ""),
                "status": c.get("status", "").lower(),
                "daily_budget": float(c.get("daily_budget", 0)) / 100.0,  # FB returns cents
                "campaign_objective": c.get("objective", "").lower(),
            })
        return campaigns


# ── Field name normalization ────────────────────────────────────────────────────
# Facebook field names vary by form setup. Normalize to our schema.
FACEBOOK_FIELD_MAP: dict[str, str] = {
    # Contact
    "full_name": "full_name",
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "phone_number": "phone",
    "phone": "phone",
    # Property
    "street_address": "property_address",
    "address": "property_address",
    "zip_code": "zip_code",
    "zip": "zip_code",
    "city": "city",
    "state": "state",
    # Qualification questions
    "motivation": "motivation",
    "why_selling": "motivation",
    "reason_for_selling": "motivation",
    "timeline": "timeline",
    "when_to_sell": "timeline",
    "close_timeline": "timeline",
    "condition": "condition",
    "property_condition": "condition",
    "asking_price": "asking_price",
    "price": "asking_price",
    "occupancy": "occupancy",
}


def normalize_facebook_fields(raw_fields: dict[str, str]) -> dict[str, str]:
    """Map raw Facebook field names to our internal field names."""
    normalized: dict[str, str] = {}
    for fb_name, value in raw_fields.items():
        canonical = FACEBOOK_FIELD_MAP.get(fb_name.lower(), fb_name.lower())
        normalized[canonical] = value
    # Split full_name if needed
    if "full_name" in normalized and "first_name" not in normalized:
        parts = normalized["full_name"].split(" ", 1)
        normalized["first_name"] = parts[0]
        normalized["last_name"] = parts[1] if len(parts) > 1 else ""
    return normalized
