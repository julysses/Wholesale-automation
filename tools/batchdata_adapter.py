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


@dataclass
class PropertyDetails:
    lead_id: str
    address: str
    city: str
    state: str
    zip_code: str
    estimated_value: float = 0.0
    equity_percent: float = 0.0
    beds: int = 0
    baths: float = 0.0
    sqft: int = 0
    year_built: int = 0
    lot_size_sqft: int = 0
    property_type: str = ""
    success: bool = False
    error: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class CompSale:
    address: str
    sale_price: float
    sale_date: str        # ISO date string
    sqft: int
    beds: int
    baths: float
    price_per_sqft: float
    distance_miles: float = 0.0


@dataclass
class CompsResult:
    lead_id: str
    comps: list[CompSale] = field(default_factory=list)
    arv_estimate: float = 0.0   # median price/sqft * subject sqft
    comp_count: int = 0
    success: bool = False
    error: str = ""
    raw: dict = field(default_factory=dict)


# ── Adapter ────────────────────────────────────────────────────────────────────

class BatchDataAdapter:
    """
    BatchData property skip trace and valuation adapter.

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

    # ── Property Details & Valuation ──────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    def get_property_details(
        self, address: str, city: str, state: str, zip_code: str, lead_id: str = ""
    ) -> PropertyDetails:
        """
        Fetch property details and valuation from BatchData.
        Uses the /property/search endpoint.
        """
        result = PropertyDetails(
            lead_id=lead_id, address=address, city=city, state=state, zip_code=zip_code
        )

        if not self._api_key:
            result.error = "dry_run: no API key"
            return result

        request_body = {
            "searchCriteria": {
                "propertyAddress": {
                    "address": address,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                }
            }
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.BASE_URL}/property/search",
                    headers=self._headers(),
                    json=request_body,
                )
                resp.raise_for_status()
                data = resp.json()

            result.raw = data
            result.success = True

            results = data.get("results", [])
            if not results:
                result.error = "No property found"
                result.success = False
                return result

            prop = results[0]
            # Map BatchData fields to our dataclass
            result.estimated_value = float(prop.get("estimatedValue", 0) or 0)
            result.equity_percent = float(prop.get("estimatedEquityPercent", 0) or 0)
            result.beds = int(prop.get("bedrooms", 0) or 0)
            result.baths = float(prop.get("bathrooms", 0) or 0)
            result.sqft = int(prop.get("buildingSize", 0) or 0)
            result.year_built = int(prop.get("yearBuilt", 0) or 0)
            result.lot_size_sqft = int(prop.get("lotSizeSqft", 0) or 0)
            result.property_type = prop.get("propertyType", "")

            logger.info(
                f"[BatchData] Fetched details for {address}: "
                f"value=${result.estimated_value:,.0f} "
                f"equity={result.equity_percent}%"
            )

        except httpx.HTTPStatusError as exc:
            result.error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error(f"[BatchData] Property details failed: {result.error}")
        except Exception as exc:
            result.error = str(exc)
            logger.error(f"[BatchData] Property details error: {exc}")

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

    # ── Comparable Sales / ARV ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    def get_comparable_sales(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: str,
        sqft: int = 0,
        beds: int = 0,
        lead_id: str = "",
        radius_miles: float = 0.5,
        sold_within_months: int = 6,
        max_comps: int = 10,
    ) -> CompsResult:
        """
        Fetch comparable sold properties from BatchData and estimate ARV.

        ARV is computed as median price-per-sqft of valid comps × subject sqft.
        Falls back gracefully (empty result) when API is unavailable or key is absent.
        """
        result = CompsResult(lead_id=lead_id)

        if not self._api_key:
            result.error = "dry_run: no API key"
            return result

        request_body = {
            "searchCriteria": {
                "propertyAddress": {
                    "address": address,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                },
                "saleType": "sold",
                "soldWithinMonths": sold_within_months,
                "radiusMiles": radius_miles,
                "maxResults": max_comps,
            }
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.BASE_URL}/property/comps",
                    headers=self._headers(),
                    json=request_body,
                )
                resp.raise_for_status()
                data = resp.json()

            result.raw = data
            raw_comps = data.get("results", [])

            parsed: list[CompSale] = []
            for c in raw_comps:
                try:
                    sale_price = float(c.get("salePrice") or c.get("lastSalePrice") or 0)
                    comp_sqft = int(c.get("buildingSize") or c.get("sqft") or 0)
                    if sale_price <= 0:
                        continue
                    ppf = (sale_price / comp_sqft) if comp_sqft > 0 else 0.0
                    parsed.append(CompSale(
                        address=c.get("address", ""),
                        sale_price=sale_price,
                        sale_date=c.get("saleDate") or c.get("lastSaleDate") or "",
                        sqft=comp_sqft,
                        beds=int(c.get("bedrooms") or 0),
                        baths=float(c.get("bathrooms") or 0),
                        price_per_sqft=ppf,
                        distance_miles=float(c.get("distanceMiles") or 0),
                    ))
                except (TypeError, ValueError):
                    continue

            result.comps = parsed
            result.comp_count = len(parsed)
            result.success = True

            # ARV = median price/sqft across comps × subject sqft
            if parsed and sqft > 0:
                ppf_list = [c.price_per_sqft for c in parsed if c.price_per_sqft > 0]
                if ppf_list:
                    ppf_list.sort()
                    mid = len(ppf_list) // 2
                    median_ppf = (
                        ppf_list[mid] if len(ppf_list) % 2 != 0
                        else (ppf_list[mid - 1] + ppf_list[mid]) / 2
                    )
                    result.arv_estimate = round(median_ppf * sqft, -2)

            logger.info(
                f"[BatchData] Comps for {address}: "
                f"count={result.comp_count} arv_est=${result.arv_estimate:,.0f}"
            )

        except httpx.HTTPStatusError as exc:
            result.error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error(f"[BatchData] Comps failed: {result.error}")
        except Exception as exc:
            result.error = str(exc)
            logger.error(f"[BatchData] Comps error: {exc}")

        return result

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
