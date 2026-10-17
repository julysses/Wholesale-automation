from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import NAMESPACE_URL, uuid5
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tools import retell_form_sms as form
from tools import retell_app_routing as routing
from tools import retell_api_turns as generation
from tools import retell_app_dispatch as dispatch
from tools.retell_sms import record_chat_event
from tests.test_webhook_completion_delivery import MemoryDB
from tests.test_twilio_integration import setup, signed, SID, MESSAGE, PHONE, SENDER
from web.api import nurture_api, twilio_webhooks as hooks

JOB = '00000000-0000-4000-8000-000000000001'
EVENT = '00000000-0000-4000-8000-000000000002'
LEAD = '00000000-0000-4000-8000-000000000003'


@pytest.fixture
def inquiry(monkeypatch):
    monkeypatch.setenv('RETELL_FORM_SMS_ENABLED', 'true')
    monkeypatch.setenv('RETELL_SMS_TRANSPORT', 'app_twilio')
    monkeypatch.setenv('RETELL_APP_TRANSPORT_ENABLED', 'true')
    monkeypatch.setenv('RETELL_APP_TEST_APPROVED', 'true')
    monkeypatch.setattr(form.settings, 'twilio_from_number', SENDER)
    monkeypatch.setattr(form.settings, 'sms_live_enabled', False)
    monkeypatch.setattr(form, 'sms_consent_blocker', lambda *_: None)
    db = MagicMock()
    receipt = {'id': EVENT, 'created_at': '2026-10-16T17:00:00Z', 'raw_answers': {'phone': PHONE}}
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [receipt]
    db.table.return_value.upsert.return_value.execute.return_value.data = [{'id': JOB}]
    return db


def test_app_inquiry_saves_fixed_owner_transport_while_sending_paused(inquiry):
    assert form.enqueue(inquiry, LEAD) == 'scheduled_app_twilio_60_seconds'
    saved = inquiry.table.return_value.upsert.call_args
    assert saved.kwargs == {'on_conflict': 'id', 'ignore_duplicates': True}
    assert saved.args[0]['delivery_transport'] == 'app_twilio'
    assert saved.args[0]['delivery_body'] == dispatch.APP_ACKNOWLEDGMENT
    assert saved.args[0]['delivery_sender'] == SENDER
    inquiry.rpc.assert_not_called()


@pytest.mark.parametrize('name,value', [
    ('RETELL_APP_TRANSPORT_ENABLED', 'false'), ('RETELL_APP_TEST_APPROVED', 'false'),
    ('RETELL_SMS_TRANSPORT', 'typo'),
])
def test_bad_app_configuration_never_falls_back_to_native(inquiry, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    monkeypatch.delenv('RETELL_APP_ACCEPTANCE_VERIFIED', raising=False)
    assert form.enqueue(inquiry, LEAD).endswith('configuration_hold')
    inquiry.table.assert_not_called()


def test_default_native_enqueue_does_not_require_migration_columns(inquiry, monkeypatch):
    monkeypatch.delenv('RETELL_SMS_TRANSPORT')
    assert form.enqueue(inquiry, LEAD) == 'scheduled_retell_60_seconds'
    row = inquiry.table.return_value.upsert.call_args.args[0]
    assert not any(k.startswith('delivery_') for k in row)


def test_retry_after_transport_switch_reports_preserved_native_job(inquiry):
    job_id = str(uuid5(NAMESPACE_URL, 'wholesaleos:retell-form-sms:' + EVENT))
    inquiry.table.return_value.upsert.return_value.execute.return_value.data = []
    inquiry.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {'id': job_id, 'delivery_transport': 'retell_native', 'status': 'review'}]
    assert form.enqueue(inquiry, LEAD) == 'existing_retell_native_job'
    inquiry.table.return_value.update.assert_not_called()


def test_native_worker_cannot_activate_when_app_transport_selected(inquiry):
    assert form.activation_ready() is False
    assert form.drain(inquiry)['sending_enabled'] is False
    inquiry.rpc.assert_not_called()


def test_native_process_cannot_overwrite_app_receipt(inquiry):
    with pytest.raises(RuntimeError):
        form.process_claim(inquiry, {'delivery_transport': 'app_twilio', 'id': JOB})
    inquiry.table.assert_not_called()


def test_native_stale_recovery_only_updates_native_jobs(monkeypatch):
    monkeypatch.setattr(form, 'activation_ready', lambda: True)
    monkeypatch.setattr(form.SMSClient, '_in_allowed_hours', lambda _: True)
    db = MagicMock(); db.rpc.return_value.execute.return_value.data = []
    form.drain(db)
    db.table.return_value.update.return_value.eq.return_value.eq.assert_called_once_with(
        'delivery_transport', 'retell_native')


@pytest.fixture
def app_reply(monkeypatch):
    monkeypatch.setenv('RETELL_APP_TRANSPORT_ENABLED', 'true')
    monkeypatch.setattr(form.settings, 'sms_live_enabled', False)
    db = MagicMock()
    job = {'id': JOB, 'delivery_transport': 'app_twilio', 'delivery_sender': SENDER,
           'status': 'accepted', 'lead_id': LEAD}
    query = db.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value
    query.execute.return_value.data = [job]
    db.rpc.return_value.execute.return_value.data = {'queued': True, 'turn_id': EVENT, 'session_id': JOB}
    data = {'From': PHONE, 'To': SENDER, 'Body': 'Tomorrow works', 'MessageSid': MESSAGE}
    return db, job, query, data


@pytest.mark.parametrize('duplicate', [True, False])
def test_actual_carrier_receipt_is_queued_even_while_paused(app_reply, duplicate):
    db, _, _, data = app_reply
    # Duplicate receipts deliberately omit lead_id. SQL resolves exact saved ID.
    assert routing.queue_reply(db, data, {'saved': True, 'duplicate': duplicate}, EVENT) is True
    db.rpc.assert_called_once_with('enqueue_retell_api_turn', {'p_job': JOB, 'p_event': EVENT})


@pytest.mark.parametrize('body', ['STOP', 'HELP', 'START', 'Do not contact me again'])
def test_controls_never_enter_generation_queue(app_reply, body):
    db, _, _, data = app_reply
    data['Body'] = body
    assert routing.queue_reply(db, data, {'saved': True}, EVENT) is False
    db.table.assert_not_called()
    db.rpc.assert_not_called()


@pytest.mark.parametrize('kind', ['review', 'processing', 'ambiguous', 'wrong_sender'])
def test_app_ownership_holds_never_fall_through_to_native(app_reply, kind):
    db, job, query, data = app_reply
    if kind == 'ambiguous':
        query.execute.return_value.data.append({'delivery_transport': 'retell_native', 'status': 'accepted'})
    elif kind == 'wrong_sender':
        job['delivery_sender'] = '+12145550101'
    else:
        job['status'] = kind
    assert routing.queue_reply(db, data, {'saved': True}, EVENT) is True
    db.rpc.assert_not_called()


def test_existing_native_chat_does_not_call_app_rpc(app_reply):
    db, job, _, data = app_reply
    job.pop('delivery_transport')
    assert routing.queue_reply(db, data, {'saved': True}, EVENT) is False
    db.rpc.assert_not_called()


def test_truncated_ambiguous_ownership_blocks_all_routes(app_reply):
    db, job, query, data = app_reply
    job['delivery_transport'] = 'retell_native'
    query.execute.return_value.data.append({'delivery_transport': 'retell_native', 'status': 'review'})
    assert routing.queue_reply(db, data, {'saved': True}, EVENT) is True
    db.rpc.assert_not_called()


@pytest.mark.parametrize('outcome', [None, {}, {'queued': True, 'turn_id': JOB, 'session_id': JOB}])
def test_unconfirmed_enqueue_cannot_acknowledge_success(app_reply, outcome):
    db, _, _, data = app_reply
    db.rpc.return_value.execute.return_value.data = outcome
    with pytest.raises(RuntimeError):
        routing.queue_reply(db, data, {'saved': True}, EVENT)


def test_signed_inbound_retry_repairs_queue_without_native_handoff(setup, monkeypatch):
    client, db = setup
    db.rpc.return_value.execute.return_value.data = {'saved': True, 'duplicate': True}
    queue = Mock(side_effect=[RuntimeError('lost response'), True])
    native = Mock()
    monkeypatch.setattr(hooks, 'queue_app_reply', queue)
    monkeypatch.setattr(hooks, 'reply_redirect', native)
    data = {'AccountSid': SID, 'MessageSid': MESSAGE, 'From': PHONE, 'To': SENDER, 'Body': 'Tomorrow works'}
    assert signed(client, data=data).status_code == 503
    response = signed(client, data=data)
    assert response.status_code == 200 and 'Redirect' not in response.text
    native.assert_not_called()
    expected = str(uuid5(NAMESPACE_URL, f'twilio:{SID}:inbound:{MESSAGE}'))
    assert [call.args[3] for call in queue.call_args_list] == [expected, expected]
    assert all(c.args[0] == 'record_twilio_event' for c in db.rpc.call_args_list)


@pytest.mark.parametrize('action,module,method,gate', [
    ('ack', dispatch, 'process_ack', 'dispatch_ready'),
    ('generate', generation, 'process_turn', 'ready'),
    ('reply', dispatch, 'process_reply', 'dispatch_ready'),
])
def test_exact_worker_requires_post_auth_uuid_and_sending_gates(monkeypatch, action, module, method, gate):
    monkeypatch.setenv('CRON_SECRET', 'worker-test')
    database = Mock(return_value=object())
    worker = Mock(return_value={'status': 'test_result'})
    monkeypatch.setattr(nurture_api, '_db', database)
    monkeypatch.setattr(module, method, worker)
    monkeypatch.setattr(module, gate, lambda: False)
    app = FastAPI(); app.include_router(nurture_api.router); client = TestClient(app)
    path = f'/webhooks/_worker/retell-app/{action}/{JOB}'
    auth = {'Authorization': 'Bearer worker-test'}
    assert client.get(path, headers=auth).status_code == 405
    assert client.post(path).status_code == 401
    assert client.post(path.replace(JOB, 'invalid'), headers=auth).status_code == 422
    assert client.post(path, headers=auth).json() == {'status': 'disabled', 'dispatch_authorized': False}
    database.assert_not_called(); worker.assert_not_called()
    monkeypatch.setattr(module, gate, lambda: True)
    assert client.post(path, headers=auth).json()['status'] == 'test_result'
    worker.assert_called_once_with(database.return_value, JOB)
    monkeypatch.delenv('CRON_SECRET')
    assert client.post(path, headers=auth).status_code == 503
    assert worker.call_count == 1


def api_event():
    return {'event': 'transcript_updated', 'chat': {
        'chat_type': 'api_chat', 'chat_id': 'chat_app', 'agent_id': 'agent_app', 'version': 2,
        'metadata': {'operation_id': JOB, 'lead_id': LEAD, 'transport': 'wholesaleos_twilio'},
        'message_with_tool_calls': [{'role': 'agent', 'message_id': 'welcome', 'content': 'Unsent welcome'},
                                    {'role': 'user', 'message_id': 'reply', 'content': 'STOP'}],
    }}


@pytest.fixture
def api_db():
    db = MemoryDB()
    db.tables['retell_api_sessions'] = {JOB: {'id': JOB, 'lead_id': LEAD, 'agent_id': 'agent_app',
        'agent_version': 2, 'chat_id': 'chat_app', 'status': 'ready'}}
    return db


def test_api_transcripts_are_audit_only_and_duplicates_do_not_make_carrier_history(api_db):
    before = deepcopy(api_db.tables)
    for _ in range(2):
        assert record_chat_event(api_db, api_event())['history_source'] == 'generation_only'
    receipts = api_db.tables.pop('webhook_jobs')
    assert len(receipts) == 1
    assert next(iter(receipts.values()))['status'] == 'done'
    assert api_db.tables == before  # No SMS/DNC/task/lead writes from generated transcripts.


def test_creation_callback_before_session_binding_is_only_archived(api_db):
    api_db.tables['retell_api_sessions'][JOB].update(chat_id=None, status='creating')
    payload = api_event(); payload['event'] = 'chat_started'
    assert record_chat_event(api_db, payload)['dispatch_authorized'] is False
    assert api_db.tables['retell_api_sessions'][JOB]['chat_id'] is None


@pytest.mark.parametrize('field,value', [('version', True), ('version', 3), ('agent_id', 'other'),
    ('chat_id', 'different'), ('chat_type', 'sms_chat')])
def test_mismatched_api_webhooks_cannot_enter_native_history(api_db, field, value):
    payload = api_event(); payload['chat'][field] = value
    with pytest.raises(ValueError):
        record_chat_event(api_db, payload)
    assert 'webhook_jobs' not in api_db.tables and 'sms_events' not in api_db.tables


def test_api_receipt_missing_session_requests_retry(api_db):
    api_db.tables['retell_api_sessions'] = {}
    with pytest.raises(RuntimeError): record_chat_event(api_db, api_event())


def test_signed_api_webhook_is_archive_only(api_db, monkeypatch):
    from tests.test_retell_webhook_security import client, _signature
    from web.api import webhooks
    monkeypatch.setattr(webhooks, 'RETELL_WEBHOOK_SECRET', 'sms-test')
    monkeypatch.setattr(webhooks, '_get_supabase', lambda: api_db)
    body = json.dumps(api_event()).encode()
    assert client.post('/webhooks/retell', content=body,
        headers={'x-retell-signature': 'invalid'}).status_code == 401
    assert 'webhook_jobs' not in api_db.tables
    response = client.post('/webhooks/retell', content=body,
        headers={'x-retell-signature': _signature(body, 'sms-test')})
    assert response.status_code == 200 and response.json()['history_source'] == 'generation_only'
    assert 'sms_events' not in api_db.tables
