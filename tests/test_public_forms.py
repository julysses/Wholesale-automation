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
    table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = SimpleNamespace(data=config)
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
