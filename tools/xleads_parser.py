"""
XLeads CSV/API parser for the Vacant Land Wholesaling Module.

Converts XLeads exports into LandLead records ready for Supabase insert.
Handles both the standard XLeads CSV column names and common variants.

Usage:
    from tools.xleads_parser import parse_xleads_csv, parse_xleads_row

    records = parse_xleads_csv("path/to/export.csv")
    # → list[dict] ready for supabase.from('land_leads').insert(records)
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Column aliases ─────────────────────────────────────────────────────────────
# Maps every known XLeads column name variant → canonical internal key
COLUMN_MAP: dict[str, str] = {
    # Address
    "property address":      "property_address",
    "address":               "property_address",
    "situs address":         "property_address",
    "site address":          "property_address",

    # City / State / Zip
    "city":                  "city",
    "situs city":            "city",
    "state":                 "state",
    "situs state":           "state",
    "zip":                   "zip_code",
    "zip code":              "zip_code",
    "situs zip":             "zip_code",
    "postal code":           "zip_code",

    # County / APN
    "county":                "county",
    "apn":                   "apn",
    "parcel number":         "apn",
    "parcel id":             "apn",
    "assessor parcel number":"apn",

    # Owner
    "owner name":            "owner_name",
    "owner":                 "owner_name",
    "owner full name":       "owner_name",
    "owner mailing address": "owner_mailing_address",
    "mailing address":       "owner_mailing_address",
    "owner phone 1":         "owner_phone_1",
    "phone 1":               "owner_phone_1",
    "phone":                 "owner_phone_1",
    "owner phone 2":         "owner_phone_2",
    "phone 2":               "owner_phone_2",
    "owner email":           "owner_email",
    "email":                 "owner_email",

    # Lot / size
    "lot size (acres)":      "lot_size_acres",
    "lot size acres":        "lot_size_acres",
    "acreage":               "lot_size_acres",
    "acres":                 "lot_size_acres",
    "lot size (sqft)":       "lot_size_sqft",
    "lot size sqft":         "lot_size_sqft",
    "lot sqft":              "lot_size_sqft",

    # Financial
    "tav":                   "tav",
    "tax assessed value":    "tav",
    "assessed value":        "tav",
    "land value":            "tav",
    "market value":          "tav",
    "asking price":          "asking_price",
    "list price":            "asking_price",

    # Zoning
    "zoning":                "zoning_raw",
    "zoning code":           "zoning_raw",
    "zoning description":    "zoning_raw",
    "land use":              "zoning_raw",

    # Utilities
    "water":                 "water_source_raw",
    "water source":          "water_source_raw",
    "sewer":                 "sewage_raw",
    "sewage":                "sewage_raw",

    # XLeads internal
    "xleads id":             "xleads_id",
    "record id":             "xleads_id",
    "id":                    "xleads_id",
}

# ── Zoning normalizer ──────────────────────────────────────────────────────────
def _normalize_zoning(raw: str) -> str:
    r = raw.lower()
    if any(x in r for x in ["r1", "r-1", "single family", "sf", "res", "residential"]):
        return "single_family"
    if any(x in r for x in ["r2", "r3", "r4", "mf", "multi", "apartment", "multifamily"]):
        return "multifamily"
    if any(x in r for x in ["c1", "c2", "commercial", "retail", "office", "industrial"]):
        return "commercial"
    if any(x in r for x in ["ag", "agricultural", "farm", "rural", "ranch"]):
        return "agricultural"
    if any(x in r for x in ["mix", "pud", "planned", "mu"]):
        return "mixed"
    return "unknown"

# ── Utility normalizers ────────────────────────────────────────────────────────
def _normalize_water(raw: str) -> str:
    r = raw.lower()
    if any(x in r for x in ["city", "municipal", "public", "utility"]):
        return "city"
    if "well" in r:
        return "well"
    if any(x in r for x in ["none", "no ", "n/a", "unavailable"]):
        return "none"
    return "unknown"

def _normalize_sewage(raw: str) -> str:
    r = raw.lower()
    if any(x in r for x in ["city", "municipal", "sewer", "public"]):
        return "city_sewer"
    if "septic" in r:
        return "septic"
    if any(x in r for x in ["none", "no ", "n/a", "unavailable"]):
        return "none"
    return "unknown"

# ── Phone cleaner ──────────────────────────────────────────────────────────────
def _clean_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return None if len(digits) < 7 else digits

# ── Dollar parser ──────────────────────────────────────────────────────────────
def _parse_money(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[$,\s]", "", raw)
    try:
        return float(cleaned)
    except ValueError:
        return None

# ── Core row parser ────────────────────────────────────────────────────────────
@dataclass
class ParseResult:
    records: list[dict]   = field(default_factory=list)
    skipped: list[dict]   = field(default_factory=list)   # {row_num, reason}
    warnings: list[str]   = field(default_factory=list)


def parse_xleads_row(raw_row: dict[str, str], row_num: int = 0) -> tuple[Optional[dict], Optional[str]]:
    """
    Parse a single CSV row dict into a land_leads insert payload.

    Returns (record, None) on success.
    Returns (None, reason) if the row should be skipped.
    """
    # Normalize column names
    row: dict[str, str] = {k.strip().lower(): v.strip() for k, v in raw_row.items()}
    mapped: dict[str, str] = {}
    for raw_col, val in row.items():
        canonical = COLUMN_MAP.get(raw_col)
        if canonical and val:
            mapped[canonical] = val

    # ── Required fields ───────────────────────────────────────────────────────
    property_address = mapped.get("property_address", "").strip()
    owner_name       = mapped.get("owner_name", "").strip()
    city             = mapped.get("city", "").strip()

    if not property_address:
        return None, f"Row {row_num}: missing property_address"
    if not owner_name:
        return None, f"Row {row_num}: missing owner_name"
    if not city:
        return None, f"Row {row_num}: missing city"

    # ── Build record ──────────────────────────────────────────────────────────
    record: dict = {
        "source":             "xleads",
        "property_address":   property_address,
        "owner_name":         owner_name,
        "city":               city,
        "state":              mapped.get("state", "TX").upper()[:2],
        "zip_code":           mapped.get("zip_code"),
        "county":             mapped.get("county"),
        "apn":                mapped.get("apn"),
        "owner_mailing_address": mapped.get("owner_mailing_address"),
        "owner_email":        mapped.get("owner_email"),
        "xleads_id":          mapped.get("xleads_id"),

        # Defaults
        "status":             "new",
        "water_source":       "unknown",
        "sewage":             "unknown",
        "infill_lot":         False,
        "dnc":                False,
        "contact_attempts":   0,
        "sms_sequence_active": False,
    }

    # Phones
    if p1 := mapped.get("owner_phone_1"):
        record["owner_phone_1"] = _clean_phone(p1)
    if p2 := mapped.get("owner_phone_2"):
        record["owner_phone_2"] = _clean_phone(p2)

    # Financials
    if tav_raw := mapped.get("tav"):
        record["tav"] = _parse_money(tav_raw)
    if ask_raw := mapped.get("asking_price"):
        record["asking_price"] = _parse_money(ask_raw)

    # Lot size
    if acres_raw := mapped.get("lot_size_acres"):
        try:
            acres = float(re.sub(r"[^\d.]", "", acres_raw))
            record["lot_size_acres"] = acres
            record["lot_size_sqft"]  = round(acres * 43560)
        except ValueError:
            pass
    elif sqft_raw := mapped.get("lot_size_sqft"):
        try:
            sqft = int(re.sub(r"[^\d]", "", sqft_raw))
            record["lot_size_sqft"]  = sqft
            record["lot_size_acres"] = round(sqft / 43560, 4)
        except ValueError:
            pass

    # Zoning
    if zoning_raw := mapped.get("zoning_raw"):
        record["zoning_raw"] = zoning_raw
        record["zoning"]     = _normalize_zoning(zoning_raw)

    # Utilities
    if water_raw := mapped.get("water_source_raw"):
        record["water_source"] = _normalize_water(water_raw)
    if sewage_raw := mapped.get("sewage_raw"):
        record["sewage"] = _normalize_sewage(sewage_raw)

    # Clean None values
    record = {k: v for k, v in record.items() if v is not None and v != ""}

    return record, None


def parse_xleads_csv(
    source: str | io.TextIOBase,
    dedupe_field: str = "apn",
) -> ParseResult:
    """
    Parse an XLeads CSV file or text stream into land_leads records.

    Args:
        source: File path string or file-like object.
        dedupe_field: Field to use for deduplication (default: 'apn').

    Returns:
        ParseResult with .records, .skipped, .warnings
    """
    result = ParseResult()
    seen: set[str] = set()

    # Open file if path given
    if isinstance(source, str):
        f = open(source, encoding="utf-8-sig", newline="")  # utf-8-sig strips BOM
    else:
        f = source

    try:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            result.warnings.append("CSV has no header row")
            return result

        for i, raw_row in enumerate(reader, start=2):  # start=2 because row 1 is header
            record, skip_reason = parse_xleads_row(raw_row, row_num=i)

            if skip_reason:
                result.skipped.append({"row": i, "reason": skip_reason})
                continue

            # Deduplication
            dedup_val = record.get(dedupe_field) or record.get("xleads_id") or record["property_address"]
            if dedup_val in seen:
                result.skipped.append({"row": i, "reason": f"Duplicate {dedupe_field}: {dedup_val}"})
                continue
            seen.add(dedup_val)

            result.records.append(record)

    finally:
        if isinstance(source, str):
            f.close()

    logger.info(
        "XLeads parse complete: %d imported, %d skipped",
        len(result.records), len(result.skipped)
    )
    return result


# ── Infill lot detector ────────────────────────────────────────────────────────
def flag_infill_lots(records: list[dict]) -> list[dict]:
    """
    Heuristic: mark a land lead as an infill lot if its address pattern
    suggests it sits between two houses (common in urban/suburban areas).

    In practice, this should be supplemented by a GIS check, but this
    catches the obvious cases from address data alone (e.g., fractional
    lot numbers, 'Lot' in the address, etc.).
    """
    infill_patterns = [
        r"\blot\b",          # "Lot 7" in address
        r"\bvacant\b",
        r"\b\d+[a-z]\b",    # 123a, 456b — subdivided lot indicators
    ]
    compiled = [re.compile(p, re.IGNORECASE) for p in infill_patterns]

    for record in records:
        addr = record.get("property_address", "")
        if any(p.search(addr) for p in compiled):
            record["infill_lot"] = True

    return records


# ── CLI helper ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json

    if len(sys.argv) < 2:
        print("Usage: python xleads_parser.py <path_to_csv> [--json]")
        sys.exit(1)

    path = sys.argv[1]
    output_json = "--json" in sys.argv

    result = parse_xleads_csv(path)
    result.records = flag_infill_lots(result.records)

    if output_json:
        print(json.dumps(result.records, indent=2, default=str))
    else:
        print(f"✓ Parsed {len(result.records)} records, skipped {len(result.skipped)}")
        if result.skipped:
            print("\nSkipped rows:")
            for s in result.skipped[:10]:
                print(f"  Row {s['row']}: {s['reason']}")
        if result.records:
            print("\nFirst record preview:")
            first = result.records[0]
            for k, v in first.items():
                print(f"  {k}: {v}")
