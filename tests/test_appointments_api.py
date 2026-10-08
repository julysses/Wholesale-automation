from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from web.api import appointments_api as api

OPERATOR = "89f3b3f6-5a88-4b79-b3f4-461e0cd626a2"
LEAD = "f44034c3-2a35-5b88-a028-ba038a408e1e"
BOOKING = "1d52e7d1-885c-44c5-8c52-a7ca5e1412d7"


def body(**changes):
    return api.CreateAppointmentRequest(**{ "request_id": BOOKING, "lead_id": LEAD,
        "scheduled_at": datetime(2099, 1, 2, 15, tzinfo=timezone.utc), **changes })


def setup(monkeypatch, value):
    db = MagicMock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=value)
    monkeypatch.setattr(api, "get_supabase_client", lambda: db)
    return db, SimpleNamespace(state=SimpleNamespace(user_id=OPERATOR))


@pytest.mark.asyncio
@pytest.mark.parametrize("reused", [False, True])
async def test_booking_returns_durable_receipt_with_same_reference(monkeypatch, reused):
    db, request = setup(monkeypatch, {"appointment": {"id": BOOKING, "calendar_sync": "not_configured", "created_by": OPERATOR}, "reused": reused})
    result = await api.create_appointment(body(), request)
    assert result["reused"] is reused
    assert result["calendar_sync"] == "not_configured"
    name, params = db.rpc.call_args.args
    assert name == "book_appointment" and params["p_id"] == BOOKING and params["p_operator"] == OPERATOR
    assert params["p_at"] == "2099-01-02T15:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize("value,status", [({"conflict": True},409), ({"invalid": True},422), ({"missing":True},404), (None,503), ({"appointment": {}},503)])
async def test_unconfirmed_or_conflicting_receipt_never_reports_success(monkeypatch,value,status):
    _, request = setup(monkeypatch,value)
    with pytest.raises(HTTPException) as error: await api.create_appointment(body(),request)
    assert error.value.status_code == status


@pytest.mark.asyncio
async def test_lost_acknowledgement_preserves_retry_reference_and_hides_database_error(monkeypatch):
    db, request = setup(monkeypatch, {})
    db.rpc.return_value.execute.side_effect = RuntimeError("private database details")
    with pytest.raises(HTTPException) as error: await api.create_appointment(body(),request)
    assert error.value.status_code == 503 and "private database" not in error.value.detail
    assert db.rpc.call_args.args[1]["p_id"] == BOOKING


@pytest.mark.parametrize("changes", [{"request_id":None}, {"lead_id":"lead-test"}, {"scheduled_at":"2099-01-02T10:00:00"}, {"appointment_type":"other"}, {"notes":"x"*4001}])
def test_invalid_booking_contract(changes):
    with pytest.raises(ValidationError): body(**changes)


@pytest.mark.asyncio
async def test_status_transition_is_compare_and_set(monkeypatch):
    db, request = setup(monkeypatch,{"appointment":{"id":BOOKING,"status":"cancelled"}})
    result = await api.transition_appointment(UUID(BOOKING),api.AppointmentTransition(expected_status="scheduled",status="cancelled"),request)
    assert result["status"] == "cancelled"
    assert db.rpc.call_args.args == ("transition_appointment",{"p_id":BOOKING,"p_expected":"scheduled","p_next":"cancelled","p_operator":OPERATOR})


@pytest.mark.asyncio
async def test_missing_operator_does_not_write(monkeypatch):
    db, _ = setup(monkeypatch,{})
    with pytest.raises(HTTPException) as error: await api.create_appointment(body(),SimpleNamespace(state=SimpleNamespace()))
    assert error.value.status_code == 401
    db.rpc.assert_not_called()
