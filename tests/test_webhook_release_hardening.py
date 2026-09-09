"""Provider-protocol and configuration regressions; no external calls or sends."""
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from config.settings import load_settings_from_rows, settings
from web.app import app
from web.api import webhooks, webhook_queue


def signed_body(body: bytes, key: str, timestamp: int) -> str:
    digest = hmac.new(key.encode(), body + str(timestamp).encode(), hashlib.sha256).hexdigest()
    return f"v={timestamp},d={digest}"


@pytest.mark.parametrize("offset", [-300_001, 300_001])
def test_retell_rejects_expired_or_future_signed_delivery(monkeypatch, offset):
    monkeypatch.setattr(webhooks.time, "time", lambda: 1_800_000_000.0)
    body = b'{"event": "call_started"}'
    signature = signed_body(body, "test-key", 1_800_000_000_000 + offset)
    assert not webhooks._verify_hmac_signature(body, signature, "test-key")


def test_retell_signs_exact_raw_bytes_and_rejects_legacy_digest(monkeypatch):
    monkeypatch.setattr(webhooks.time, "time", lambda: 1_800_000_000.0)
    body = b'{ "event": "call_started" }'
    signature = signed_body(body, "test-key", 1_800_000_000_000)
    assert webhooks._verify_hmac_signature(body, signature, "test-key")
    assert not webhooks._verify_hmac_signature(b'{"event":"call_started"}', signature, "test-key")
    assert not webhooks._verify_hmac_signature(body, signature, "wrong-key")
    bare_digest = hmac.new(b"test-key", body, hashlib.sha256).hexdigest()
    assert not webhooks._verify_hmac_signature(body, bare_digest, "test-key")


def test_retell_api_key_fallback_accepts_official_delivery(monkeypatch):
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "retell_webhook_secret", "")
    monkeypatch.setattr(settings, "retell_api_key", "test-key")
    processor = AsyncMock()
    monkeypatch.setattr(webhooks, "_process_inline", processor)
    body = json.dumps({"event": "call_started", "call": {"call_id": "call-test"}}).encode()
    response = TestClient(app).post("/webhooks/retell", content=body, headers={
        "content-type": "application/json",
        "x-retell-signature": signed_body(body, "test-key", int(time.time() * 1000)),
    })
    assert response.status_code == 200
    processor.assert_awaited_once()


def test_saved_defaults_types_and_secrets_apply_without_environment(monkeypatch):
    for name in ("AGENCY_NAME", "EMAIL_PROVIDER", "RETELL_WEBHOOK_SECRET", "AUTO_PUSH_TO_DIALER", "DISTRESS_SCORE_THRESHOLD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "agency_name", "Texas Wholesale Solutions")
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    monkeypatch.setattr(settings, "retell_webhook_secret", "")
    monkeypatch.setattr(settings, "auto_push_to_dialer", True)
    monkeypatch.setattr(settings, "distress_score_threshold", 45)
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", "")
    load_settings_from_rows([
        {"key": "agency_name", "value": "Configured Agency"},
        {"key": "email_provider", "value": "mailgun"},
        {"key": "retell_webhook_secret", "value": "saved-test-key"},
        {"key": "auto_push_to_dialer", "value": "false"},
        {"key": "distress_score_threshold", "value": "62"},
    ])
    assert settings.agency_name == "Configured Agency"
    assert settings.email_provider == "mailgun"
    assert settings.auto_push_to_dialer is False
    assert settings.distress_score_threshold == 62
    assert webhooks._webhook_setting("RETELL_WEBHOOK_SECRET") == "saved-test-key"


def test_environment_overrides_saved_value_and_bad_values_are_ignored(monkeypatch):
    monkeypatch.setenv("AGENCY_NAME", "Environment Agency")
    monkeypatch.setattr(settings, "agency_name", "Environment Agency")
    monkeypatch.delenv("DISTRESS_SCORE_THRESHOLD", raising=False)
    monkeypatch.setattr(settings, "distress_score_threshold", 45)
    monkeypatch.delenv("AUTO_PUSH_TO_DIALER", raising=False)
    monkeypatch.setattr(settings, "auto_push_to_dialer", False)
    load_settings_from_rows([
        {"key": "agency_name", "value": "Saved Agency"},
        {"key": "distress_score_threshold", "value": "invalid"},
        {"key": "auto_push_to_dialer", "value": "not-a-boolean"},
    ])
    assert settings.agency_name == "Environment Agency"
    assert settings.distress_score_threshold == 45
    assert settings.auto_push_to_dialer is False


def test_facebook_standard_dotted_verification_query(monkeypatch):
    monkeypatch.setattr(webhooks, "FACEBOOK_WEBHOOK_VERIFY_TOKEN", "test-token")
    response = TestClient(app).get("/webhooks/facebook/lead", params={
        "hub.mode": "subscribe", "hub.verify_token": "test-token", "hub.challenge": "12345",
    })
    assert response.status_code == 200
    assert response.text == "12345"


@pytest.mark.parametrize("strict", [True, False])
def test_facebook_missing_secret_never_processes_unsigned_payload(monkeypatch, strict):
    monkeypatch.setattr(webhooks, "FACEBOOK_APP_SECRET", "")
    monkeypatch.setattr(settings, "facebook_app_secret", "")
    monkeypatch.setattr(webhooks, "WEBHOOK_STRICT", strict)
    processor = AsyncMock()
    monkeypatch.setattr(webhooks, "_process_inline", processor)
    assert TestClient(app).post("/webhooks/facebook/lead", json={"entry": []}).status_code == 503
    processor.assert_not_awaited()


def test_facebook_signed_payload_accepted_and_tampering_rejected(monkeypatch):
    monkeypatch.setattr(webhooks, "FACEBOOK_APP_SECRET", "test-key")
    body = b'{"entry": []}'
    signature = "sha256=" + hmac.new(b"test-key", body, hashlib.sha256).hexdigest()
    client = TestClient(app)
    assert client.post("/webhooks/facebook/lead", content=body, headers={"X-Hub-Signature-256": signature}).status_code == 200
    assert client.post("/webhooks/facebook/lead", content=body + b" ", headers={"X-Hub-Signature-256": signature}).status_code == 403


def test_worker_requires_configured_secret_and_bounds_batch(monkeypatch):
    drain = AsyncMock(return_value={"processed": 0})
    monkeypatch.setattr(webhooks, "_drain_queue", drain)
    monkeypatch.setattr(webhooks, "CRON_SECRET", "")
    client = TestClient(app)
    assert client.get("/webhooks/_worker/drain").status_code == 503
    monkeypatch.setattr(webhooks, "CRON_SECRET", "test-worker-secret")
    assert client.get("/webhooks/_worker/drain").status_code == 401
    assert client.get("/webhooks/_worker/drain?limit=101", headers={"Authorization": "Bearer test-worker-secret"}).status_code == 422
    drain.assert_not_awaited()
    assert client.post("/webhooks/_worker/drain?limit=3", headers={"x-worker-secret": "test-worker-secret"}).status_code == 200
    drain.assert_awaited_once_with(limit=3)


@pytest.mark.asyncio
async def test_losing_queue_claim_does_not_process_job(monkeypatch):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "job-1", "source": "test", "attempts": 0, "payload": {}}
    ]
    sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    processor = AsyncMock()
    monkeypatch.setattr(webhook_queue, "_get_supabase", lambda: sb)
    monkeypatch.setattr(webhooks, "get_webhook_processors", lambda: {"test": processor})
    result = await webhook_queue.drain()
    assert result["processed"] == 0
    processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_call_qualifies_from_saved_realtime_chunks(monkeypatch):
    from tests.test_retell_transcript_ordering import _chunk
    from tests.test_webhook_completion_delivery import MemoryDB
    sb = MemoryDB()
    monkeypatch.setattr(webhooks, "_get_supabase", lambda: sb)
    await webhooks._retell_transcript_chunk("call-1", "lead-1", _chunk(1, "user", "I need to sell this month.", 1000))
    # Stop qualification after recording its input; all persistence is the in-memory fake.
    qualify = MagicMock(side_effect=RuntimeError("isolated qualification failure"))
    monkeypatch.setattr(webhooks, "extract_lead_signals", qualify)
    event = SimpleNamespace(call_id="call-1", lead_id="lead-1", disposition=SimpleNamespace(value="not_interested"))
    with pytest.raises(RuntimeError, match="isolated qualification failure"):
        await webhooks._retell_call_completed(event, {"call": {"call_id": "call-1", "metadata": {}}})
    assert qualify.call_args.args[0] == "Seller: I need to sell this month."
