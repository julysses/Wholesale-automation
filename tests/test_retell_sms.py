import io
import zipfile
import csv
import pytest
from tools.retell_sms import record_chat_event, recipient_opted_out
from tools.dialer_export import prepare_export
from tests.test_webhook_completion_delivery import MemoryDB


def event(text='Please contact me tomorrow'):
    return {'event': 'chat_analyzed', 'chat': {'chat_id': 'sms-1', 'metadata': {'lead_id': 'lead-1'},
        'to_number': '+12145551234', 'message_with_tool_calls': [{'role': 'user', 'content': text}]}}


def test_reply_duplicate_then_optout_then_late_reply():
    db = MemoryDB()
    db.tables['leads'] = {'lead-1': {'id': 'lead-1', 'dnc': False}}
    record_chat_event(db, event())
    record_chat_event(db, event())
    assert len(db.tables['tasks']) == len(db.tables['webhook_jobs']) == 1
    record_chat_event(db, event('STOP'))
    record_chat_event(db, event('STOP'))
    record_chat_event(db, event())
    assert len(db.tables['dnc_registry']) == 1
    assert db.tables['leads']['lead-1']['dnc'] is True
    assert db.tables['leads']['lead-1']['sms_sequence_active'] is False
    assert next(iter(db.tables['tasks'].values()))['status'] == 'cancelled'


def test_duplicate_preserves_human_completed_task():
    db = MemoryDB()
    db.tables['leads'] = {'lead-1': {'id': 'lead-1', 'dnc': False}}
    record_chat_event(db, event())
    next(iter(db.tables['tasks'].values()))['status'] = 'completed'
    record_chat_event(db, event())
    assert next(iter(db.tables['tasks'].values()))['status'] == 'completed'


@pytest.mark.parametrize('text', ['STOP', 'unsubscribe', 'Please remove me', "Don't text me", 'QUIT'])
def test_recipient_optouts_only(text):
    assert recipient_opted_out([{'role': 'user', 'content': text}])
    assert not recipient_opted_out([{'role': 'agent', 'content': text}])


def test_unlinked_chat_fails_closed():
    db = MemoryDB()
    db.tables['leads'] = {}
    with pytest.raises(ValueError):
        record_chat_event(db, event())
    assert not db.tables.get('tasks')


def test_sms_drafts_never_infer_clearance_or_seller_name():
    contact = {'name': 'Jane Smith', 'phone': '+12145551234', 'dnc_status': 'clear', 'expires_at': '2099-01-01T00:00:00Z'}
    lead = {'lead_id': 'l', 'dnc': False, 'address_std': '123 Main St', 'request': {'state': 'completed'}, 'contacts': [contact]}
    with zipfile.ZipFile(io.BytesIO(prepare_export([lead]))) as z:
        rows = list(csv.DictReader(io.StringIO(z.read('retell-sms-review.csv').decode('utf-8-sig'))))
        assert len(rows) == 1
        assert rows[0]['SMSReady'] == 'false'
        assert rows[0]['FirstName'] == ''
        assert '{{sender_name}}' in rows[0]['MessageDraft']
        assert '123 Main St' in rows[0]['MessageDraft']
        assert '24 hours' in rows[0]['MessageDraft'] and '10 days' in rows[0]['MessageDraft']
        assert 'Documented SMS consent required' in rows[0]['HoldReason']


def test_signed_chat_route_and_invalid_signature(monkeypatch):
    import json
    from tests.test_retell_webhook_security import client, _signature
    from web.api import webhooks
    db = MemoryDB()
    monkeypatch.setattr(webhooks, 'RETELL_WEBHOOK_SECRET', 'sms-test')
    monkeypatch.setattr(webhooks, '_get_supabase', lambda: db)
    body = json.dumps(event()).encode()
    response = client.post('/webhooks/retell', content=body,
        headers={'x-retell-signature': _signature(body, 'sms-test')})
    assert response.status_code == 200
    assert response.json()['dispatch_authorized'] is False
    before = len(db.tables['webhook_jobs'])
    response = client.post('/webhooks/retell', content=body,
        headers={'x-retell-signature': 'invalid'})
    assert response.status_code == 401
    assert len(db.tables['webhook_jobs']) == before


def test_receipt_storage_failure_returns_retryable_error(monkeypatch):
    import json
    from tests.test_retell_webhook_security import client, _signature
    from web.api import webhooks
    monkeypatch.setattr(webhooks, 'RETELL_WEBHOOK_SECRET', 'sms-test')
    monkeypatch.setattr(webhooks, '_get_supabase', lambda: None)
    body = json.dumps(event()).encode()
    response = client.post('/webhooks/retell', content=body,
        headers={'x-retell-signature': _signature(body, 'sms-test')})
    assert response.status_code == 503


@pytest.mark.parametrize('text', ['Call me at the end of the day', 'Can we stop by tomorrow?', 'I need to cancel my appointment'])
def test_ordinary_reply_is_not_keyword_optout(text):
    assert not recipient_opted_out([{'role': 'user', 'content': text}])
