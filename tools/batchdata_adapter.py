"""
BatchData / BatchSkipTracing adapter.

Handles property-level skip tracing: given an owner name + property address,
returns enriched phone numbers and emails with confidence scores.

Usage:
    adapter = BatchDataAdapter()
    result  = adapter.skip_trace_property(payload)

API docs: https://developer.batchdata.com
Auth: API key passed as Bearer token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class EnrichedPhone:
    number: str               # E.164: +15551234567
    type: str                 # mobile | landline | voip | unknown
    confidence: float         # 0.0–1.0
    status: str = "active"    # active | disconnected | unknown


@dataclass
class EnrichedEmail:
    email: str
    confidence: float  # 0.0–1.0


@dataclass
class SkipTracePayload:
    owner_name: str
    property_address: str
    city: str
    state: str = "TX"
    zip_code: str = ""


@dataclass
class SkipTraceResult:
    lead_id: str
    phones: list[EnrichedPhone] = field(default_factory=list)
    emails: list[EnrichedEmail] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    success: bool = False
    error: str = ""

    @property
    def best_phone(self) -> Optional[EnrichedPhone]:
        """Return highest-confidence phone, preferring mobile over landline."""
        TYPE_RANK = {"mobile": 0, "voip": 1, "landline": 2, "unknown": 3}
        sorted_phones = sorted(
            self.phones,
            key=lambda p: (TYPE_RANK.get(p.type, 9), -p.confidence),
        )
        return sorted_phones[0] if sorted_phones else None

    @property
    def has_mobile(self) -> bool:
        return any(p.type == "mobile" for p in self.phones)

    @property
    def landline_only(self) -> bool:
        return bool(self.phones) and not self.has_mobile


# ── Adapter ────────────────────────────────────────────────────────────────────

class BatchDataAdapter:
    """
    BatchData property skip trace adapter.

    When BATCHDATA_API_KEY is not configured the adapter runs in dry-run mode,
    returning an empty result so the pipeline can continue without crashing.
    """

    BASE_URL = "https://api.batchdata.com/api/v1"

    def __init__(self) -> None:
        self._api_key = settings.batchdata_api_key
        if not self._api_key:
            logger.warning(
                "[BatchData] BATCHDATA_API_KEY not set — running in dry-run mode"
            )

    # ── Authentication ────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Core skip trace ───────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    def skip_trace_property(self, payload: SkipTracePayload, lead_id: str = "") -> SkipTraceResult:
        """
        Call BatchData property skip trace endpoint.
        Returns enriched phones + emails ranked by confidence.
        Falls back gracefully if API is unavailable.
        """
        result = SkipTraceResult(lead_id=lead_id)

        if not self._api_key:
            result.error = "dry_run: no API key"
            return result

        request_body = {
            "requests": [
                {
                    "propertyAddress": {
                        "address": payload.property_address,
                        "city": payload.city,
                        "state": payload.state,
                        "zip": payload.zip_code,
                    },
                    "ownerName": payload.owner_name,
                }
            ]
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.BASE_URL}/property/skip-trace",
                    headers=self._headers(),
                    json=request_body,
                )
                resp.raise_for_status()
                data = resp.json()

            result.raw = data
            result.success = True

            # Extract results from BatchData response structure
            records = (
                data.get("results", {})
                    .get("persons", [{}])[0]
                    .get("phones", [])
            ) if data.get("results") else []

            result.phones = self._map_phones(data)
            result.emails = self._map_emails(data)

            logger.info(
                f"[BatchData] lead={lead_id} "
                f"phones={len(result.phones)} emails={len(result.emails)}"
            )

        except httpx.HTTPStatusError as exc:
            result.error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error(f"[BatchData] skip trace failed: {result.error}")
        except Exception as exc:
            result.error = str(exc)
            logger.error(f"[BatchData] skip trace error: {exc}")

        return result

    # ── Response mapping ──────────────────────────────────────────────────────

    def _map_phones(self, data: dict) -> list[EnrichedPhone]:
        """
        Map BatchData response → list[EnrichedPhone], ranked mobile-first.

        BatchData returns a nested structure; we normalise it here so the rest
        of the codebase never needs to know about the vendor's schema.
        """
        raw_phones: list[dict] = []

        # Handle BatchData's nested results format
        persons = data.get("results", {}).get("persons", [])
        for person in persons:
            raw_phones.extend(person.get("phones", []))

        # Also try flat phones key
        if not raw_phones:
            raw_phones = data.get("phones", [])

        phones: list[EnrichedPhone] = []
        for p in raw_phones:
            number = p.get("phone", "") or p.get("number", "")
            if not number:
                continue
            # Normalise to E.164 if not already prefixed
            if not number.startswith("+"):
                number = f"+1{number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

            phone_type = (p.get("type") or p.get("phoneType") or "unknown").lower()
            # Normalise BatchData type labels
            if "cell" in phone_type or "mobile" in phone_type:
                phone_type = "mobile"
            elif "land" in phone_type:
                phone_type = "landline"
            elif "voip" in phone_type:
                phone_type = "voip"
            else:
                phone_type = "unknown"

            confidence = float(p.get("confidence", p.get("score", 0.5)) or 0.5)
            if confidence > 1.0:
                confidence = confidence / 100.0  # some APIs return 0-100

            phones.append(EnrichedPhone(
                number=number,
                type=phone_type,
                confidence=confidence,
                status=p.get("status", "active"),
            ))

        # Rank: mobile > voip > landline > unknown, then by confidence desc
        TYPE_RANK = {"mobile": 0, "voip": 1, "landline": 2, "unknown": 3}
        return sorted(phones, key=lambda p: (TYPE_RANK.get(p.type, 9), -p.confidence))

    def _map_emails(self, data: dict) -> list[EnrichedEmail]:
        raw_emails: list[dict] = []

        persons = data.get("results", {}).get("persons", [])
        for person in persons:
            raw_emails.extend(person.get("emails", []))

        if not raw_emails:
            raw_emails = data.get("emails", [])

        emails: list[EnrichedEmail] = []
        for e in raw_emails:
            addr = e.get("email", "") or e.get("address", "")
            if not addr or "@" not in addr:
                continue
            confidence = float(e.get("confidence", e.get("score", 0.5)) or 0.5)
            if confidence > 1.0:
                confidence = confidence / 100.0
            emails.append(EnrichedEmail(email=addr.lower(), confidence=confidence))

        return sorted(emails, key=lambda e: -e.confidence)

    # ── Batch skip trace ──────────────────────────────────────────────────────

    def skip_trace_batch(
        self, payloads: list[tuple[str, SkipTracePayload]]
    ) -> list[SkipTraceResult]:
        """
        Skip trace multiple leads.
        payloads: list of (lead_id, SkipTracePayload)

        In practice BatchData supports batch requests; this implementation sends
        them individually to keep error handling per-record clean.
        """
        results = []
        for lead_id, payload in payloads:
            result = self.skip_trace_property(payload, lead_id=lead_id)
            results.append(result)
        return results
