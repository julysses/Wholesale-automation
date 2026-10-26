"""No provider calls: verify authentication and reject malformed signed envelopes."""
import hashlib
import hmac
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from tools.facebook_ads_adapter import FacebookAdsAdapter
from web.api import webhooks
from web.app import app


def adapter(secret="secret", token="verify"):
    return FacebookAdsAdapter(secret, "", token)


@pytest.mark.parametrize("secret", ["", " ", "\t"])
def test_unconfigured_secret_rejects_even_matching_digest(secret):
    body = b'{}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert not adapter(secret).verify_webhook_signature(body, signature)


@pytest.mark.parametrize("signature", ["", "sha256=", "sha256=" + "é" * 64,
                                        "sha256=" + "a" * 65, "sha256=" + "a" * 64 + "\n"])
def test_malformed_signature_returns_false(signature):
    assert not adapter().verify_webhook_signature(b'{}', signature)


@pytest.mark.parametrize("token", ["", " ", "\t"])
def test_blank_challenge_configuration_is_never_accepted(token):
    assert adapter(token=token).verify_webhook_challenge("subscribe", token, "123") is None


def test_challenge_requires_exact_token_and_nonempty_challenge():
    assert adapter().verify_webhook_challenge("subscribe", "verify", "123") == "123"
    assert adapter().verify_webhook_challenge("subscribe", "vérify", "123") is None
    assert adapter().verify_webhook_challenge("subscribe", "verify", "") is None


@pytest.mark.parametrize("payload", [[], None, {"entry": None}, {"entry": [None]},
    {"entry": [{"changes": None}]}, {"entry": [{"changes": [None]}]},
    *[{"entry": [{"changes": [{"field": "leadgen", "value": value}]}]}
      for value in [None, [], {}, {"leadgen_id": None}, {"leadgen_id": True}, {"leadgen_id": " "}]]])
def test_signed_malformed_envelope_never_processes(monkeypatch, payload):
    import json
    monkeypatch.setattr(webhooks, "FACEBOOK_APP_SECRET", "secret")
    process = AsyncMock()
    monkeypatch.setattr(webhooks, "_process_inline", process)
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    response = TestClient(app).post("/webhooks/facebook/lead", content=body,
                                  headers={"X-Hub-Signature-256": signature})
    assert response.status_code == 400
    process.assert_not_awaited()


def test_unrelated_changes_ignored_and_lead_identity_preserved():
    entries = adapter().parse_lead_webhook({"entry": [{"id": "page", "changes": [
        {"field": "feed", "value": None},
        {"field": "leadgen", "value": {"leadgen_id": "123", "form_id": "456"}}]}]})
    assert len(entries) == 1
    assert (entries[0].leadgen_id, entries[0].page_id, entries[0].form_id) == ("123", "page", "456")
