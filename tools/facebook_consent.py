"""Consent specification for the immutable Hilltop native form.

Never infer consent from contact details, a free-text question, or an unknown
form. Keep the provider's raw checkbox answers with the exact disclosure.
"""
from datetime import datetime, timezone

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
