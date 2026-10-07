"""Graph credentials must not appear in request URLs or failure logs."""
import logging

import httpx
import pytest

from tools import facebook_ads_adapter as module


@pytest.mark.parametrize("method,args,result", [
    ("fetch_lead_form_data", ("123",), None),
    ("sync_campaign_insights", ("456",), None),
    ("sync_all_campaigns", (), []),
])
def test_graph_failure_keeps_credentials_out_of_urls_and_logs(monkeypatch, caplog, method, args, result):
    token = "private-test-token"
    requests = []
    real_client = httpx.Client

    def respond(request):
        requests.append(request)
        return httpx.Response(401, json={"error": {"message": token}})

    monkeypatch.setattr(module.httpx, "Client", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(respond)))
    adapter = module.FacebookAdsAdapter("secret", token, "verify", "789")
    with caplog.at_level(logging.INFO):
        assert getattr(adapter, method)(*args) == result
    assert len(requests) == 1
    request = requests[0]
    assert request.headers["Authorization"] == f"Bearer {token}"
    assert request.url.path.startswith("/v26.0/")
    assert "access_token" not in request.url.params
    assert token not in str(request.url)
    assert token not in caplog.text


def test_lead_retrieval_uses_supported_intake_fields(monkeypatch):
    real_client = httpx.Client

    def respond(request):
        # Mirrors the v26 failure observed with a real native test lead.
        fields = set(request.url.params["fields"].split(","))
        if fields - {"field_data", "created_time"}:
            return httpx.Response(400, json={"error": {"code": 100}})
        return httpx.Response(200, json={
            "created_time": "2026-10-07T19:55:53+0000",
            "field_data": [{"name": "property_address", "values": ["Test property"]}],
        })

    monkeypatch.setattr(module.httpx, "Client", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(respond)))
    lead = module.FacebookAdsAdapter("secret", "token", "verify").fetch_lead_form_data("123")
    assert lead is not None
    assert lead.fields["property_address"] == "Test property"
