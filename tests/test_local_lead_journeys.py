"""Real HTTP handlers + real disposable PostgreSQL + mocked external providers.

Run only via scripts/run_offline_tests.py --lead-journeys. No production URL,
credential, scheduler or provider request is used.
"""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from config.settings import settings
from tools import crm, retell_api_chat, retell_api_turns, retell_app_dispatch
from tools.email_client import EmailClient
from tools.facebook_ads_adapter import FacebookAdsAdapter
from tools.facebook_consent import HILLTOP_CONSENT_FORM_ID, SMS_CHECKBOX_KEY
from tests.local_journey_db import Database
from web.app import app
from web.api import lead_forms_api, twilio_webhooks

pytestmark = pytest.mark.skipif(not os.environ.get("SMS_TEST_ADMIN_URL"), reason="requires disposable journey runner")
BASE = "https://local-journey.example"
SENDER = "+14695550101"
OWNER = "00000000-0000-4000-8000-000000000777"
ACCOUNT = "AC" + "a" * 32


@pytest.fixture
def journey(monkeypatch):
    db = Database()
    db.query('SET ROLE service_role')
    monkeypatch.setattr(crm, "get_supabase_client", lambda: db)
    monkeypatch.setattr(lead_forms_api, "_get_supabase", lambda: db)
    monkeypatch.setattr(twilio_webhooks, "get_supabase_client", lambda: db)
    for key, value in {
        "twilio_auth_token": "local-signature-only", "twilio_account_sid": ACCOUNT,
        "twilio_from_number": SENDER, "twilio_webhook_base_url": BASE,
        "twilio_messaging_service_sid": "MG" + "b" * 32,
        "sms_live_enabled": False, "email_live_enabled": True,
        "sendgrid_api_key": "synthetic-only", "email_provider": "sendgrid",
        "from_email": "sender@example.test", "notification_email": "owner@example.test",
        "tcpa_allowed_start_hour": 0, "tcpa_allowed_end_hour": 24,
        "facebook_app_secret": "local-meta-signature",
        "sms_weekend_blocked": False, "facebook_access_token": "synthetic-meta-only",
    }.items():
        monkeypatch.setattr(settings, key, value)
    for key, value in {
        "FACEBOOK_APP_SECRET": "local-meta-signature",
        "RETELL_FORM_SMS_ENABLED": "true", "RETELL_SMS_TRANSPORT": "app_twilio",
        "RETELL_APP_TRANSPORT_ENABLED": "true", "RETELL_APP_ACCEPTANCE_VERIFIED": "true",
        "RETELL_SMS_LIVE_ENABLED": "true", "RETELL_SMS_AGENT_ID": "agent_local",
        "RETELL_SMS_API_KEY": "synthetic-retell-only", "RETELL_SMS_AGENT_VERSION": "2",
    }.items():
        monkeypatch.setenv(key, value)
    # Only provider boundaries are replaced. Email claim/outcome SQL stays real.
    email = Mock(return_value=True)
    monkeypatch.setattr(EmailClient, "_send_sendgrid", email)
    sms = Mock()
    sms.messages.create.side_effect = lambda **kw: SimpleNamespace(sid="SM" + uuid4().hex, status="queued")
    monkeypatch.setattr("twilio.rest.Client", lambda *_a, **_k: sms)
    chats, requests = {}, []
    def retell_post(url, **kw):
        requests.append((url, kw["json"]))
        payload = kw["json"]
        if url.endswith("/create-chat"):
            chat_id = "chat_" + uuid4().hex
            chats[chat_id] = {**payload, "chat_id": chat_id, "chat_type": "api_chat", "chat_status": "ongoing"}
            result = chats[chat_id]
        else:
            assert url.endswith("/create-chat-completion")
            assert payload["content"] == "Please call tomorrow afternoon."
            result = {"messages": [{"message_id": "msg_local", "role": "agent", "content": "We will follow up tomorrow. Reply STOP to opt out."}]}
        return SimpleNamespace(status_code=201, json=lambda: result)
    monkeypatch.setattr(retell_api_chat.requests, "post", retell_post)
    monkeypatch.setattr(retell_api_chat.requests, "get",
        lambda url, **kw: SimpleNamespace(status_code=200, json=lambda: chats[url.rsplit("/", 1)[1]]))
    yield SimpleNamespace(db=db, client=TestClient(app), sms=sms, email=email, retell=requests)
    db.connection.close()


def submit(j, monkeypatch, source, phone, consent=True, expected_status=200):
    request_id = str(uuid4())
    if source == "facebook":
        provider_data = SimpleNamespace(form_id=HILLTOP_CONSENT_FORM_ID,
            created_time=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(),
            fields={"full_name": "Local Seller", "phone_number": phone, "street_address": "123 Test St"},
            custom_disclaimer_responses=[{"checkbox_key": SMS_CHECKBOX_KEY, "is_checked": "1" if consent else "0"}])
        monkeypatch.setattr(FacebookAdsAdapter, "fetch_lead_form_data", lambda *_: provider_data)
        payload = json.dumps({"entry": [{"id": "local-page", "changes": [{"field": "leadgen",
            "value": {"leadgen_id": request_id, "form_id": HILLTOP_CONSENT_FORM_ID}}]}]}).encode()
        signature = "sha256=" + hmac.new(b"local-meta-signature", payload, hashlib.sha256).hexdigest()
        invoke = lambda: j.client.post("/webhooks/facebook/lead", content=payload,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
    else:
        questions = [
            {"field_name": "property_address", "label": "Address", "type": "text"},
            {"field_name": "inquiry_type", "label": "Intent", "type": "text"},
            {"field_name": "first_name", "label": "First name", "type": "text", "required": True},
            {"field_name": "phone", "label": "Phone", "type": "tel", "required": True},
            {"field_name": "sms_opt_in", "label": "Local SMS consent; reply STOP", "type": "checkbox", "required": False},
        ]
        j.db.query("""INSERT INTO public.lead_form_configs(id,slug,questions,name)
            VALUES(%s,%s,%s,'Local test form') ON CONFLICT(slug) DO NOTHING""", [str(uuid4()), source, questions])
        answers = {"first_name": "Local", "last_name": "Seller", "phone": phone,
                   "property_address": "123 Test St, Dallas, TX 75001", "sms_opt_in": consent,
                   "sms_consent_text": "Local SMS consent; reply STOP", "inquiry_type": "sell"}
        invoke = lambda: j.client.post(f"/api/forms/{source}/submit",
            json={"request_id": request_id, "answers": answers, "utm_source": "facebook"})
    response = invoke()
    assert response.status_code == expected_status, response.text
    if expected_status != 200:
        return response, invoke
    assert invoke().status_code == 200
    leads = j.db.query("SELECT * FROM public.leads WHERE owner_phone_1=%s", [phone])
    assert len(leads) == 1
    lead = leads[0]
    assert lead["assigned_to"] == OWNER and lead["ai_calling_paused"] is True
    tasks = j.db.query("SELECT * FROM public.tasks WHERE lead_id=%s", [lead["id"]])
    assert len(tasks) == 1 and tasks[0]["assigned_to"] == OWNER and tasks[0]["due_date"]
    notices = j.db.query("SELECT * FROM public.app_notifications WHERE lead_id=%s AND type='pipeline_step'", [lead["id"]])
    assert len(notices) == 1 and notices[0]["metadata"]["delivery_state"] == "completed"
    assert j.email.call_count == 1
    return lead, invoke


def carrier(j, phone, body=None, message=None, status=None):
    payload = {"AccountSid": ACCOUNT, "MessageSid": message or "SM"+uuid4().hex,
               "From": phone if body is not None else SENDER, "To": SENDER if body is not None else phone}
    kind, query = ("inbound", "") if body is not None else ("status", "?message_id="+status[0])
    if body is not None: payload["Body"] = body
    else: payload["MessageStatus"] = status[1]
    url = BASE+"/webhooks/twilio/"+kind+query
    signature = RequestValidator("local-signature-only").compute_signature(url, payload)
    invoke = lambda: j.client.post("/webhooks/twilio/"+kind+query, data=payload, headers={"X-Twilio-Signature": signature})
    response = invoke()
    assert response.status_code == 200, response.text
    assert invoke().status_code == 200
    return str(uuid5(NAMESPACE_URL, f"twilio:{ACCOUNT}:{kind}:{payload['MessageSid']}"))


@pytest.mark.parametrize("source", ["hilltop-home-co", "the-jays-dallas", "facebook"])
def test_submission_ack_reply_receipts_stop_and_no_replay(journey, monkeypatch, source):
    j = journey
    phone = {"hilltop-home-co": "+12145550201", "the-jays-dallas": "+12145550202", "facebook": "+12145550203"}[source]
    monkeypatch.setattr(settings, "sms_allowed_recipients", phone)
    lead, replay = submit(j, monkeypatch, source, phone)
    jobs = j.db.query("SELECT * FROM public.retell_form_sms_jobs WHERE lead_id=%s", [lead["id"]])
    assert len(jobs) == 1
    job = jobs[0]
    assert bool(job["facebook_submission_id"]) == (source == "facebook")
    assert bool(job["submission_id"]) == (source != "facebook")
    assert retell_app_dispatch.process_ack(j.db, job["id"])["status"] == "disabled"
    j.sms.messages.create.assert_not_called()
    monkeypatch.setattr(settings, "sms_live_enabled", True)  # Local mock only.
    # Honor the real database default and original 60-second acknowledgment delay.
    due = datetime.fromisoformat(job["due_at"])
    deadline = time.monotonic() + 65
    while datetime.now(timezone.utc) < due:
        assert time.monotonic() < deadline
        time.sleep(0.5)
    outcome = retell_app_dispatch.process_ack(j.db, job["id"])
    assert outcome["carrier_accepted"] is True, outcome
    retell_app_dispatch.process_ack(j.db, job["id"])
    assert j.sms.messages.create.call_count == 1
    ack = j.db.query("SELECT * FROM public.sms_events WHERE id=%s", [job["id"]])[0]
    monkeypatch.setattr(settings, "sms_live_enabled", False)
    carrier(j, phone, message=ack["raw_payload"]["provider_sid"], status=(job["id"], "delivered"))
    assert j.db.query("SELECT status FROM public.sms_events WHERE id=%s", [job["id"]])[0]["status"] == "delivered"
    turn = carrier(j, phone, body="Please call tomorrow afternoon.")
    tasks = j.db.query("SELECT * FROM public.tasks WHERE id=%s", [turn])
    assert len(tasks) == 1 and tasks[0]["assigned_to"] == OWNER and tasks[0]["due_date"]
    assert j.db.query("SELECT recipient_id FROM public.app_notifications WHERE id=%s", [turn])[0]["recipient_id"] == OWNER
    assert retell_api_turns.process_turn(j.db, turn)["status"] == "disabled"
    assert not j.retell
    monkeypatch.setattr(settings, "sms_live_enabled", True)
    assert retell_api_turns.process_turn(j.db, turn)["status"] == "generated"
    assert len(j.retell) == 2
    assert j.sms.messages.create.call_count == 1  # Generation never sends.
    reply = retell_app_dispatch.process_reply(j.db, turn)
    assert reply["carrier_accepted"] is True
    retell_app_dispatch.process_reply(j.db, turn)
    retell_api_turns.process_turn(j.db, turn)
    assert j.sms.messages.create.call_count == 2 and len(j.retell) == 2
    row = j.db.query("SELECT * FROM public.sms_events WHERE id=%s", [reply["message_id"]])[0]
    carrier(j, phone, message=row["raw_payload"]["provider_sid"], status=(row["id"], "delivered"))
    carrier(j, phone, body="STOP")
    carrier(j, phone, body="START")
    carrier(j, phone, body="Please call tomorrow afternoon.")
    assert j.db.query("SELECT dnc,status FROM public.leads WHERE id=%s", [lead["id"]])[0] == {"dnc": True, "status": "dnc"}
    assert j.db.query("SELECT status FROM public.tasks WHERE id=%s", [turn])[0]["status"] == "cancelled"
    assert replay().status_code == 200
    retell_app_dispatch.process_ack(j.db, job["id"])
    retell_app_dispatch.process_reply(j.db, turn)
    retell_api_turns.process_turn(j.db, turn)
    assert j.sms.messages.create.call_count == 2 and len(j.retell) == 2
    assert j.db.query("SELECT count(*) n FROM public.retell_api_turns WHERE session_id=%s", [job["id"]])[0]["n"] == 1
    audit = Database()
    try:
        assert not audit.query("SELECT * FROM net.test_requests")
        assert audit.query("SELECT enabled FROM private.retell_app_scheduler")[0]["enabled"] is False
        assert audit.query("SELECT enabled FROM private.retell_sms_scheduler")[0]["enabled"] is False
    finally:
        audit.connection.close()


@pytest.mark.parametrize("source", ["hilltop-home-co", "the-jays-dallas", "facebook"])
def test_no_sms_consent_still_saves_owner_handoff_without_job(journey, monkeypatch, source):
    phone = {"hilltop-home-co": "+12145550301", "the-jays-dallas": "+12145550302", "facebook": "+12145550303"}[source]
    lead, _ = submit(journey, monkeypatch, source, phone, consent=False)
    assert not journey.db.query("SELECT id FROM public.retell_form_sms_jobs WHERE lead_id=%s", [lead["id"]])
    journey.sms.messages.create.assert_not_called()
    assert not journey.retell


@pytest.mark.parametrize("source", ["hilltop-home-co", "the-jays-dallas", "facebook"])
def test_missing_owner_preserves_receipt_and_retry_finishes_once(journey, monkeypatch, source):
    j = journey
    phone = {"hilltop-home-co": "+12145550401", "the-jays-dallas": "+12145550402", "facebook": "+12145550403"}[source]
    j.db.query("UPDATE public.profiles SET status='pending' WHERE id=%s", [OWNER])
    try:
        _, replay = submit(j, monkeypatch, source, phone, expected_status=503)
        table = "facebook_lead_submissions" if source == "facebook" else "lead_form_submissions"
        assert j.db.query(f"SELECT id FROM public.{table} WHERE raw_answers->>'phone'=%s", [phone])
        j.email.assert_not_called()
        j.sms.messages.create.assert_not_called()
    finally:
        j.db.query("UPDATE public.profiles SET status='approved' WHERE id=%s", [OWNER])
    assert replay().status_code == 200
    assert replay().status_code == 200
    leads = j.db.query("SELECT id,assigned_to FROM public.leads WHERE owner_phone_1=%s", [phone])
    assert len(leads) == 1 and leads[0]["assigned_to"] == OWNER
    assert len(j.db.query("SELECT id FROM public.tasks WHERE lead_id=%s", [leads[0]["id"]])) == 1
    assert len(j.db.query("SELECT id FROM public.retell_form_sms_jobs WHERE lead_id=%s", [leads[0]["id"]])) == 1
    assert j.email.call_count == 1
    j.sms.messages.create.assert_not_called()


def test_native_committed_receipt_lost_response_recovers_without_duplicate(journey, monkeypatch):
    j = journey
    original = j.db.query
    interrupted = False
    def query(statement, params=()):
        nonlocal interrupted
        result = original(statement, params)
        if not interrupted and "INSERT INTO \"public\".\"facebook_lead_submissions\"" in (
                statement.as_string(j.db.connection) if hasattr(statement, "as_string") else statement):
            interrupted = True
            raise TimeoutError("Synthetic lost receipt response after commit")
        return result
    monkeypatch.setattr(j.db, "query", query)
    _, replay = submit(j, monkeypatch, "facebook", "+12145550501", expected_status=503)
    assert interrupted
    assert replay().status_code == 200
    assert replay().status_code == 200
    rows = original("SELECT id FROM public.leads WHERE owner_phone_1='+12145550501'")
    assert len(rows) == 1
    assert len(original("SELECT id FROM public.facebook_lead_submissions WHERE lead_id=%s", [rows[0]["id"]])) == 1
    assert len(original("SELECT id FROM public.retell_form_sms_jobs WHERE lead_id=%s", [rows[0]["id"]])) == 1
    assert j.email.call_count == 1
    j.sms.messages.create.assert_not_called()
