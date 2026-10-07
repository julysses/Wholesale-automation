"""Operator visibility and fail-closed intake SMS without contacting providers."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.settings import settings
from web.api import lead_forms_api as forms
from tests.test_webhook_completion_delivery import MemoryDB, MemoryTable

LEAD_ID = "22222222-2222-4222-8222-222222222222"
OWNER = "+15555550111"
SELLER = "+15555550222"


class Query(MemoryTable):
    def gte(self, *_):
        return self

    def neq(self, key, value):
        self.exclude = (key, value)
        return self

    def execute(self):
        if self.name == "leads" and self.db.safety_failure:
            raise RuntimeError("database unavailable")
        if self.name == "leads" and hasattr(self, "exclude"):
            return SimpleNamespace(data=[])
        return super().execute()


class DB(MemoryDB):
    safety_failure = False

    def __init__(self):
        self.tables = {"leads": {LEAD_ID: {"id": LEAD_ID, "dnc": False, "owner_phone_1": SELLER}}}

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, payload):
        assert name == "intake_phone_status"
        # SQL normalization and registry matching are covered by isolated PostgreSQL tests.
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={
            "suppressed": any(row.get("dnc") is True for row in self.tables.get("leads", {}).values()),
            "duplicate": False,
        }))



@pytest.fixture
def pipeline(monkeypatch):
    db, client = DB(), MagicMock()
    client.send.return_value = True
    monkeypatch.setattr(forms, "_get_supabase", lambda: db)
    monkeypatch.setattr(forms, "SMSClient", lambda: client)
    monkeypatch.setattr(settings, "owner_alert_phone_number", OWNER)
    db.email_client = MagicMock()
    db.email_client.send.return_value = True
    monkeypatch.setattr(forms, "EmailClient", lambda: db.email_client)
    monkeypatch.setattr(settings, "notification_email", "owner@example.com")
    return db, client


def run(consent=True):
    forms._send_lead_pipeline_sms(LEAD_ID, {"first_name": "Test", "sms_opt_in": consent}, SELLER, "Test property")


def receipt(db):
    return next(iter(db.tables["app_notifications"].values()))


@pytest.mark.parametrize("consent", [False, "false", "no", "", None])
def test_no_consent_still_records_owner_alert_without_seller_send(pipeline, consent):
    db, client = pipeline
    run(consent)
    assert [call.args[1] for call in client.send.call_args_list] == []
    assert receipt(db)["metadata"]["seller_sms"] == "no_consent_or_phone"


def test_failed_suppression_lookup_blocks_seller_but_not_owner(pipeline):
    db, client = pipeline
    db.safety_failure = True
    run()
    assert [call.args[1] for call in client.send.call_args_list] == []
    assert receipt(db)["metadata"]["seller_sms"] == "suppression_check_failed"


@pytest.mark.parametrize("mode", ["current", "other", "missing"])
def test_suppression_or_missing_lead_blocks_seller(pipeline, mode):
    db, client = pipeline
    if mode == "current":
        db.tables["leads"][LEAD_ID]["dnc"] = True
    elif mode == "other":
        db.tables["leads"]["other"] = {"id": "other", "owner_phone_1": SELLER, "dnc": True}
    else:
        db.tables["leads"] = {}
    run()
    assert [call.args[1] for call in client.send.call_args_list] == []


@pytest.mark.parametrize("mode,expected", [("blocked", "failed_or_blocked"), ("error", "unknown"), ("dry", "dry_run"), ("ok", "accepted")])
def test_delivery_outcomes_are_persisted_and_never_automatically_resent(pipeline, mode, expected):
    db, client = pipeline
    def send(message, number):
        assert db.tables["app_notifications"], "Record alert before any external send"
        if mode == "error":
            raise RuntimeError("provider timeout")
        if mode == "dry":
            message.a2p_provider = "twilio:dry-run"
        return mode != "blocked"
    client.send.side_effect = send
    run()
    run()
    assert client.send.call_count == 1
    assert receipt(db)["metadata"]["owner_sms"] == "not_supported_for_registered_campaign"
    assert db.email_client.send.call_count == 1
    assert receipt(db)["metadata"]["seller_sms"] == expected


def test_missing_owner_email_is_recorded(pipeline, monkeypatch):
    db, client = pipeline
    monkeypatch.setattr(settings, "notification_email", "")
    run(False)
    client.send.assert_not_called()
    assert receipt(db)["metadata"]["owner_email"] == "not_configured"


def test_missing_notification_receipt_never_sends(pipeline, monkeypatch):
    _, client = pipeline
    broken = MagicMock()
    broken.table.return_value.upsert.return_value.execute.return_value.data = []
    broken.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    monkeypatch.setattr(forms, "_get_supabase", lambda: broken)
    with pytest.raises(RuntimeError, match="persistence was not confirmed"):
        run()
    client.send.assert_not_called()


def test_interrupted_outcome_write_never_replays_provider_sends(pipeline, monkeypatch):
    db, client = pipeline
    original = Query.execute
    def execute(self):
        if self.name == "app_notifications" and self.action == "update":
            raise RuntimeError("write interrupted")
        return original(self)
    monkeypatch.setattr(Query, "execute", execute)
    with pytest.raises(RuntimeError, match="interrupted"):
        run()
    assert receipt(db)["metadata"]["seller_sms"] == "unresolved"
    run()
    assert client.send.call_count == 1




@pytest.mark.parametrize("status", [None, {}, {"suppressed": "false", "duplicate": False}])
def test_unconfirmed_phone_status_blocks_seller(pipeline, monkeypatch, status):
    db, client = pipeline
    monkeypatch.setattr(db, "rpc", lambda *_: SimpleNamespace(execute=lambda: SimpleNamespace(data=status)))
    run()
    assert [call.args[1] for call in client.send.call_args_list] == []
    assert receipt(db)["metadata"]["seller_sms"] == "suppression_check_failed"


@pytest.mark.parametrize("mode,expected", [("ok", "accepted"), ("blocked", "failed_or_blocked"), ("timeout", "unknown")])
def test_owner_email_without_seller_consent_is_durable_and_not_replayed(pipeline, mode, expected):
    db, sms = pipeline
    if mode == "timeout":
        db.email_client.send.side_effect = RuntimeError("ambiguous response")
    else:
        db.email_client.send.return_value = mode == "ok"
    run(False)
    run(False)
    sms.send.assert_not_called()
    assert db.email_client.send.call_count == 1
    kwargs = db.email_client.send.call_args.kwargs
    assert kwargs["to_email"] == "owner@example.com"
    assert kwargs["message_id"] == receipt(db)["metadata"]["owner_email_message_id"]
    assert receipt(db)["metadata"]["owner_email"] == expected


def test_sms_provider_failure_does_not_prevent_owner_email(pipeline):
    db, sms = pipeline
    sms.send.side_effect = RuntimeError("SMS unavailable")
    run()
    assert receipt(db)["metadata"]["seller_sms"] == "unknown"
    assert receipt(db)["metadata"]["owner_email"] == "accepted"
    db.email_client.send.assert_called_once()
