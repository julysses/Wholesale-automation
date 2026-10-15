from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace
from tools import retell_form_sms as sms


def test_disabled_worker_never_claims_or_sends(monkeypatch):
    monkeypatch.delenv('RETELL_FORM_SMS_ENABLED', raising=False)
    db = MagicMock()
    post = MagicMock()
    monkeypatch.setattr(sms.requests, 'post', post)
    assert sms.drain(db)['sending_enabled'] is False
    db.rpc.assert_not_called()
    post.assert_not_called()


def test_form_queue_uses_submission_time_plus_one_minute(monkeypatch):
    monkeypatch.setenv('RETELL_FORM_SMS_ENABLED', 'true')
    monkeypatch.setattr(sms, 'sms_consent_blocker', lambda *args: None)
    db = MagicMock()
    receipt = {'id': 'submission', 'created_at': '2026-10-15T12:00:00+00:00', 'raw_answers': {'phone': '+12145551234'}}
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[receipt])
    db.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(data=[{'id': 'saved'}])
    assert sms.enqueue(db, 'lead') == 'scheduled_retell_60_seconds'
    row = db.table.return_value.upsert.call_args.args[0]
    assert datetime.fromisoformat(row['due_at']) - datetime.fromisoformat(receipt['created_at']) == timedelta(seconds=60)
    assert db.table.return_value.upsert.call_args.kwargs['ignore_duplicates'] is True


def test_no_consent_never_enqueues(monkeypatch):
    monkeypatch.setenv('RETELL_FORM_SMS_ENABLED', 'true')
    monkeypatch.setattr(sms, 'sms_consent_blocker', lambda *args: 'missing consent')
    db = MagicMock()
    receipt = {'id': 'submission', 'created_at': '2026-10-15T12:00:00+00:00', 'raw_answers': {'phone': '+12145551234'}}
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[receipt])
    assert sms.enqueue(db, 'lead') == 'consent_or_suppression_hold'
    db.table.return_value.upsert.assert_not_called()


def test_disabled_after_claim_stops_without_provider(monkeypatch):
    monkeypatch.setattr(sms, 'activation_ready', lambda: False)
    finish = MagicMock()
    post = MagicMock()
    monkeypatch.setattr(sms, 'finish', finish)
    monkeypatch.setattr(sms.requests, 'post', post)
    sms.process_claim(MagicMock(), {'id': 'job'})
    assert finish.call_args.args[2] == 'stopped'
    post.assert_not_called()


@pytest.mark.parametrize('window, hours, should_send', [
    ('valid', True, True), ('expired', True, False), ('future', True, False),
    ('missing', True, False), ('naive', True, False), ('valid', False, False),
])
def test_provider_deadline_and_timeout(monkeypatch, window, hours, should_send):
    monkeypatch.setattr(sms, 'activation_ready', lambda: True)
    monkeypatch.setattr(sms.settings, 'sms_allowed_recipients', '+12145551234')
    monkeypatch.setattr(sms, 'sms_consent_blocker', lambda *args: None)
    for key in ['RETELL_SMS_FROM_NUMBER','RETELL_SMS_AGENT_ID','RETELL_SMS_AGENT_VERSION','RETELL_SMS_API_KEY','RETELL_SMS_SENDER_NAME']:
        monkeypatch.setenv(key, 'test-only')
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{'dnc': False, 'owner_phone_1': '+12145551234', 'owner_first_name': 'Test', 'property_address': '123 Test St'}])
    finish = MagicMock()
    post = MagicMock(side_effect=TimeoutError())
    monkeypatch.setattr(sms, 'finish', finish)
    monkeypatch.setattr(sms.requests, 'post', post)
    monkeypatch.setattr(sms.SMSClient, '_in_allowed_hours', lambda self: hours)
    now = datetime.now(timezone.utc)
    job = {'id': 'j', 'lead_id': 'l', 'submission_id': 's', 'phone_number': '+12145551234',
           'due_at': (now-timedelta(seconds=5)).isoformat(),
           'expires_at': (now+timedelta(minutes=14)).isoformat()}
    if window == 'expired':
        job['expires_at'] = (now-timedelta(seconds=1)).isoformat()
    elif window == 'future':
        job['due_at'] = (now+timedelta(seconds=30)).isoformat()
    elif window == 'missing':
        job.pop('expires_at')
    elif window == 'naive':
        job['expires_at'] = now.replace(tzinfo=None).isoformat()
    sms.process_claim(db, job)
    if not should_send:
        post.assert_not_called()
        assert finish.call_args.args[2] == 'stopped'
        return
    assert post.call_count == 1
    assert finish.call_args.args[2] == 'review'
    assert post.call_args.kwargs['json']['honor_internal_dnc'] is True
    assert post.call_args.kwargs['json']['metadata']['submission_id'] == 's'
