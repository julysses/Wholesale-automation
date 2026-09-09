"""Release regression tests: migration failures stop startup; calendars stay truthful."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from config.settings import settings
from tools.calendar_adapter import CalendarAdapter
from web.api import appointments_api

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "run_migrations.py"


@pytest.mark.parametrize("database_url", [None, "sqlite:///local.db", "https://project.supabase.co"])
def test_migration_cli_rejects_missing_or_non_postgres_database(database_url, tmp_path):
    env = {"PYTHONDONTWRITEBYTECODE": "1", "SUPABASE_URL": "https://project.example.invalid"}
    if database_url:
        env["DATABASE_URL"] = database_url
    result = subprocess.run([sys.executable, str(RUNNER)], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr
    assert "Connecting to database" not in result.stdout
    assert not (tmp_path / "local.db").exists()


def test_migration_sql_failure_exits_nonzero_and_stops_later_files(tmp_path):
    # Patch only the database transport in a fresh process. The real CLI,
    # migration discovery, exception path and process exit behavior all run.
    code = f"""
import runpy
from unittest.mock import MagicMock
import sqlalchemy
connection = MagicMock()
connection.execute.side_effect = [None, [], RuntimeError('simulated SQL migration failure')]
engine = MagicMock()
engine.begin.return_value.__enter__.return_value = connection
engine.connect.return_value.__enter__.return_value = connection
sqlalchemy.create_engine = MagicMock(return_value=engine)
runpy.run_path({str(RUNNER)!r}, run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-c", code], env={"PYTHONDONTWRITEBYTECODE": "1", "DATABASE_URL": "postgresql://unused.invalid/test"}, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "Migration 001_initial_schema.sql failed" in result.stderr
    assert "application startup stopped" in result.stderr
    assert "Executing 002_" not in result.stdout
    assert "Successfully executed" not in result.stdout


@pytest.mark.parametrize("google,calendly,expected", [("", "", "not_configured"), ("calendar@example.test", "", "not_supported"), ("", "test-key", "not_supported")])
def test_calendar_never_reports_a_fake_provider_sync(monkeypatch, google, calendly, expected):
    monkeypatch.setattr(settings, "google_calendar_id", google)
    monkeypatch.setattr(settings, "calendly_api_key", calendly)
    calendar = CalendarAdapter()
    assert calendar.sync_deal_milestones("deal-test", "123 Main St", {"Closing": datetime.now(timezone.utc)}) is False
    assert calendar.status == expected


def appointment_db():
    appointment = {"id": "appointment-test", "lead_id": "lead-test", "status": "scheduled"}
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(data=[appointment])
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = SimpleNamespace(data={"property_address": "123 Main St"})
    return db, appointment


@pytest.mark.asyncio
@pytest.mark.parametrize("configured,expected", [(False, "not_configured"), (True, "not_supported")])
async def test_saved_appointment_reports_calendar_limitation(monkeypatch, configured, expected):
    db, stored = appointment_db()
    monkeypatch.setattr(appointments_api, "get_supabase_client", lambda: db)
    monkeypatch.setattr(settings, "google_calendar_id", "calendar@example.test" if configured else "")
    monkeypatch.setattr(settings, "calendly_api_key", "")
    result = await appointments_api.create_appointment(appointments_api.CreateAppointmentRequest(lead_id="lead-test", scheduled_at=datetime.now(timezone.utc)))
    assert result["id"] == stored["id"]
    assert result["status"] == "scheduled"
    assert result["calendar_sync"] == expected
    assert "calendar_sync" not in stored
    db.table.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_calendar_failure_does_not_lose_saved_appointment(monkeypatch):
    db, stored = appointment_db()
    monkeypatch.setattr(appointments_api, "get_supabase_client", lambda: db)
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = RuntimeError("simulated lookup error")
    result = await appointments_api.create_appointment(appointments_api.CreateAppointmentRequest(lead_id="lead-test", scheduled_at=datetime.now(timezone.utc)))
    assert result["id"] == stored["id"]
    assert result["calendar_sync"] == "failed"


@pytest.mark.asyncio
async def test_failed_appointment_insert_never_attempts_calendar(monkeypatch):
    db, _ = appointment_db()
    db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("simulated save error")
    monkeypatch.setattr(appointments_api, "get_supabase_client", lambda: db)
    calendar = MagicMock()
    monkeypatch.setattr(appointments_api, "CalendarAdapter", calendar)
    with pytest.raises(HTTPException):
        await appointments_api.create_appointment(appointments_api.CreateAppointmentRequest(lead_id="lead-test", scheduled_at=datetime.now(timezone.utc)))
    calendar.assert_not_called()
