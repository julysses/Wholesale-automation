import io
import zipfile
import csv
import pytest
from tools.retell_sms import record_chat_event, recipient_opted_out
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
    assert db.tables['leads']['lead-1']['ai_calling_paused'] is True
    assert db.tables['leads']['lead-1']['sms_sequence_active'] is False
    assert len(db.tables['sms_events']) == 1
    assert next(iter(db.tables['sms_events'].values()))['direction'] == 'inbound'
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


@pytest.mark.parametrize('text', ['STOP', 'unsubscribe', 'Please remove me', "Don't text me", 'QUIT', 'Wrong number', 'You have the wrong number'])
def test_recipient_optouts_only(text):
    assert recipient_opted_out([{'role': 'user', 'content': text}])
    assert not recipient_opted_out([{'role': 'agent', 'content': text}])


def test_unlinked_chat_fails_closed():
    db = MemoryDB()
    db.tables['leads'] = {}
    with pytest.raises(ValueError):
        record_chat_event(db, event())
    assert not db.tables.get('tasks')


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


def test_optout_arriving_during_task_insert_cancels_late_task():
    from tests.test_webhook_completion_delivery import MemoryTable
    class RaceTable(MemoryTable):
        def execute(self):
            result = super().execute()
            if self.name == 'tasks' and self.action == 'upsert':
                self.db.tables['leads']['lead-1']['dnc'] = True
            return result
    class RaceDB(MemoryDB):
        def table(self, name):
            return RaceTable(self, name)
    db = RaceDB()
    db.tables['leads'] = {'lead-1': {'id': 'lead-1', 'dnc': False}}
    record_chat_event(db, event())
    assert next(iter(db.tables['tasks'].values()))['status'] == 'cancelled'


def test_missing_metadata_resolves_only_exact_saved_chat():
    db = MemoryDB()
    db.tables['leads'] = {'lead-1': {'id':'lead-1','dnc':False}}
    db.tables['retell_form_sms_jobs'] = {'job-1':{'id':'job-1','lead_id':'lead-1',
        'chat_id':'sms-1','phone_number':'+12145551234'}}
    payload=event();payload['chat'].pop('metadata')
    record_chat_event(db,payload)
    assert next(iter(db.tables['tasks'].values()))['lead_id']=='lead-1'
    payload['chat']['to_number']='+12145559999'
    with pytest.raises(ValueError):
        record_chat_event(db,payload)
    payload['chat']['to_number']='+12145551234'
    payload['chat']['chat_id']='unknown-chat'
    with pytest.raises(ValueError):
        record_chat_event(db,payload)


def test_documented_chat_without_phone_uses_saved_receipt():
    db = MemoryDB()
    db.tables['leads'] = {'lead-1': {'id':'lead-1','dnc':False}}
    db.tables['retell_form_sms_jobs'] = {'job-1':{'id':'job-1','lead_id':'lead-1',
        'chat_id':'sms-1','phone_number':'+12145551234'}}
    payload=event('STOP'); payload['chat'].pop('to_number')
    record_chat_event(db,payload)
    assert next(iter(db.tables['dnc_registry'].values()))['phone_number']=='+12145551234'
    assert next(iter(db.tables['sms_events'].values()))['phone_number']=='+12145551234'
    payload['chat']['metadata']['lead_id']='different-lead'
    with pytest.raises(ValueError):
        record_chat_event(db,payload)
