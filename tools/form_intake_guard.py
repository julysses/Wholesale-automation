"""Spam screening for public form intake.

Suspicious inquiries are never dropped. They are saved as quarantined receipts
so an operator can review and release them, but they create no lead, owner
alert, task or SMS until released through the admin recovery route.

Signals, in order of confidence:
  1. Honeypot: a hidden field that people never see and bots fill in.
  2. Source key: for forms that are only submitted server-to-server by our
     own website, a shared secret header proves the request came through it.
  3. Velocity: the same email reused within minutes under a different name or
     phone, too many inquiries from one email, or a flood on one form.

Velocity lookups fail open: a database hiccup must never block a real seller.
IP addresses are not used, because the website proxy makes them unreliable.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

HONEYPOT_FIELDS = ("company_website", "_hp")
INTAKE_KEY_HEADER = "x-wholesaleos-intake-key"

IDENTITY_WINDOW = timedelta(minutes=10)
EMAIL_REPEAT_LIMIT = 3          # this many earlier inquiries from one email → quarantine
FORM_FLOOD_WINDOW = timedelta(minutes=5)
FORM_FLOOD_LIMIT = 20           # earlier inquiries on one form inside the window


def honeypot_tripped(raw_answers: dict[str, Any]) -> bool:
    for field in HONEYPOT_FIELDS:
        value = raw_answers.get(field)
        if value not in (None, "", False):
            return True
    return False


def _key_required_slugs() -> set[str]:
    raw = os.getenv("FORM_INTAKE_KEY_REQUIRED_SLUGS", "")
    return {slug.strip() for slug in raw.split(",") if slug.strip()}


def source_key_problem(form_slug: Optional[str], header_value: Optional[str]) -> Optional[str]:
    """Return a reason when a website-only form lacks a valid source key."""
    if not form_slug or form_slug not in _key_required_slugs():
        return None
    secret = os.getenv("FORM_INTAKE_SHARED_SECRET", "")
    if not secret:
        logger.error("[intake_guard] %s requires a source key but none is configured", form_slug)
        return "source_key_unconfigured"
    if not header_value or not hmac.compare_digest(header_value.encode(), secret.encode()):
        return "unverified_source"
    return None


def _identity(answers: dict[str, Any]) -> tuple[str, str]:
    name = " ".join(str(answers.get(k, "")).strip().lower() for k in ("first_name", "last_name")).strip()
    phone = re.sub(r"\D", "", str(answers.get("phone", "")))[-10:]
    return name, phone


def velocity_reasons(
    supabase,
    form_id: str,
    answers: dict[str, Any],
    request_id: Optional[str],
    now: Optional[datetime] = None,
) -> list[str]:
    """Look at recent receipts. Any lookup failure returns no reasons."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    email = str(answers.get("email", "")).strip()
    if email:
        try:
            query = (supabase.table("lead_form_submissions")
                     .select("id,raw_answers")
                     .eq("raw_answers->>email", email)
                     .gte("created_at", (now - IDENTITY_WINDOW).isoformat()))
            if request_id:
                query = query.neq("id", request_id)
            rows = query.limit(25).execute().data
        except Exception:
            logger.warning("[intake_guard] email velocity lookup failed", exc_info=True)
            rows = None
        if isinstance(rows, list) and rows:
            name, phone = _identity(answers)
            for row in rows:
                prior = row.get("raw_answers") if isinstance(row, dict) else None
                if not isinstance(prior, dict):
                    continue
                prior_name, prior_phone = _identity(prior)
                if (name and prior_name and prior_name != name) or (phone and prior_phone and prior_phone != phone):
                    reasons.append("email_reused_with_different_identity")
                    break
            if len(rows) >= EMAIL_REPEAT_LIMIT:
                reasons.append("email_repeat_limit")
    try:
        flood = (supabase.table("lead_form_submissions")
                 .select("id", count="exact")
                 .eq("form_id", form_id)
                 .gte("created_at", (now - FORM_FLOOD_WINDOW).isoformat())
                 .limit(1).execute().count)
    except Exception:
        logger.warning("[intake_guard] form flood lookup failed", exc_info=True)
        flood = None
    if isinstance(flood, int) and not isinstance(flood, bool) and flood >= FORM_FLOOD_LIMIT:
        reasons.append("form_flood")
    return reasons


def assess_submission(
    supabase,
    form_config: dict,
    answers: dict[str, Any],
    raw_answers: dict[str, Any],
    source_key: Optional[str],
    request_id: Optional[str],
) -> list[str]:
    """Return quarantine reasons; an empty list means process normally."""
    reasons: list[str] = []
    if honeypot_tripped(raw_answers):
        reasons.append("honeypot")
    key_problem = source_key_problem(form_config.get("slug"), source_key)
    if key_problem:
        reasons.append(key_problem)
    reasons.extend(velocity_reasons(supabase, str(form_config["id"]), answers, request_id))
    return reasons
