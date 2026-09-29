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
ANSWERS = {"first_name": "Test", "phone": "(214) 555-0100", "sms_opt_in": "true"}


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
