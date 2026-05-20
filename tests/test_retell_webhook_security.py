"""Security regression tests for Retell webhook signature enforcement."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from web.app import app
import web.api.webhooks as webhooks


client = TestClient(app)


def _body() -> bytes:
    payload = {
        "event": "call_started",
        "call": {
            "call_id": "call_test_123",
            "metadata": {"lead_id": "lead_test_123"},
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_retell_webhook_fails_closed_without_configured_secret(monkeypatch):
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", "")

    response = client.post(
        "/webhooks/retell",
        content=_body(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 503


def test_retell_webhook_rejects_missing_signature(monkeypatch):
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", "test-secret")

    response = client.post(
        "/webhooks/retell",
        content=_body(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 401


def test_retell_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", "test-secret")

    response = client.post(
        "/webhooks/retell",
        content=_body(),
        headers={
            "content-type": "application/json",
            "x-retell-signature": "bad-signature",
        },
    )

    assert response.status_code == 401


def test_retell_webhook_accepts_valid_hmac_signature(monkeypatch):
    secret = "test-secret"
    body = _body()
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", secret)

    response = client.post(
        "/webhooks/retell",
        content=body,
        headers={
            "content-type": "application/json",
            "x-retell-signature": _signature(body, secret),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_retell_call_webhook_rejects_legacy_static_secret(monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", secret)

    response = client.post(
        "/webhooks/retell/call",
        content=_body(),
        headers={
            "content-type": "application/json",
            "x-webhook-secret": secret,
        },
    )

    assert response.status_code == 401


def test_retell_call_webhook_accepts_valid_hmac_signature(monkeypatch):
    secret = "test-secret"
    body = _body()
    monkeypatch.setattr(webhooks, "RETELL_WEBHOOK_SECRET", secret)

    response = client.post(
        "/webhooks/retell/call",
        content=body,
        headers={
            "content-type": "application/json",
            "x-retell-signature": _signature(body, secret),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
