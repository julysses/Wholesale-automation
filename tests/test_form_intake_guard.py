"""Spam screening keeps suspicious inquiries as reviewable receipts only."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tools import form_intake_guard as guard
from web.app import app
from web.api import lead_forms_api as forms

QUESTIONS = [
    {"field_name": "first_name", "label": "First name", "type": "text", "required": True},
    {"field_name": "email", "label": "Email", "type": "email", "required": False},
    {"field_name": "phone", "label": "Phone", "type": "tel", "required": True},
]
ANSWERS = {"first_name": "Dana", "email": "dana@example.com", "phone": "(214) 555-0100"}
REQUEST_ID = "6f1f2c0e-7f4b-4a55-9d3e-0b8f6a1d2c33"


def _db(prior_rows=None, flood_count=0):
    database = MagicMock()
    table = database.table.return_value
    table.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = \
        SimpleNamespace(data=[{"id": "form-1", "slug": "seller", "questions": QUESTIONS}])
    velocity = table.select.return_value.eq.return_value.gte.return_value
    velocity.limit.return_value.execute.return_value = SimpleNamespace(data=prior_rows or [])
    velocity.neq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=prior_rows or [])
    velocity.limit.return_value.execute.return_value.count = flood_count
    table.insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": "submission-1"}])
    return database


@pytest.fixture
def service(monkeypatch):
    holder = {}

    def install(**kwargs):
        database = _db(**kwargs)
        holder["db"] = database
        monkeypatch.setattr(forms, "_get_supabase", lambda: database)
        return database

    processor = AsyncMock(return_value="lead-1")
    monkeypatch.setattr(forms, "_process_form_submission", processor)
    monkeypatch.delenv("FORM_INTAKE_KEY_REQUIRED_SLUGS", raising=False)
    monkeypatch.delenv("FORM_INTAKE_SHARED_SECRET", raising=False)
    return install, processor


def _inserted(db):
    return db.table.return_value.insert.call_args.args[0]


def test_clean_inquiry_is_processed(service):
    install, process = service
    db = install()
    response = TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS})
    assert response.status_code == 200
    assert _inserted(db)["processing_status"] == "pending"
    assert "_spam_review" not in _inserted(db)["raw_answers"]
    process.assert_awaited_once()


def test_honeypot_is_quarantined_with_a_normal_response(service):
    install, process = service
    db = install()
    response = TestClient(app).post("/api/forms/seller/submit",
                                    json={"answers": {**ANSWERS, "company_website": "http://spam.test"}})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["processing_status"] == "received"
    saved = _inserted(db)
    assert saved["processing_status"] == "quarantined"
    assert saved["raw_answers"]["_spam_review"]["reasons"] == ["honeypot"]
    process.assert_not_called()


def test_email_reused_under_another_name_is_quarantined(service):
    install, process = service
    db = install(prior_rows=[{"id": "x", "raw_answers": {"first_name": "Qwrtz", "phone": "9725550199"}}])
    TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS})
    assert _inserted(db)["raw_answers"]["_spam_review"]["reasons"] == ["email_reused_with_different_identity"]
    process.assert_not_called()


def test_same_person_resubmitting_once_is_not_quarantined(service):
    install, process = service
    db = install(prior_rows=[{"id": "x", "raw_answers": {"first_name": " dana ", "phone": "+1 214-555-0100"}}])
    TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS})
    assert _inserted(db)["processing_status"] == "pending"
    process.assert_awaited_once()


def test_form_flood_is_quarantined(service):
    install, process = service
    db = install(flood_count=guard.FORM_FLOOD_LIMIT)
    TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS})
    assert "form_flood" in _inserted(db)["raw_answers"]["_spam_review"]["reasons"]
    process.assert_not_called()


def test_lookup_failure_fails_open(service):
    install, process = service
    db = install()
    db.table.return_value.select.return_value.eq.return_value.gte.side_effect = RuntimeError("db down")
    response = TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS})
    assert response.status_code == 200
    process.assert_awaited_once()


@pytest.mark.parametrize("header,expected", [(None, "unverified_source"), ("wrong", "unverified_source"), ("s3cret", None)])
def test_website_only_form_requires_source_key(service, monkeypatch, header, expected):
    install, process = service
    monkeypatch.setenv("FORM_INTAKE_KEY_REQUIRED_SLUGS", "seller")
    monkeypatch.setenv("FORM_INTAKE_SHARED_SECRET", "s3cret")
    db = install()
    headers = {guard.INTAKE_KEY_HEADER: header} if header else {}
    TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS}, headers=headers)
    if expected:
        assert _inserted(db)["raw_answers"]["_spam_review"]["reasons"] == [expected]
        process.assert_not_called()
    else:
        assert _inserted(db)["processing_status"] == "pending"
        process.assert_awaited_once()


def test_missing_secret_quarantines_instead_of_dropping(service, monkeypatch):
    install, process = service
    monkeypatch.setenv("FORM_INTAKE_KEY_REQUIRED_SLUGS", "seller")
    db = install()
    TestClient(app).post("/api/forms/seller/submit", json={"answers": ANSWERS})
    assert _inserted(db)["raw_answers"]["_spam_review"]["reasons"] == ["source_key_unconfigured"]
    process.assert_not_called()


def test_referenced_inquiry_is_marked_quarantined_after_reservation(service):
    install, process = service
    db = install()
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"status": "created", "submission_id": REQUEST_ID, "processing_status": "pending"})
    response = TestClient(app).post("/api/forms/seller/submit", json={
        "request_id": REQUEST_ID, "answers": {**ANSWERS, "_hp": "x"}})
    assert response.status_code == 200
    db.table.return_value.update.assert_called_once_with({"processing_status": "quarantined"})
    process.assert_not_called()


def test_replay_of_quarantined_inquiry_stays_quarantined(service):
    install, process = service
    db = install()
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"status": "replayed", "submission_id": REQUEST_ID, "processing_status": "quarantined"})
    response = TestClient(app).post("/api/forms/seller/submit", json={"request_id": REQUEST_ID, "answers": ANSWERS})
    assert response.json()["processing_status"] == "received"
    db.table.return_value.update.assert_not_called()
    process.assert_not_called()
