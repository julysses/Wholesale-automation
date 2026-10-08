"""Consent specification for the immutable Hilltop native form.

Never infer consent from contact details, a free-text question, or an unknown
form. Keep the provider's raw checkbox answers with the exact disclosure.
"""
from datetime import datetime, timezone
import re
from types import SimpleNamespace


def normalize_us_phone(value) -> str:
    value = str(value or '').strip()
    if not re.fullmatch(r'\+?[0-9().\s-]+', value):
        raise ValueError('A valid US phone number is required')
    digits = re.sub(r'\D', '', value)
    if len(digits) == 10:
        digits = '1' + digits
    if not re.fullmatch(r'1[2-9][0-9]{9}', digits):
        raise ValueError('A valid US phone number is required')
    return '+' + digits

HILLTOP_CONSENT_FORM_ID = "1548364970390755"
SMS_DISCLOSURE = "I agree to receive recurring automated text messages from Hilltop Home Co., a DBA of The Jays Dallas, LLC, about my property inquiry, offer updates, appointment reminders and closing updates. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase or receiving an offer."
AI_DISCLOSURE = "I agree to receive automated calls using an AI-generated or artificial voice from Hilltop Home Co., a DBA of The Jays Dallas, LLC, at the number I provide about my property inquiry, offers and appointments. Calls may be recorded. Consent is not a condition of purchase or receiving an offer. I may revoke consent at any time by calling 214-701-0100 or emailing julio@hilltophome.co."
# Verified against native test1116758057469583: Meta uses normalized disclosure
# text as the key for this form, rather than positional optional_1/optional_2.
SMS_CHECKBOX_KEY = SMS_DISCLOSURE.lower().replace(" ", "_")
AI_CHECKBOX_KEY = AI_DISCLOSURE.lower().replace(" ", "_")


def facebook_consent_record(lead_data, leadgen_id: str) -> dict:
    form_id = str(getattr(lead_data, "form_id", "") or "")
    responses = getattr(lead_data, "custom_disclaimer_responses", []) or []
    created_time = getattr(lead_data, "created_time", None)
    recognized = form_id == HILLTOP_CONSENT_FORM_ID and bool(created_time)

    def checked(key):
        matches = [row for row in responses if isinstance(row, dict) and row.get("checkbox_key") == key]
        # Missing, duplicate or unexpected values never authorize contact.
        return recognized and len(matches) == 1 and matches[0].get("is_checked") in ("1", 1, True)

    return {
        "source": "facebook_native_form", "form_id": form_id,
        "leadgen_id": leadgen_id, "submitted_at": created_time,
        "phone": (getattr(lead_data, "fields", {}) or {}).get("phone_number", ""),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recognized_form": recognized, "raw_responses": responses,
        "sms": {"accepted": checked(SMS_CHECKBOX_KEY), "checkbox_key": SMS_CHECKBOX_KEY,
                "disclosure": SMS_DISCLOSURE if recognized else None},
        "ai_calls": {"accepted": checked(AI_CHECKBOX_KEY), "checkbox_key": AI_CHECKBOX_KEY,
                     "disclosure": AI_DISCLOSURE if recognized else None},
    }


def matching_native_consent(receipt, phone: str, lead: dict, channel: str) -> bool:
    """Revalidate immutable native evidence independently for each channel."""
    if channel not in ('sms', 'ai_calls') or not isinstance(receipt, dict):
        return False
    if receipt.get('source') != 'facebook_native_form' or lead.get('source') != 'facebook_lead_ad':
        return False
    try:
        submitted = datetime.fromisoformat(receipt['submitted_at'].replace('Z', '+00:00'))
        if submitted.tzinfo is None or submitted > datetime.now(timezone.utc):
            return False
        phone = normalize_us_phone(phone)
        if normalize_us_phone(receipt.get('phone')) != phone or normalize_us_phone(lead.get('owner_phone_1')) != phone:
            return False
        leadgen = str(receipt.get('leadgen_id') or '')
        if not leadgen or lead.get('internal_notes', '') != f'FB leadgen_id={leadgen}':
            return False
        actual = facebook_consent_record(SimpleNamespace(form_id=receipt.get('form_id'),
            created_time=receipt.get('submitted_at'), custom_disclaimer_responses=receipt.get('raw_responses')), leadgen)
        saved = receipt.get(channel, {})
        return (actual[channel]['accepted'] is True and saved.get('accepted') is True
                and saved.get('disclosure') == actual[channel]['disclosure'])
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
