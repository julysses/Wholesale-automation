"""Immutable native inquiry evidence; never invent a website submission."""
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from tools.facebook_consent import normalize_us_phone


def save_submission(sb, lead_id, answers):
    consent = answers["_facebook_consent"]
    leadgen_id = str(consent["leadgen_id"])
    receipt_id = str(uuid5(NAMESPACE_URL, "wholesaleos:facebook:submission:" + leadgen_id))
    try:
        phone = normalize_us_phone(consent.get("phone"))
    except ValueError:
        phone = None
    row = {
        "id": receipt_id, "lead_id": lead_id, "leadgen_id": leadgen_id,
        "form_id": consent["form_id"], "submitted_at": consent["submitted_at"],
        "phone_number": phone, "raw_answers": answers,
    }
    try:
        saved = sb.table("facebook_lead_submissions").upsert(
            row, on_conflict="id", ignore_duplicates=True,
        ).execute().data
    except Exception as exc:
        # Concurrent inserts can collide on a secondary UNIQUE index even when
        # ON CONFLICT(id) ignores the primary key. Recover only the exact receipt
        # below, with the same immutable evidence checks as an ordinary retry.
        if (getattr(exc, "code", None) or getattr(exc, "pgcode", None)) != "23505":
            raise
        saved = None
    if not saved:
        saved = sb.table("facebook_lead_submissions").select("*").eq("id", receipt_id).limit(1).execute().data
    if not isinstance(saved, list) or len(saved) != 1:
        raise RuntimeError("Facebook inquiry receipt persistence was not confirmed")
    actual = saved[0]
    # recorded_at reflects ingestion time; all provider/input evidence is frozen.
    def manifest(value):
        copy = deepcopy(value)
        copy.get("_facebook_consent", {}).pop("recorded_at", None)
        return copy
    if (any(actual.get(k) != v for k, v in row.items() if k != "raw_answers")
            or manifest(actual.get("raw_answers", {})) != manifest(answers)):
        raise RuntimeError("Facebook inquiry receipt conflicts with saved evidence; review required")
    return actual["raw_answers"]
