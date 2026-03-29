"""
Buyer CSV Parser — County Records & PropStream Ingestion.

Accepts CSV exports from:
  - County deed/tax records  (flexible column mapping)
  - PropStream  ("Cash Buyers" or "Absentee Owner" export)
  - Title company lists
  - Manual spreadsheets

Pipeline:
  1. Detect and normalize column names
  2. Parse each row into a BuyerTxRow (buyer + transaction)
  3. Identify investor candidates (LLC/INC entity names)
  4. Group by grantee/entity → merge into buyer records
  5. Deduplicate by apn (per buyer)
  6. Return ParseResult with buyers[], transactions[], errors[]

Usage:
    from tools.buyer_csv_parser import parse_buyer_csv

    with open("county_deeds_dallas.csv") as f:
        result = parse_buyer_csv(f, market="DFW")

    # result.buyers      → list of buyer dicts (upsert to buyers table)
    # result.transactions → list of transaction dicts (insert to buyer_transactions)
    # result.log         → dict for buyer_import_log table
"""

from __future__ import annotations

import csv
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


# ── Column alias maps ─────────────────────────────────────────────────────────
# Maps raw CSV header variants → canonical field name

BUYER_COLUMN_MAP: dict[str, str] = {
    # Grantee / buyer name
    "grantee":               "grantee",
    "grantee name":          "grantee",
    "buyer":                 "grantee",
    "buyer name":            "grantee",
    "purchaser":             "grantee",
    "purchaser name":        "grantee",
    "owner":                 "grantee",
    "owner name":            "grantee",
    # Grantor / seller
    "grantor":               "grantor",
    "grantor name":          "grantor",
    "seller":                "grantor",
    "seller name":           "grantor",
    # Property address
    "property address":      "property_address",
    "situs address":         "property_address",
    "site address":          "property_address",
    "address":               "property_address",
    "property location":     "property_address",
    # City / State / Zip
    "city":                  "city",
    "situs city":            "city",
    "state":                 "state",
    "situs state":           "state",
    "zip":                   "zip_code",
    "zip code":              "zip_code",
    "situs zip":             "zip_code",
    "postal code":           "zip_code",
    # County
    "county":                "county",
    # Purchase info
    "sale price":            "purchase_price",
    "sales price":           "purchase_price",
    "purchase price":        "purchase_price",
    "deed amount":           "purchase_price",
    "consideration":         "purchase_price",
    "transfer value":        "purchase_price",
    "sale amount":           "purchase_price",
    "sale date":             "purchase_date",
    "sales date":            "purchase_date",
    "deed date":             "purchase_date",
    "recording date":        "purchase_date",
    "transfer date":         "purchase_date",
    "close date":            "purchase_date",
    "closing date":          "purchase_date",
    # Cash indicator
    "cash sale":             "cash_transaction",
    "cash transaction":      "cash_transaction",
    "cash buyer":            "cash_transaction",
    "is cash":               "cash_transaction",
    "financing type":        "financing_type",   # parsed to cash bool
    "loan type":             "financing_type",
    # Lender
    "lender":                "lender_name",
    "lender name":           "lender_name",
    "mortgagee":             "lender_name",
    "bank":                  "lender_name",
    # Loan
    "loan amount":           "loan_amount",
    "mortgage amount":       "loan_amount",
    # Property details
    "property type":         "property_type",
    "land use":              "property_type",
    "use code":              "property_type",
    "sqft":                  "sqft",
    "sq ft":                 "sqft",
    "living area":           "sqft",
    "bedrooms":              "bedrooms",
    "beds":                  "bedrooms",
    "bathrooms":             "bathrooms",
    "baths":                 "bathrooms",
    "year built":            "year_built",
    # APN / parcel
    "apn":                   "apn",
    "parcel number":         "apn",
    "parcel id":             "apn",
    "account number":        "apn",
    "tax id":                "apn",
    "assessor parcel number":"apn",
    # PropStream specific
    "mailing address":       "mailing_address",
    "mailing city":          "mailing_city",
    "mailing state":         "mailing_state",
    "mailing zip":           "mailing_zip",
    "absentee owner":        "absentee_owner",
    "phone 1":               "phone",
    "phone1":                "phone",
    "primary phone":         "phone",
    "email":                 "email",
    "email address":         "email",
    # Deed info
    "deed book":             "deed_book",
    "deed page":             "deed_page",
    "instrument number":     "deed_book",
}

# Financing type strings that indicate a cash sale
CASH_FINANCING_KEYWORDS = {
    "cash", "all cash", "no lender", "none", "private", "seller financed",
    "seller finance", "owner financed", "owner finance",
}

# Regex to detect LLC / Corp entity buyers
ENTITY_PATTERNS = re.compile(
    r"\b(LLC|L\.L\.C|INC|CORP|CORPORATION|LTD|LP|L\.P|TRUST|HOLDINGS|GROUP|"
    r"PROPERTIES|INVESTMENTS|VENTURES|REALTY|CAPITAL|FUND|PARTNERS|PARTNERSHIP|"
    r"ASSOCIATES|SOLUTIONS|ENTERPRISES|ACQUISITIONS)\b",
    re.IGNORECASE,
)

# Property type normalization
PROPERTY_TYPE_MAP: dict[str, str] = {
    "sfr": "SFR", "single family": "SFR", "single family residential": "SFR",
    "single-family": "SFR", "res": "SFR", "residential": "SFR",
    "duplex": "MFR", "triplex": "MFR", "fourplex": "MFR",
    "multifamily": "MFR", "multi family": "MFR", "multi-family": "MFR",
    "apt": "MFR", "apartment": "MFR",
    "condo": "Condo", "condominium": "Condo",
    "townhome": "Condo", "townhouse": "Condo",
    "land": "Land", "vacant land": "Land", "lot": "Land",
    "commercial": "Commercial", "comm": "Commercial",
    "industrial": "Commercial",
}


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class BuyerTxRow:
    """Normalized single row from a CSV (one transaction)."""
    grantee:          str = ""
    entity_name:      str = ""
    is_entity:        bool = False
    grantor:          str = ""
    property_address: str = ""
    city:             str = ""
    state:            str = "TX"
    zip_code:         str = ""
    county:           str = ""
    purchase_price:   Optional[float] = None
    purchase_date:    Optional[date]  = None
    cash_transaction: bool = False
    lender_name:      str = ""
    loan_amount:      Optional[float] = None
    property_type:    str = ""
    sqft:             Optional[int]   = None
    bedrooms:         Optional[int]   = None
    bathrooms:        Optional[float] = None
    year_built:       Optional[int]   = None
    apn:              str = ""
    deed_book:        str = ""
    deed_page:        str = ""
    phone:            str = ""
    email:            str = ""
    absentee_owner:   bool = False
    raw:              dict = field(default_factory=dict)
    row_num:          int  = 0
    error:            str  = ""


@dataclass
class ParseResult:
    """Complete result of parsing a buyer CSV file."""
    buyers:       list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    errors:       list[dict[str, Any]] = field(default_factory=list)
    log:          dict[str, Any]       = field(default_factory=dict)


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_buyer_csv(
    source: Union[str, io.TextIOBase],
    market: str = "",
    min_price: float = 0,
    max_price: float = 0,
    cash_only: bool = False,
    entities_only: bool = False,
    source_label: str = "county_csv",
    filename: str = "",
) -> ParseResult:
    """
    Parse a buyer CSV file and return normalized buyers + transactions.

    Args:
        source:         File path string or file-like object
        market:         Market tag (DFW, Houston, etc.) applied to all buyers
        min_price:      Filter: skip transactions below this price
        max_price:      Filter: skip transactions above this price (0 = no limit)
        cash_only:      Only include cash transactions
        entities_only:  Only include LLC/INC/Corp buyers
        source_label:   Value stored in buyer_import_log.source
        filename:       Original filename for the audit log

    Returns:
        ParseResult with buyers, transactions, errors, log
    """
    if isinstance(source, str):
        with open(source, newline="", encoding="utf-8-sig") as f:
            return _parse(f, market, min_price, max_price,
                          cash_only, entities_only, source_label, filename)
    return _parse(source, market, min_price, max_price,
                  cash_only, entities_only, source_label, filename)


def _parse(
    f: io.TextIOBase,
    market: str,
    min_price: float,
    max_price: float,
    cash_only: bool,
    entities_only: bool,
    source_label: str,
    filename: str,
) -> ParseResult:
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        return ParseResult(log={"status": "failed", "errors": [{"row": 0, "error": "Empty file or no headers"}]})

    col_map = _build_col_map(reader.fieldnames)
    rows_total = 0
    rows_skipped = 0
    errors: list[dict] = []

    # Group transactions by normalized entity key
    # entity_key → {"buyer_fields": {...}, "transactions": [...]}
    entity_groups: dict[str, dict] = {}

    for row_num, raw_row in enumerate(reader, start=2):
        rows_total += 1
        normalized = _normalize_row(raw_row, col_map, row_num)

        if normalized.error:
            errors.append({"row": row_num, "error": normalized.error})
            rows_skipped += 1
            continue

        # Apply filters
        if min_price > 0 and (normalized.purchase_price or 0) < min_price:
            rows_skipped += 1
            continue
        if max_price > 0 and (normalized.purchase_price or 0) > max_price:
            rows_skipped += 1
            continue
        if cash_only and not normalized.cash_transaction:
            rows_skipped += 1
            continue
        if entities_only and not normalized.is_entity:
            rows_skipped += 1
            continue

        entity_key = _entity_key(normalized)

        if entity_key not in entity_groups:
            entity_groups[entity_key] = {
                "buyer": _build_buyer_record(normalized, market),
                "transactions": [],
            }
        else:
            # Update buyer with richer data if available
            _merge_buyer_data(entity_groups[entity_key]["buyer"], normalized)

        tx = _build_transaction(normalized)
        entity_groups[entity_key]["transactions"].append(tx)

    # Flatten groups into output lists
    buyers: list[dict] = []
    transactions: list[dict] = []
    buyers_created = 0
    tx_created = 0

    for group in entity_groups.values():
        buyer = group["buyer"]
        buyer_txs = group["transactions"]

        # Aggregate signals
        from tools.buyer_intelligence_engine import aggregate_transactions, compute_ibie_score, assign_ibie_tier, compute_tags
        signals = aggregate_transactions(buyer_txs)
        buyer.update(signals)

        # Initial score
        score = compute_ibie_score(buyer)
        buyer["ibie_score"] = score
        buyer["ibie_tier"] = assign_ibie_tier(score)
        buyer["tags"] = compute_tags(buyer)

        buyers.append(buyer)
        buyers_created += 1
        transactions.extend(buyer_txs)
        tx_created += len(buyer_txs)

    log = {
        "source":              source_label,
        "filename":            filename,
        "market":              market,
        "rows_total":          rows_total,
        "rows_imported":       rows_total - rows_skipped,
        "buyers_created":      buyers_created,
        "transactions_created": tx_created,
        "rows_skipped":        rows_skipped,
        "errors":              errors,
        "status":              "complete",
    }

    logger.info(
        f"[buyer_csv] Parsed {rows_total} rows → "
        f"{buyers_created} buyers, {tx_created} transactions, {rows_skipped} skipped"
    )
    return ParseResult(buyers=buyers, transactions=transactions, errors=errors, log=log)


# ── Column mapping ────────────────────────────────────────────────────────────

def _build_col_map(fieldnames: list[str]) -> dict[str, str]:
    """Map actual CSV column names → canonical field names."""
    col_map: dict[str, str] = {}
    for col in fieldnames:
        key = col.strip().lower()
        if key in BUYER_COLUMN_MAP:
            col_map[col] = BUYER_COLUMN_MAP[key]
    return col_map


def _get(raw: dict, col_map: dict, canonical: str, default: str = "") -> str:
    """Retrieve a value from a raw CSV row by canonical field name."""
    for raw_col, canon in col_map.items():
        if canon == canonical:
            val = raw.get(raw_col, "")
            if val:
                return str(val).strip()
    return default


# ── Row normalizer ────────────────────────────────────────────────────────────

def _normalize_row(raw: dict, col_map: dict, row_num: int) -> BuyerTxRow:
    g = lambda f, d="": _get(raw, col_map, f, d)

    grantee = _clean_name(g("grantee"))
    if not grantee:
        return BuyerTxRow(row_num=row_num, error="Missing grantee/buyer name", raw=dict(raw))

    is_entity = bool(ENTITY_PATTERNS.search(grantee))
    entity_name = grantee if is_entity else ""

    # Purchase price
    price = _parse_money(g("purchase_price"))

    # Purchase date
    p_date = _parse_date(g("purchase_date"))

    # Cash detection
    cash_raw = g("cash_transaction").lower()
    financing = g("financing_type").lower()
    cash_tx = (
        cash_raw in ("1", "true", "yes", "y", "cash", "x") or
        financing.lower() in CASH_FINANCING_KEYWORDS or
        (not g("lender_name") and not g("loan_amount") and not financing)
    )

    # Zip code — 5 digits only
    zip_raw = g("zip_code")
    zip_clean = re.sub(r"\D", "", zip_raw)[:5] if zip_raw else ""

    # APN — strip dashes/spaces
    apn = re.sub(r"[\s\-]", "", g("apn"))

    # Property type normalization
    raw_type = g("property_type").strip().lower()
    prop_type = PROPERTY_TYPE_MAP.get(raw_type, raw_type.upper() if raw_type else "")

    return BuyerTxRow(
        grantee=grantee,
        entity_name=entity_name,
        is_entity=is_entity,
        grantor=_clean_name(g("grantor")),
        property_address=g("property_address"),
        city=g("city"),
        state=g("state") or "TX",
        zip_code=zip_clean,
        county=g("county"),
        purchase_price=price,
        purchase_date=p_date,
        cash_transaction=cash_tx,
        lender_name=g("lender_name"),
        loan_amount=_parse_money(g("loan_amount")),
        property_type=prop_type,
        sqft=_safe_int(g("sqft")),
        bedrooms=_safe_int(g("bedrooms")),
        bathrooms=_safe_float_val(g("bathrooms")),
        year_built=_safe_int(g("year_built")),
        apn=apn,
        deed_book=g("deed_book"),
        deed_page=g("deed_page"),
        phone=_clean_phone(g("phone")),
        email=g("email").lower().strip(),
        absentee_owner=g("absentee_owner").lower() in ("1", "true", "yes", "y"),
        raw=dict(raw),
        row_num=row_num,
    )


def _entity_key(row: BuyerTxRow) -> str:
    """Dedup key: normalized entity name (or personal name if not an entity)."""
    name = row.entity_name or row.grantee
    return re.sub(r"\s+", " ", name.upper().strip())


# ── Record builders ───────────────────────────────────────────────────────────

def _build_buyer_record(row: BuyerTxRow, market: str) -> dict[str, Any]:
    """Build a buyers table dict from the first transaction row for an entity."""
    name_parts = _split_name(row.grantee)
    return {
        "first_name":    name_parts[0],
        "last_name":     name_parts[1],
        "company":       row.entity_name or "",
        "entity_name":   row.entity_name,
        "phone":         row.phone,
        "email":         row.email,
        "market":        market,
        "cash_buyer":    row.cash_transaction,
        "repeat_buyer":  False,
        "source":        "csv_import",
        "active":        True,
        "email_opt_in":  bool(row.email),
        "sms_opt_in":    bool(row.phone),
        "deals_closed":  0,
        "pof_verified":  False,
        "tier":          "C",
        "ibie_score":    0.0,
        "ibie_tier":     "D",
        "tags":          [],
    }


def _merge_buyer_data(existing: dict, row: BuyerTxRow) -> None:
    """Fill in any missing buyer fields from a later transaction row."""
    if not existing.get("phone") and row.phone:
        existing["phone"] = row.phone
    if not existing.get("email") and row.email:
        existing["email"] = row.email
    if row.cash_transaction:
        existing["cash_buyer"] = True


def _build_transaction(row: BuyerTxRow) -> dict[str, Any]:
    """Build a buyer_transactions table dict from a normalized row."""
    return {
        "property_address": row.property_address,
        "city":             row.city,
        "state":            row.state,
        "zip_code":         row.zip_code,
        "county":           row.county,
        "purchase_price":   row.purchase_price,
        "purchase_date":    row.purchase_date.isoformat() if row.purchase_date else None,
        "cash_transaction": row.cash_transaction,
        "lender_name":      row.lender_name,
        "loan_amount":      row.loan_amount,
        "property_type":    row.property_type,
        "sqft":             row.sqft,
        "bedrooms":         row.bedrooms,
        "bathrooms":        row.bathrooms,
        "year_built":       row.year_built,
        "apn":              row.apn or None,
        "deed_book":        row.deed_book,
        "deed_page":        row.deed_page,
        "grantor":          row.grantor,
        "grantee":          row.grantee,
        "source":           "csv",
        "raw_data":         row.raw,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_name(raw: str) -> str:
    if not raw:
        return ""
    # Normalize unicode, strip extra whitespace
    name = unicodedata.normalize("NFC", raw.strip())
    name = re.sub(r"\s+", " ", name)
    return name


def _split_name(full_name: str) -> tuple[str, str]:
    """Best-effort split of 'FirstName LastName (or entity)' into (first, last)."""
    parts = full_name.strip().split()
    if len(parts) == 0:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))


def _parse_money(val: str) -> Optional[float]:
    if not val:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(val))
        if not cleaned:
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


DATE_FORMATS = [
    "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%Y/%m/%d",
    "%m/%d/%y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y",
]


def _parse_date(val: str) -> Optional[date]:
    if not val:
        return None
    val = val.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val[:10], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _clean_phone(raw: str) -> str:
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return f"+{digits}" if digits else ""


def _safe_int(val: str) -> Optional[int]:
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _safe_float_val(val: str) -> Optional[float]:
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None
