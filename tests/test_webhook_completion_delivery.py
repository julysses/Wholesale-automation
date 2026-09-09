"""At-most-once completion attempts and retryable delivery failure contracts."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from agents.qualification_agent import QualificationResult
from web.api import webhooks


class MemoryTable:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.action, self.payload, self.filters, self.one = "select", {}, {}, False
        self.ignore = False

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def single(self):
        self.one = True
        return self

    def limit(self, _):
        return self

    def upsert(self, payload, *, ignore_duplicates=False, **_):
        self.action, self.payload, self.ignore = "upsert", payload, ignore_duplicates
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.name, {})
        if self.action in {"upsert", "insert"}:
            key = self.payload.get("id") or (
                self.payload.get("call_id") if self.name in {"ai_call_records", "call_transcripts"} else None
            ) or f"{self.name}-{len(rows) + 1}"
            if self.ignore and key in rows:
                return SimpleNamespace(data=[])
            rows[key] = {**rows.get(key, {}), "id": key, **self.payload}
            return SimpleNamespace(data=[rows[key].copy()])
        selected = [row for row in rows.values() if all(row.get(k) == v for k, v in self.filters.items())]
        if self.action == "update":
            for row in selected:
                row.update(self.payload)
        return SimpleNamespace(data=(selected[0].copy() if selected else None) if self.one else [r.copy() for r in selected])


class MemoryDB:
    def __init__(self):
        self.tables = {"leads": {"lead-1": {"id": "lead-1", "contact_attempts": 0}}}

    def table(self, name):
        return MemoryTable(self, name)


def final_event(kind="call_ended", transcript="Seller: I need to sell this week."):
    call = {"call_id": "call-1", "metadata": {"lead_id": "lead-1"}, "to_number": "+15555550123"}
    if transcript is not None:
        call["transcript"] = transcript
    if kind == "call_analyzed":
        call["call_analysis"] = {"custom_analysis_data": {"disposition": "hot_lead"}}
    return {"event": kind, "call": call}


@pytest.fixture
def completion(monkeypatch):
    db = MemoryDB()
    qualify = MagicMock(return_value=QualificationResult(classification="HOT", qualification_score=90))
    hot = AsyncMock()
    monkeypatch.setattr(webhooks, "_get_supabase", lambda: db)
    monkeypatch.setattr(webhooks, "extract_lead_signals", qualify)
    monkeypatch.setattr(webhooks, "_trigger_hot_lead_automation", hot)
    return db, qualify, hot


@pytest.mark.asyncio
async def test_ended_analyzed_and_duplicate_deliveries_attempt_completion_once(completion):
    db, qualify, hot = completion
    await webhooks._process_inline("retell", final_event())
    await webhooks._process_inline("retell", final_event("call_analyzed"))
    await webhooks._process_inline("retell", final_event("call_analyzed"))
    assert db.tables["leads"]["lead-1"]["contact_attempts"] == 1
    assert db.tables["leads"]["lead-1"]["status"] == "hot"
    assert len(db.tables["qualification_results"]) == 1
    qualify.assert_called_once()
    hot.assert_awaited_once()
    receipts = db.tables["webhook_jobs"]
    assert receipts[webhooks._retell_receipt_id("call-1", "completion")]["status"] == "done"
    assert receipts[webhooks._retell_receipt_id("call-1", "event:call_ended")]["payload"]["event"] == "call_ended"
    assert receipts[webhooks._retell_receipt_id("call-1", "event:call_analyzed")]["payload"]["call"]["call_analysis"]


@pytest.mark.asyncio
async def test_incomplete_ended_event_defers_claim_until_analyzed_transcript(completion):
    db, qualify, hot = completion
    await webhooks._process_inline("retell", final_event(transcript=None))
    qualify.assert_not_called()
    assert webhooks._retell_receipt_id("call-1", "completion") not in db.tables["webhook_jobs"]
    await webhooks._process_inline("retell", final_event("call_analyzed"))
    qualify.assert_called_once()
    hot.assert_awaited_once()


@pytest.mark.asyncio
async def test_retell_second_route_uses_same_completion_claim(completion):
    _, qualify, hot = completion
    await webhooks._process_inline("retell", final_event())
    await webhooks._process_inline("retell_call", final_event("call_analyzed"))
    qualify.assert_called_once()
    hot.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_completion_is_parked_and_retry_does_not_repeat_attempt(completion):
    db, qualify, hot = completion
    qualify.side_effect = RuntimeError("qualification unavailable")
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await webhooks._process_inline("retell", final_event())
        assert error.value.status_code == 503
        assert error.value.headers["Retry-After"] == "30"
    qualify.assert_called_once()
    hot.assert_not_awaited()
    assert db.tables["webhook_jobs"][webhooks._retell_receipt_id("call-1", "completion")]["status"] == "failed"


@pytest.mark.asyncio
async def test_concurrent_completion_cannot_take_existing_claim(completion, monkeypatch):
    _, _, _ = completion
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def hold_claim(*_):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(webhooks, "_run_retell_completion", hold_claim)
    first = asyncio.create_task(webhooks._process_inline("retell", final_event()))
    await asyncio.wait_for(started.wait(), 1)
    with pytest.raises(HTTPException) as error:
        await webhooks._process_inline("retell", final_event("call_analyzed"))
    assert error.value.status_code == 503
    release.set()
    await first
    await webhooks._process_inline("retell", final_event("call_analyzed"))
    assert calls == 1


def test_empty_claim_response_without_receipt_is_not_success():
    sb = MagicMock()
    sb.table.return_value.upsert.return_value.execute.return_value.data = []
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with pytest.raises(RuntimeError, match="operator recovery"):
        webhooks._claim_retell_completion(sb, "call-1", final_event())


@pytest.mark.asyncio
async def test_missing_database_and_unknown_processor_return_retryable_failure(monkeypatch):
    monkeypatch.setattr(webhooks, "_get_supabase", lambda: None)
    for source in ["retell", "unknown"]:
        with pytest.raises(HTTPException) as error:
            await webhooks._process_inline(source, final_event())
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_hot_automation_failure_is_awaited_and_parks_receipt(completion):
    db, _, hot = completion
    hot.side_effect = RuntimeError("notification unavailable")
    with pytest.raises(HTTPException):
        await webhooks._process_inline("retell", final_event())
    assert db.tables["webhook_jobs"][webhooks._retell_receipt_id("call-1", "completion")]["status"] == "failed"


@pytest.mark.asyncio
async def test_facebook_fetch_failure_escapes():
    adapter = MagicMock()
    adapter.fetch_lead_form_data.return_value = None
    with pytest.raises(RuntimeError, match="could not be fetched"):
        await webhooks._process_facebook_lead(SimpleNamespace(leadgen_id="fb-1"), adapter)


@pytest.mark.asyncio
async def test_facebook_retry_creates_one_lead_without_invalid_qualification_call(monkeypatch):
    from tools import crm
    db = MemoryDB()
    monkeypatch.setattr(crm, "get_supabase_client", lambda: db)
    adapter = MagicMock()
    adapter.fetch_lead_form_data.return_value = SimpleNamespace(fields={"full_name": "Test Seller"})
    entry = SimpleNamespace(leadgen_id="fb-1", campaign_id="")
    await webhooks._process_facebook_lead(entry, adapter)
    await webhooks._process_facebook_lead(entry, adapter)
    imported = [r for r in db.tables["leads"].values() if r.get("internal_notes") == "FB leadgen_id=fb-1"]
    assert len(imported) == 1


@pytest.mark.asyncio
async def test_hot_partial_failures_park_receipt_but_preserve_other_successes(monkeypatch):
    from config.settings import settings

    class TaskFailureDB(MemoryDB):
        def table(self, name):
            table = super().table(name)
            if name == "tasks":
                table.execute = MagicMock(side_effect=RuntimeError("task write unavailable"))
            return table

    db = TaskFailureDB()
    db.tables["leads"]["lead-1"]["owner_phone_1"] = "+15555550123"
    monkeypatch.setattr(webhooks, "_get_supabase", lambda: db)
    monkeypatch.setattr(webhooks, "extract_lead_signals", lambda *_, **__: QualificationResult(classification="HOT", qualification_score=90))
    monkeypatch.setattr(webhooks, "_launch_control_configured", lambda: True)
    sms = SimpleNamespace(add_contact_to_campaign=AsyncMock(return_value=False))
    monkeypatch.setattr(webhooks, "LaunchControlAdapter", lambda: sms)
    email = SimpleNamespace(_configured=True, send=MagicMock(return_value=False))
    monkeypatch.setattr(webhooks, "EmailClient", lambda: email)
    monkeypatch.setattr(settings, "notification_email", "test@example.invalid")

    with pytest.raises(HTTPException) as error:
        await webhooks._process_inline("retell", final_event())
    assert error.value.status_code == 503
    receipt = db.tables["webhook_jobs"][webhooks._retell_receipt_id("call-1", "completion")]
    assert receipt["status"] == "failed"
    assert all(label in receipt["last_error"] for label in ["task creation", "SMS enrollment", "email alert"])
    assert db.tables["leads"]["lead-1"]["ai_calling_paused"] is True
    assert len(db.tables["app_notifications"]) == 1
    sms.add_contact_to_campaign.assert_awaited_once()
    email.send.assert_called_once()
    with pytest.raises(HTTPException):
        await webhooks._process_inline("retell", final_event("call_analyzed"))
    sms.add_contact_to_campaign.assert_awaited_once()
    email.send.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_action", ["tasks", "pause", "app_notifications"])
async def test_hot_required_db_actions_reject_empty_success_rows(monkeypatch, failed_action):
    from config.settings import settings

    class EmptyActionDB(MemoryDB):
        def table(self, name):
            table = super().table(name)
            original = table.execute

            def execute():
                if name == failed_action or (failed_action == "pause" and name == "leads" and table.payload == {"ai_calling_paused": True}):
                    return SimpleNamespace(data=[])
                return original()

            table.execute = execute
            return table

    db = EmptyActionDB()
    monkeypatch.setattr(webhooks, "_launch_control_configured", lambda: False)
    monkeypatch.setattr(settings, "notification_email", "")
    with pytest.raises(RuntimeError, match="HOT automation failed"):
        await webhooks._trigger_hot_lead_automation(
            db, "lead-1", "call-1", "Test address", "Test Owner",
            QualificationResult(classification="HOT"), None, None,
        )


@pytest.mark.asyncio
async def test_hot_optional_unconfigured_providers_are_not_required(monkeypatch):
    from config.settings import settings
    db = MemoryDB()
    monkeypatch.setattr(webhooks, "_get_supabase", lambda: db)
    monkeypatch.setattr(webhooks, "extract_lead_signals", lambda *_, **__: QualificationResult(classification="HOT", qualification_score=90))
    monkeypatch.setattr(webhooks, "_launch_control_configured", lambda: False)
    sms_constructor = MagicMock(side_effect=AssertionError("unconfigured SMS must not run"))
    monkeypatch.setattr(webhooks, "LaunchControlAdapter", sms_constructor)
    email = SimpleNamespace(_configured=False, send=MagicMock(side_effect=AssertionError("unconfigured email must not run")))
    monkeypatch.setattr(webhooks, "EmailClient", lambda: email)
    monkeypatch.setattr(settings, "notification_email", "test@example.invalid")
    await webhooks._process_inline("retell", final_event())
    assert db.tables["webhook_jobs"][webhooks._retell_receipt_id("call-1", "completion")]["status"] == "done"
    sms_constructor.assert_not_called()
    email.send.assert_not_called()


@pytest.mark.asyncio
async def test_warm_configured_false_delivery_parks_completion(completion, monkeypatch):
    db, qualify, hot = completion
    qualify.return_value = QualificationResult(classification="WARM", qualification_score=60)
    monkeypatch.setattr(webhooks, "_launch_control_configured", lambda: True)
    sms = SimpleNamespace(add_contact_to_campaign=AsyncMock(return_value=False))
    monkeypatch.setattr(webhooks, "LaunchControlAdapter", lambda: sms)
    for _ in range(2):
        with pytest.raises(HTTPException):
            await webhooks._process_inline("retell", final_event())
    assert db.tables["webhook_jobs"][webhooks._retell_receipt_id("call-1", "completion")]["status"] == "failed"
    sms.add_contact_to_campaign.assert_awaited_once()
    hot.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyzed_enriches_provider_details_and_status_without_rerunning_actions(completion):
    db, qualify, hot = completion
    ended = final_event()
    analyzed = final_event("call_analyzed")
    analyzed["call"].update({"duration_ms": 85_000, "recording_url": "https://example.invalid/recording"})
    analyzed["call"]["call_analysis"] = {
        "call_summary": "Appointment confirmed by provider",
        "custom_analysis_data": {"disposition": "appointment_set", "asking_price": "180000", "timeline_to_sell": "30_days"},
    }
    await webhooks._process_inline("retell", ended)
    await webhooks._process_inline("retell", analyzed)
    await webhooks._process_inline("retell", ended)  # Late older event must not erase analysis.
    record = db.tables["ai_call_records"]["call-1"]
    assert record["disposition"] == "appointment_set"
    assert record["duration_sec"] == 85
    assert record["recording_url"] == "https://example.invalid/recording"
    assert record["asking_price"] == 180000
    assert record["call_notes"] == "Appointment confirmed by provider"
    assert record["raw_payload"]["event"] == "call_analyzed"
    assert db.tables["leads"]["lead-1"]["status"] == "appointment_set"
    assert db.tables["leads"]["lead-1"]["contact_attempts"] == 1
    qualify.assert_called_once()
    hot.assert_awaited_once()
    db.tables["leads"]["lead-1"]["status"] = "under_contract"
    await webhooks._process_inline("retell", analyzed)
    assert db.tables["leads"]["lead-1"]["status"] == "under_contract"


@pytest.mark.asyncio
async def test_analyzed_first_preserves_explicit_appointment_disposition(completion):
    db, _, _ = completion
    analyzed = final_event("call_analyzed")
    analyzed["call"]["call_analysis"]["custom_analysis_data"]["disposition"] = "appointment_set"
    await webhooks._process_inline("retell", analyzed)
    assert db.tables["leads"]["lead-1"]["status"] == "appointment_set"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,status", [
    ("dial_no_answer", "no_answer"), ("dial_busy", "no_answer"),
    ("dial_failed", "no_answer"), ("voicemail_reached", "voicemail"),
])
async def test_no_conversation_terminal_outcomes_count_once_without_qualification(completion, reason, status):
    db, qualify, hot = completion
    ended = final_event(transcript=None)
    ended["call"]["disconnection_reason"] = reason
    analyzed = {"event": "call_analyzed", "call": dict(ended["call"])}
    for event in [ended, analyzed, analyzed]:
        await webhooks._process_inline("retell", event)
    assert db.tables["leads"]["lead-1"]["status"] == status
    assert db.tables["leads"]["lead-1"]["contact_attempts"] == 1
    assert db.tables["ai_call_records"]["call-1"]["disposition"] == status
    qualify.assert_not_called()
    hot.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_analyzed_without_transcript_remains_retryable(completion):
    db, qualify, hot = completion
    analyzed = final_event("call_analyzed", transcript=None)
    with pytest.raises(HTTPException) as error:
        await webhooks._process_inline("retell", analyzed)
    assert error.value.status_code == 503
    assert webhooks._retell_receipt_id("call-1", "completion") not in db.tables["webhook_jobs"]
    qualify.assert_not_called()
    hot.assert_not_awaited()
