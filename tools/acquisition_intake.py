"""Pure native-form intake preparation; no CRM writes, matching or outreach.

All answers are seller assertions. Qualification is preliminary completeness,
not ownership verification, valuation, contact permission or offer approval.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import copy
import json
import hashlib
import re
from typing import Any

VERSION = 'seller-intake-v1'
ALIASES = {
    'street_address': 'property_address', 'address': 'property_address',
    'zip': 'zip_code', 'phone_number': 'phone', 'reason_for_selling': 'motivation',
    'why_selling': 'motivation', 'when_to_sell': 'timeline', 'close_timeline': 'timeline',
    'property_condition': 'condition', 'price': 'asking_price',
    'ownership_authority': 'authority', 'authorized_to_sell': 'authority',
}
FIELDS = frozenset(('property_address', 'city', 'state', 'zip_code', 'county',
                    'full_name', 'first_name', 'last_name', 'phone', 'email',
                    'motivation', 'timeline', 'condition', 'asking_price',
                    'occupancy', 'authority', 'interested'))
REQUIRED = ('property_address', 'city', 'state', 'authority', 'condition',
            'timeline', 'motivation', 'asking_price')
YES = frozenset(('yes', 'true', '1', 'owner', 'authorized representative'))
NO = frozenset(('no', 'false', '0'))


def _money(value: str) -> str | None:
    # US dollars only; no guessed ranges, suffixes, non-US separators or negatives.
    if not re.fullmatch(r'\$?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?', value):
        return None
    try:
        amount = Decimal(value.replace('$', '').replace(',', ''))
    except InvalidOperation:
        return None
    if amount > Decimal('1000000000'):
        return None
    return str(amount.quantize(Decimal('.01')))


def prepare_facebook_intake(*, leadgen_id: str, provider_data: dict[str, Any]) -> dict[str, Any]:
    """Prepare deterministic evidence for one authorized provider retrieval.

    Caller must verify subscription, receipt and current lease. This function
    never accepts a workspace, canonical property ID, permission or offer input.
    The original provider response belongs in access-controlled receipt storage.
    """
    if not isinstance(leadgen_id, str) or not leadgen_id.strip():
        raise ValueError('Missing native lead identity')
    if not isinstance(provider_data, dict) or str(provider_data.get('id', '')) != leadgen_id:
        raise ValueError('Provider lead identity mismatch')
    for name in ('form_id', 'created_time'):
        value = provider_data.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > 200):
            raise ValueError('Invalid provider metadata')
    # Preserve the exact returned consent object, including false/empty/missing
    # distinctions. It is evidence, never an interpreted permission grant.
    evidence_keys = ('id','form_id','created_time','field_data','custom_disclaimer_responses',
                     'ad_id','adset_id','campaign_id','is_organic','platform')
    provider_evidence = {key: copy.deepcopy(provider_data[key]) for key in evidence_keys if key in provider_data}
    try:
        encoded = json.dumps(provider_evidence, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, TypeError):
        raise ValueError('Invalid provider evidence') from None
    if len(encoded) > 524288:
        raise ValueError('Provider evidence exceeds intake limit')
    disclaimers = provider_data.get('custom_disclaimer_responses')
    if 'custom_disclaimer_responses' in provider_data and not isinstance(disclaimers, list):
        raise ValueError('Invalid provider disclaimer evidence')
    raw_fields = provider_data.get('field_data')
    normalized = normalize_seller_fields(raw_fields)
    return {
        'version': VERSION, 'source_type': 'facebook_native_form',
        'external_lead_id': leadgen_id,
        'provider_form_id': str(provider_data.get('form_id') or ''),
        'submitted_at': provider_data.get('created_time'),
        'provider_evidence': provider_evidence,
        'provider_evidence_hash': hashlib.sha256(encoded).hexdigest(),
        **normalized,
    }


def normalize_seller_fields(raw_fields):
    """Shared seller assertions; no source identity, permission or canonical match."""
    if not isinstance(raw_fields, list) or len(raw_fields) > 100:
        raise ValueError('Invalid native field data')
    answers: dict[str, str] = {}
    conflicts: set[str] = set()
    malformed: set[str] = set()
    # Store all occurrences, including duplicate names and blank values. Never
    # allow an alias or later answer to silently replace conflicting evidence.
    evidence: list[dict[str, Any]] = []
    total_bytes = 0
    for field in raw_fields:
        if not isinstance(field, dict) or not isinstance(field.get('name'), str):
            raise ValueError('Invalid native field entry')
        name = field['name']
        values = field.get('values')
        if len(name) > 200 or not isinstance(values, list) or len(values) > 100:
            raise ValueError('Invalid native field values')
        if any(not isinstance(v, str) or len(v) > 10000 for v in values):
            raise ValueError('Invalid native answer')
        total_bytes += len(name.encode()) + sum(len(v.encode()) for v in values)
        if total_bytes > 1048576:
            raise ValueError('Native answers exceed intake limit')
        canonical = ALIASES.get(name.strip().lower(), name.strip().lower())
        evidence.append({'name': name, 'values': list(values), 'canonical_field': canonical if canonical in FIELDS else None})
        if canonical not in FIELDS:
            continue  # Consent/custom fields retained, never interpreted as permission.
        distinct = set(v.strip() for v in values if v.strip())
        if len(distinct) > 1:
            conflicts.add(canonical)
            continue
        value = next(iter(distinct), '')
        if canonical in answers and answers[canonical] != value:
            conflicts.add(canonical)
        else:
            answers[canonical] = value
    for field in conflicts:
        answers.pop(field, None)
    price = None
    if answers.get('asking_price'):
        price = _money(answers['asking_price'])
        if price is None:
            malformed.add('asking_price')
    authority_text = answers.get('authority', '').lower()
    authority = True if authority_text in YES else False if authority_text in NO else None
    if authority_text and authority is None:
        malformed.add('authority')
    missing = [name for name in REQUIRED if not answers.get(name)]
    if not answers.get('phone') and not answers.get('email'):
        missing.append('contact')
    state = answers.get('state', '').upper()
    reasons: list[str] = []
    if conflicts:
        reasons.append('CONFLICTING_ANSWERS')
    if malformed:
        reasons.append('AMBIGUOUS_ANSWERS')
    if missing:
        reasons.append('MISSING_REQUIRED_ANSWERS')
    if authority is False:
        reasons.append('SELLER_DENIES_AUTHORITY')
    if answers.get('interested', '').lower() in NO:
        reasons.append('SELLER_NOT_INTERESTED')
    if state and state not in ('TX', 'TEXAS'):
        reasons.append('TERRITORY_REVIEW_REQUIRED')
    if conflicts or malformed:
        classification = 'requires_human_review'
    elif authority is False or 'SELLER_NOT_INTERESTED' in reasons:
        classification = 'unqualified'
    elif missing:
        classification = 'incomplete'
    else:
        # County and address are not verified by a free-text form submission.
        # Only a subsequent canonical property resolution may qualify territory.
        classification = 'requires_human_review'
    if classification == 'requires_human_review' and not missing:
        reasons.append('CANONICAL_PROPERTY_REVIEW_REQUIRED')
    return {
        'answers': answers, 'field_evidence': evidence,
        'asking_price': price, 'authority_asserted': authority,
        'classification': classification, 'reason_codes': reasons,
        'missing_fields': missing, 'conflicting_fields': sorted(conflicts),
        'ambiguous_fields': sorted(malformed),
        'property_verified': False, 'ownership_verified': False,
        'contact_permission_granted': False, 'outreach_authorized': False,
        'binding_offer': False,
    }
