from types import SimpleNamespace

import pytest

from tools.facebook_consent import HILLTOP_CONSENT_FORM_ID, facebook_consent_record


@pytest.mark.parametrize("sms,ai,expected_sms,expected_ai", [
    ("1", "", True, False), ("", "1", False, True),
    ("", "", False, False), ("true", "yes", False, False),
])
def test_channels_require_their_own_checked_box(sms, ai, expected_sms, expected_ai):
    data = SimpleNamespace(form_id=HILLTOP_CONSENT_FORM_ID, created_time="2026-10-07T20:00:00Z",
        custom_disclaimer_responses=[{"checkbox_key": "optional_1", "is_checked": sms},
                                     {"checkbox_key": "optional_2", "is_checked": ai}])
    receipt = facebook_consent_record(data, "test-lead")
    assert receipt["sms"]["accepted"] is expected_sms
    assert receipt["ai_calls"]["accepted"] is expected_ai
    assert receipt["raw_responses"] == data.custom_disclaimer_responses
    assert receipt["submitted_at"] == data.created_time
    assert "STOP" in receipt["sms"]["disclosure"]


@pytest.mark.parametrize("form,time,responses", [
    ("unknown", "2026-10-07T20:00:00Z", [{"checkbox_key": "optional_1", "is_checked": "1"}]),
    (HILLTOP_CONSENT_FORM_ID, None, [{"checkbox_key": "optional_1", "is_checked": "1"}]),
    (HILLTOP_CONSENT_FORM_ID, "2026-10-07T20:00:00Z", []),
    (HILLTOP_CONSENT_FORM_ID, "2026-10-07T20:00:00Z", [{"checkbox_key": "optional_1", "is_checked": "1"}] * 2),
])
def test_ambiguous_consent_never_authorizes_sms(form, time, responses):
    receipt = facebook_consent_record(SimpleNamespace(form_id=form, created_time=time,
        custom_disclaimer_responses=responses), "test-lead")
    assert receipt["sms"]["accepted"] is False
