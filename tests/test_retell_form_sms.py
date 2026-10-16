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
    receipt = {'id': 'submission', 'created_at': '2026-10-15T17:00:00+00:00', 'raw_answers': {'phone': '+12145551234'}}
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[receipt])
    db.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(data=[{'id': 'saved'}])
    assert sms.enqueue(db, 'lead') == 'scheduled_retell_60_seconds'
    row = db.table.return_value.upsert.call_args.args[0]
    assert datetime.fromisoformat(row['due_at']) - datetime.fromisoformat(receipt['created_at']) == timedelta(seconds=60)
    assert db.table.return_value.upsert.call_args.kwargs['ignore_duplicates'] is True


@pytest.mark.parametrize('submitted,due,expires', [
    ('2026-10-15T20:00:00-05:00','2026-10-16T14:00:00+00:00','2026-10-16T14:15:00+00:00'),
    ('2026-10-16T06:00:00-05:00','2026-10-16T14:00:00+00:00','2026-10-16T14:15:00+00:00'),
    ('2026-10-16T18:59:30-05:00','2026-10-17T14:00:00+00:00','2026-10-17T14:15:00+00:00'),
    ('2026-10-31T20:00:00-05:00','2026-11-01T15:00:00+00:00','2026-11-01T15:15:00+00:00'),
    ('2027-03-13T20:00:00-06:00','2027-03-14T14:00:00+00:00','2027-03-14T14:15:00+00:00'),
])
def test_after_hours_receipt_waits_for_next_central_window(monkeypatch,submitted,due,expires):
    monkeypatch.setattr(sms.settings,'tcpa_allowed_start_hour',9)
    monkeypatch.setattr(sms.settings,'tcpa_allowed_end_hour',19)
    actual_due, actual_expiry, deferred = sms.acknowledgement_window(datetime.fromisoformat(submitted))
    assert (actual_due.isoformat(),actual_expiry.isoformat(),deferred)==(due,expires,True)


def test_next_window_queue_keeps_identity_and_never_renews_previous_job(monkeypatch):
    monkeypatch.setenv('RETELL_FORM_SMS_ENABLED','true')
    monkeypatch.setattr(sms,'sms_consent_blocker',lambda *args:None)
    db=MagicMock()
    receipt={'id':'after-hours','created_at':'2026-10-15T20:00:00-05:00','raw_answers':{'phone':'+12145551234'}}
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[receipt])
    db.table.return_value.upsert.return_value.execute.return_value=SimpleNamespace(data=[{'id':'saved'}])
    assert sms.enqueue(db,'lead')=='scheduled_retell_next_contact_window'
    first=db.table.return_value.upsert.call_args
    assert first.args[0]['due_at']=='2026-10-16T14:00:00+00:00'
    assert first.args[0]['expires_at']=='2026-10-16T14:15:00+00:00'
    assert sms.enqueue(db,'lead')=='scheduled_retell_next_contact_window'
    assert db.table.return_value.upsert.call_args==first
    assert first.kwargs['ignore_duplicates'] is True
    db.table.return_value.update.assert_not_called()


def test_invalid_contact_configuration_cannot_enqueue(monkeypatch):
    monkeypatch.setattr(sms.settings,'tcpa_allowed_start_hour',19)
    monkeypatch.setattr(sms.settings,'tcpa_allowed_end_hour',9)
    with pytest.raises(ValueError): sms.acknowledgement_window(datetime.now(timezone.utc))


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
@pytest.mark.parametrize('all_consented', [False, True])
def test_provider_deadline_and_timeout(monkeypatch, window, hours, should_send, all_consented):
    monkeypatch.setenv('RETELL_SMS_ALL_CONSENTED_FORMS', str(all_consented).lower())
    monkeypatch.setattr(sms, 'activation_ready', lambda: True)
    monkeypatch.setattr(sms.settings, 'sms_allowed_recipients', '' if all_consented else '+12145551234')
    monkeypatch.setattr(sms, 'sms_consent_blocker', lambda *args: None)
    for key in ['RETELL_SMS_FROM_NUMBER','RETELL_SMS_AGENT_ID','RETELL_SMS_AGENT_VERSION','RETELL_SMS_API_KEY','RETELL_SMS_SENDER_NAME']:
        monkeypatch.setenv(key, '0' if key == 'RETELL_SMS_AGENT_VERSION' else 'test-only')
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


@pytest.mark.parametrize('status,agent,connected',[(200,'agent_193fc3ebd9844b50d54352f200',True),(200,'other',False),(401,'other',False),(302,'other',False)])
def test_connection_probe_is_read_only_and_redacted(monkeypatch,status,agent,connected):
    monkeypatch.setenv('RETELL_SMS_API_KEY','probe-secret')
    monkeypatch.setenv('RETELL_SMS_AGENT_ID','agent_193fc3ebd9844b50d54352f200')
    monkeypatch.setenv('RETELL_SMS_AGENT_VERSION','1')
    get=MagicMock(return_value=SimpleNamespace(status_code=status,json=lambda:{'agent_id':agent,'version':1,'is_published':True,'webhook_url':'https://wholesale-automation.vercel.app/webhooks/retell'}))
    post=MagicMock()
    monkeypatch.setattr(sms.requests,'get',get)
    monkeypatch.setattr(sms.requests,'post',post)
    result=sms.check_connection()
    assert result['connected'] is connected
    assert result['dispatch_authorized'] is False
    assert 'secret' not in str(result)
    assert get.call_args.kwargs['allow_redirects'] is False
    post.assert_not_called()


def test_connection_probe_requires_worker_auth(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web.api.nurture_api import router
    monkeypatch.setenv('CRON_SECRET','worker-test')
    probe=MagicMock(return_value={'connected':True,'dispatch_authorized':False})
    monkeypatch.setattr(sms,'check_connection',probe)
    app=FastAPI();app.include_router(router);client=TestClient(app)
    path='/webhooks/_worker/retell-form-sms?check_connection=true'
    assert client.get(path).status_code==401
    probe.assert_not_called()
    assert client.get(path,headers={'Authorization':'Bearer worker-test'}).json()['connected'] is True


@pytest.mark.parametrize('value,expected',[('0',0),('12',12),('latest',None),('-1',None),('',None)])
def test_agent_release_is_pinned_numeric(monkeypatch,value,expected):
    monkeypatch.setenv('RETELL_SMS_AGENT_VERSION',value)
    assert sms.configured_version()==expected


@pytest.mark.parametrize('field,value',[('version',2),('is_published',False),('webhook_url','https://wrong.example')])
def test_connection_probe_rejects_wrong_release(monkeypatch,field,value):
    monkeypatch.setenv('RETELL_SMS_API_KEY','probe-secret')
    monkeypatch.setenv('RETELL_SMS_AGENT_ID','agent_expected')
    monkeypatch.setenv('RETELL_SMS_AGENT_VERSION','1')
    data={'agent_id':'agent_expected','version':1,'is_published':True,
          'webhook_url':'https://wholesale-automation.vercel.app/webhooks/retell'}
    data[field]=value
    get=MagicMock(return_value=SimpleNamespace(status_code=200,json=lambda:data))
    monkeypatch.setattr(sms.requests,'get',get)
    result=sms.check_connection()
    assert result['connected'] is False
    assert get.call_args.kwargs['params']=={'version':1}
    assert 'https://' not in str(result)


def test_owner_approved_launch_requires_explicit_flags_and_other_gates(monkeypatch):
    monkeypatch.setattr(sms.settings,'sms_live_enabled',True)
    monkeypatch.setattr(sms.settings,'sms_allowed_recipients','')
    for key in ['RETELL_FORM_SMS_ENABLED','RETELL_SMS_LIVE_ENABLED','RETELL_SMS_LAUNCH_APPROVED','RETELL_SMS_ALL_CONSENTED_FORMS']:
        monkeypatch.setenv(key,'true')
    monkeypatch.delenv('RETELL_SMS_ACCEPTANCE_VERIFIED',raising=False)
    for key,value in {'RETELL_SMS_AGENT_ID':'agent_expected','RETELL_SMS_AGENT_VERSION':'1',
                      'RETELL_SMS_API_KEY':'test','RETELL_SMS_FROM_NUMBER':'+14698049920',
                      'RETELL_SMS_SENDER_NAME':'the automated assistant'}.items():
        monkeypatch.setenv(key,value)
    assert sms.activation_ready()
    monkeypatch.setenv('RETELL_SMS_ALL_CONSENTED_FORMS','false')
    assert not sms.activation_ready()
    monkeypatch.setenv('RETELL_SMS_ALL_CONSENTED_FORMS','true')
    monkeypatch.setattr(sms.settings,'sms_live_enabled',False)
    assert not sms.activation_ready()
