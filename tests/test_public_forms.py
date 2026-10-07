from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from web.app import app
from web.api import lead_forms_api as forms


QUESTIONS = [
    {"field_name": "first_name", "label": "First name", "type": "text", "required": True},
    {"field_name": "phone", "label": "Phone", "type": "tel", "required": True},
    {"field_name": "sms_opt_in", "label": "SMS consent", "type": "checkbox", "required": True},
]
ANSWERS = {"first_name": "Test", "phone": "(214) 555-0100", "sms_opt_in": "true", "sms_consent_text": "SMS consent"}


@pytest.fixture
def form_service(monkeypatch):
    config = {"id": "form-1", "questions": QUESTIONS, "thank_you_message": "Thank you"}
    database = MagicMock()
    table = database.table.return_value
    table.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[config])
    table.insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": "submission-1"}])
    monkeypatch.setattr(forms, "_get_supabase", lambda: database)
    processor = AsyncMock()
    monkeypatch.setattr(forms, "_process_form_submission", processor)
    return database, processor


@pytest.mark.parametrize("changes", [
    {"first_name": "   "}, {"phone": "123"}, {"phone": {}},
    {"sms_opt_in": "false"}, {"sms_opt_in": False}, {"first_name": "a" * 5001},
])
def test_invalid_submission_is_rejected_before_save(form_service, changes):
    db, process = form_service
    response = TestClient(app).post("/api/forms/test/submit", json={"answers": {**ANSWERS, **changes}})
    assert response.status_code == 422
    db.table.return_value.insert.assert_not_called()
    process.assert_not_called()


def test_public_submission_is_durable_before_success(form_service):
    db, process = form_service
    response = TestClient(app).post("/api/forms/test/submit", json={"answers": ANSWERS})
    assert response.status_code == 200
    assert response.json()["success"] is True
    db.table.return_value.insert.assert_called_once()
    assert process.call_args.kwargs["submission_id"] == "submission-1"


@pytest.mark.parametrize("empty_response", [False, True])
def test_failed_save_never_returns_success(form_service, empty_response):
    db, process = form_service
    execute = db.table.return_value.insert.return_value.execute
    if empty_response:
        execute.return_value = SimpleNamespace(data=[])
    else:
        execute.side_effect = RuntimeError("database unavailable")
    response = TestClient(app).post("/api/forms/test/submit", json={"answers": ANSWERS})
    assert response.status_code == 503
    process.assert_not_called()


def test_public_config_does_not_require_login(form_service):
    assert TestClient(app).get("/api/forms/test").status_code == 200


@pytest.mark.parametrize("method,path", [("get", "/api/forms/test"), ("post", "/api/forms/test/submit")])
def test_database_failure_is_retryable_not_missing_form(form_service, method, path):
    db, process = form_service
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = RuntimeError("secret database detail")
    response = getattr(TestClient(app), method)(path, **({"json": {"answers": ANSWERS}} if method == "post" else {}))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert "secret" not in response.text
    db.table.return_value.insert.assert_not_called()
    process.assert_not_called()


def test_missing_form_is_404_without_fallback_lookup(form_service):
    db, _ = form_service
    execute = db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute
    execute.return_value = SimpleNamespace(data=[])
    assert TestClient(app).get("/api/forms/missing").status_code == 404
    execute.assert_called_once()


def test_uuid_config_uses_id_and_slug_uses_slug(form_service):
    db, _ = form_service
    client = TestClient(app)
    for identifier, field in [("hilltop-home-co", "slug"), ("22222222-2222-4222-8222-222222222222", "id")]:
        assert client.get(f"/api/forms/{identifier}").status_code == 200
        db.table.return_value.select.return_value.eq.assert_called_with(field, identifier)


def test_finalization_failure_is_not_acknowledged_as_success(form_service):
    from fastapi import HTTPException
    _, processor = form_service
    processor.side_effect = HTTPException(503, "Inquiry saved; follow-up delayed")
    response = TestClient(app).post("/api/forms/test/submit", json={"answers": ANSWERS})
    assert response.status_code == 503
    processor.assert_awaited_once()


def test_recovery_requires_authentication():
    response = TestClient(app).post("/api/lead-gen/submissions/22222222-2222-4222-8222-222222222222/recover")
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("created,delivery,expected_sends", [(True, True, 1), (False, True, 0), (True, False, 0)])
async def test_atomic_finalize_controls_recovery_and_notifications(monkeypatch, created, delivery, expected_sends):
    database = MagicMock()
    database.rpc.return_value.execute.return_value.data = {
        "lead_id": "22222222-2222-4222-8222-222222222222", "created": created,
    }
    monkeypatch.setattr(forms, "_get_supabase", lambda: database)
    sms = MagicMock()
    monkeypatch.setattr(forms, "_send_lead_pipeline_sms", sms)
    answers = {**ANSWERS, "property_address": "Fixture, Dallas, TX"}
    result = await forms._process_form_submission(
        {"send_confirmation_sms": False}, answers, forms._compute_scores_from_answers(answers),
        "11111111-1111-4111-8111-111111111111", None, deliver_notifications=delivery,
    )
    assert result == "22222222-2222-4222-8222-222222222222"
    args = database.rpc.call_args.args
    assert args[0] == "finalize_form_submission"
    assert args[1]["p_lead"]["owner_phone_1"] == "+12145550100"
    assert sms.call_count == expected_sends
    if expected_sends:
        assert sms.call_args.kwargs["answers"]["sms_opt_in"] is False
    database.table.assert_not_called()


@pytest.mark.asyncio
async def test_atomic_failure_preserves_receipt_and_does_not_send(monkeypatch):
    from fastapi import HTTPException
    database = MagicMock()
    database.rpc.return_value.execute.side_effect = RuntimeError("task write failed")
    monkeypatch.setattr(forms, "_get_supabase", lambda: database)
    sms = MagicMock()
    monkeypatch.setattr(forms, "_send_lead_pipeline_sms", sms)
    with pytest.raises(HTTPException) as error:
        await forms._process_form_submission({}, ANSWERS, forms._compute_scores_from_answers(ANSWERS),
            "11111111-1111-4111-8111-111111111111", None)
    assert error.value.status_code == 503
    assert "saved" in error.value.detail
    sms.assert_not_called()
    database.table.assert_not_called()


@pytest.mark.parametrize("choice,accepted", [(True,True),(False,False)])
def test_receipt_captures_server_owned_consent_evidence(form_service, choice, accepted):
    db, _ = form_service
    config = {"id":"form-1", "slug":"test", "questions":[{**q,"required":False} for q in QUESTIONS]}
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[config])
    response = TestClient(app).post("/api/forms/test/submit",json={"answers":{
        **ANSWERS, "sms_opt_in":choice, "_sms_consent":{"accepted":True,"disclosure":"forged"},
        "sms_consent_text":"SMS consent", "sms_consent_recorded_at":"yesterday"}})
    assert response.status_code == 200
    record = db.table.return_value.insert.call_args.args[0]["raw_answers"]["_sms_consent"]
    assert record["accepted"] is accepted
    assert record["disclosure"] == "SMS consent"
    assert len(record["disclosure_sha256"]) == 64
    assert record["form_id"] == "form-1"
    assert record["recorded_at"] != "yesterday"


@pytest.mark.parametrize("text", [None,"old disclosure"])
def test_changed_disclosure_rejects_opt_in_before_saving(form_service,text):
    db, processor = form_service
    response = TestClient(app).post("/api/forms/test/submit",json={"answers":{**ANSWERS,"sms_consent_text":text}})
    assert response.status_code == 409
    db.table.return_value.insert.assert_not_called()
    processor.assert_not_called()


@pytest.mark.asyncio
async def test_jays_inquiry_retains_message_and_manual_review(monkeypatch):
    database = MagicMock()
    database.rpc.return_value.execute.return_value.data = {"lead_id": "lead-1", "created": True}
    monkeypatch.setattr(forms, "_get_supabase", lambda: database)
    notify = MagicMock()
    monkeypatch.setattr(forms, "_send_lead_pipeline_sms", notify)
    answers = {"first_name": "Test", "email": "test@example.com", "inquiry_type": "buyer", "message": "criteria: Three bedrooms", "property_address": ""}
    await forms._process_form_submission({"slug": "the-jays-dallas"}, answers,
        forms._compute_scores_from_answers(answers), "receipt-1", None)
    saved = database.rpc.call_args.args[1]["p_lead"]
    assert saved["status"] == "new"
    assert saved["ai_calling_paused"] is True
    assert "Three bedrooms" in saved["internal_notes"]
    assert saved["property_address"] == "The Jays Dallas — buyer inquiry"
    assert notify.call_args.kwargs["source"] == "the-jays-dallas"


def test_jays_non_seller_checkbox_never_authorizes_sms(form_service):
    db, processor = form_service
    config = {"id": "form-1", "slug": "the-jays-dallas", "questions": [
        {"field_name": "inquiry_type", "label": "Intent", "type": "text"},
        {"field_name": "sms_opt_in", "label": "SMS consent", "type": "checkbox"},
    ]}
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[config])
    response = TestClient(app).post("/api/forms/the-jays-dallas/submit", json={"answers": {
        "inquiry_type": "buyer", "sms_opt_in": True, "sms_consent_text": "SMS consent"}})
    assert response.status_code == 200
    receipt = db.table.return_value.insert.call_args.args[0]["raw_answers"]
    assert receipt["_sms_consent"]["accepted"] is False
    assert processor.call_args.kwargs["answers"]["sms_opt_in"] == ""
