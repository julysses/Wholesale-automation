from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator
from web.api import twilio_webhooks as hooks
from tools.sms_client import SMSClient
from schemas.outreach import OutreachMessage, OutreachChannel, OutreachStatus

SID = 'AC' + 'a'*32
MESSAGE = 'SM' + 'b'*32
BASE = 'https://wholesale-automation.vercel.app'
PHONE = '+12147010100'
SENDER = '+14698049920'

@pytest.fixture
def setup(monkeypatch):
    for key,value in {'twilio_auth_token':'unit-test-secret','twilio_account_sid':SID,
        'twilio_webhook_base_url':BASE,'twilio_from_number':SENDER,
        'twilio_messaging_service_sid':'MG'+'c'*32,'sms_live_enabled':False}.items():
        monkeypatch.setattr(hooks.settings,key,value)
    db=MagicMock()
    db.rpc.return_value.execute.return_value.data={'saved':True}
    monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',lambda _,payload:(payload.get('app_message_id'),payload.get('MessageStatus')))
    app=FastAPI();app.include_router(hooks.router)
    return TestClient(app),db

def signed(client,kind='inbound',data=None,query='',signature=None):
    payload=data or {'AccountSid':SID,'MessageSid':MESSAGE,'From':PHONE,'To':SENDER,'Body':'STOP','OptOutType':'STOP'}
    url=BASE+'/webhooks/twilio/'+kind+query
    sig=signature if signature is not None else RequestValidator('unit-test-secret').compute_signature(url,payload)
    return client.post('/webhooks/twilio/'+kind+query,data=payload,headers={'X-Twilio-Signature':sig})

def test_valid_stop_is_committed_before_ack(setup):
    client,db=setup
    assert signed(client).status_code==200
    args=db.rpc.call_args.args
    assert args[0]=='record_twilio_event'
    assert args[1]['p_payload']['OptOutType']=='STOP'
    assert args[1]['p_kind']=='inbound'
    first=args[1]['p_event']; signed(client)
    assert db.rpc.call_args.args[1]['p_event']==first

@pytest.mark.parametrize('sig',['','invalid'])
def test_invalid_signature_never_writes(setup,sig):
    client,db=setup
    assert signed(client,signature=sig).status_code==401
    db.rpc.assert_not_called()

def test_wrong_account_rejected(setup):
    client,db=setup
    payload={'AccountSid':'AC'+'d'*32,'MessageSid':MESSAGE,'From':PHONE,'To':SENDER}
    assert signed(client,data=payload).status_code==403
    db.rpc.assert_not_called()

def test_storage_failure_retries_not_false_ack(setup):
    client,db=setup
    db.rpc.return_value.execute.side_effect=RuntimeError('offline')
    assert signed(client).status_code==503

def test_missing_credentials_fail_closed(setup,monkeypatch):
    client,db=setup
    monkeypatch.setattr(hooks.settings,'twilio_auth_token','')
    assert signed(client,signature='anything').status_code==503
    db.rpc.assert_not_called()

def test_callback_query_is_signed_and_reference_recorded(setup):
    client,db=setup
    ref=str(uuid4())
    data={'AccountSid':SID,'MessageSid':MESSAGE,'From':SENDER,'To':PHONE,'MessageStatus':'delivered'}
    assert signed(client,'status',data,'?message_id='+ref).status_code==200
    assert db.rpc.call_args.args[1]['p_payload']['app_message_id']==ref
    invalid=RequestValidator('unit-test-secret').compute_signature(BASE+'/webhooks/twilio/status',data)
    assert signed(client,'status',data,'?message_id='+ref,invalid).status_code==401

def test_sending_disabled_does_not_simulate_success(setup,monkeypatch):
    message=OutreachMessage(lead_id=uuid4(),channel=OutreachChannel.SMS,body='Test',compliance_cleared=True)
    client=SMSClient()
    monkeypatch.setattr(client,'_in_allowed_hours',lambda:True)
    monkeypatch.setattr(client,'_is_weekend',lambda:False)
    assert client.send(message,PHONE) is False
    assert message.status==OutreachStatus.STOPPED
    assert message.sent_at is None

@pytest.fixture
def sending(setup,monkeypatch):
    import twilio.rest
    from tools import crm
    monkeypatch.setattr(hooks.settings,'sms_live_enabled',True)
    db=MagicMock(); q=db.table.return_value
    q.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data=[{
        'raw_answers':{'phone':PHONE,'property_address':'Test','_sms_consent':{'accepted':True,'rendered_disclosure_matches':True}}}]
    db.rpc.return_value.execute.return_value.data={'suppressed':False,'claimed':True}
    q.upsert.return_value.execute.return_value.data=[{'id':'saved'}]
    q.update.return_value.eq.return_value.execute.return_value.data=[{'id':'saved'}]
    monkeypatch.setattr(crm,'get_supabase_client',lambda:db)
    monkeypatch.setattr('tools.sms_client.reconcile_twilio_receipt',lambda *_:'accepted')
    sdk=MagicMock();sdk.messages.create.return_value.sid=MESSAGE
    monkeypatch.setattr(twilio.rest,'Client',lambda *_args, **_kwargs:sdk)
    return db,sdk,OutreachMessage(lead_id=uuid4(),channel=OutreachChannel.SMS,body='Test')

def test_send_has_durable_claim_sid_and_callback(sending):
    db,sdk,msg=sending
    assert SMSClient()._send_twilio(msg,PHONE)
    assert msg.provider_message_id==MESSAGE
    assert sdk.messages.create.call_args.kwargs['status_callback'].endswith('?message_id='+str(msg.id))
    assert sdk.messages.create.call_args.kwargs['messaging_service_sid']=='MG'+'c'*32

def test_duplicate_claim_never_sends_again(sending):
    db,sdk,msg=sending
    db.rpc.return_value.execute.return_value.data={'suppressed':False,'claimed':False,'reason':'existing_reference'}
    assert SMSClient()._send_twilio(msg,PHONE) is False
    sdk.messages.create.assert_not_called()

def test_owner_number_without_matching_consent_blocked(sending):
    db,sdk,msg=sending
    assert SMSClient()._send_twilio(msg,'+12145550199') is False
    sdk.messages.create.assert_not_called()

def test_suppressed_recipient_blocked(sending):
    db,sdk,msg=sending
    db.rpc.return_value.execute.return_value.data={'suppressed':True}
    assert SMSClient()._send_twilio(msg,PHONE) is False
    sdk.messages.create.assert_not_called()


def test_vercel_bundle_includes_twilio():
    from pathlib import Path
    assert 'twilio==9.11.2' in Path('api/requirements.txt').read_text().splitlines()

@pytest.mark.parametrize('allowlist,recipient,expected', [
    (PHONE,PHONE,True),
    (PHONE,'(214) 701-0100',True),
    ('+12145550199',PHONE,False),
    (' , ',PHONE,False),
    (PHONE+'9',PHONE,False),
])
def test_twilio_test_allowlist(sending,monkeypatch,allowlist,recipient,expected):
    db,sdk,msg=sending
    monkeypatch.setattr(hooks.settings,'sms_allowed_recipients',allowlist)
    assert SMSClient()._send_twilio(msg,recipient) is expected
    assert sdk.messages.create.call_count==int(expected)
    if not expected:
        db.table.assert_not_called()
        assert msg.status==OutreachStatus.STOPPED


@pytest.mark.parametrize('local_time,inbound,expected', [
    ('2026-10-08T08:59:59',False,False),
    ('2026-10-08T09:00:00',False,True),
    ('2026-10-08T18:59:59',False,True),
    ('2026-10-08T19:00:00',False,False),
    ('2026-10-10T12:00:00',False,False),
    ('2026-10-10T12:00:00',True,True),
    ('2026-10-10T19:00:00',True,False),
])
def test_public_send_enforces_texas_hours_and_weekend(sending,monkeypatch,local_time,inbound,expected):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from tools import sms_client
    db,sdk,msg=sending
    clock=datetime.fromisoformat(local_time).replace(tzinfo=ZoneInfo('America/Chicago'))
    monkeypatch.setattr(sms_client,'_texas_now',lambda:clock)
    monkeypatch.setattr(hooks.settings,'tcpa_allowed_start_hour',9)
    monkeypatch.setattr(hooks.settings,'tcpa_allowed_end_hour',19)
    monkeypatch.setattr(hooks.settings,'sms_weekend_blocked',True)
    monkeypatch.setattr(hooks.settings,'sms_allowed_recipients',PHONE)
    msg.compliance_cleared=True
    msg.is_inbound_reply=inbound
    assert SMSClient('twilio').send(msg,PHONE) is expected
    assert sdk.messages.create.call_count==int(expected)
    if not expected:
        db.table.assert_not_called()
        assert msg.sent_at is None


@pytest.mark.parametrize('state',['failed','undelivered','canceled'])
def test_signed_tracked_failure_requires_operator_alert(setup,monkeypatch,state):
    client,db=setup
    ref,lead_id=str(uuid4()),str(uuid4())
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'lead_id':lead_id}]
    alert=MagicMock();monkeypatch.setattr(hooks,'record_provider_alert',alert)
    data={'AccountSid':SID,'MessageSid':MESSAGE,'From':SENDER,'To':PHONE,'MessageStatus':state}
    assert signed(client,'status',data,'?message_id='+ref).status_code==200
    alert.assert_called_once_with(db,'twilio',ref,state,lead_id)
    alert.side_effect=RuntimeError('alert unavailable')
    assert signed(client,'status',data,'?message_id='+ref).status_code==503
