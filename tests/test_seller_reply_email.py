from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tools import seller_reply_email as mail
from tools.email_client import EmailClient
from tests.test_webhook_completion_delivery import MemoryDB
from tests.test_twilio_integration import setup, signed, SID, MESSAGE, PHONE, SENDER
from web.api import twilio_webhooks as hooks, nurture_api

EVENT, LEAD = str(uuid4()), str(uuid4())

@pytest.fixture
def delivery(monkeypatch):
    for key,value in {'email_live_enabled':True,'notification_email':'owner@example.com',
                      'email_allowed_recipients':'owner@example.com','sendgrid_api_key':'test-key',
                      'from_email':'alerts@example.com','sms_live_enabled':False}.items():
        monkeypatch.setattr(mail.settings,key,value)
    db=MemoryDB()
    db.tables['sms_events']={EVENT:{'id':EVENT,'provider':'twilio','direction':'inbound','lead_id':LEAD,
        'phone_number':PHONE,'body':'Please call ASAP','opt_out':False,'created_at':'2026-10-19T19:26:50Z'}}
    db.tables['leads'][LEAD]={'id':LEAD,'property_address':'123 Test St','owner_first_name':'Seller'}
    db.tables['app_notifications']={EVENT:{'id':EVENT,'metadata':{'provider':'twilio'},'read':False}}
    db.tables['email_messages']={}
    def claim(_self,recipient,subject):
        if _self.message_id in db.tables['email_messages']:return False
        db.tables['email_messages'][_self.message_id]={'id':_self.message_id,'recipient':recipient,'subject':subject,'status':'attempting'}
        return True
    monkeypatch.setattr(EmailClient,'_claim',claim)
    monkeypatch.setattr('tools.crm.get_supabase_client',lambda:db)
    dispatch=MagicMock(return_value=True);monkeypatch.setattr(EmailClient,'_dispatch',dispatch)
    return db,dispatch


def test_reply_emails_configured_owner_once_even_when_seller_texting_paused(delivery):
    db,send=delivery
    assert mail.notify_reply(db,EVENT)['provider_accepted']
    assert mail.notify_reply(db,EVENT)['duplicate']
    send.assert_called_once();recipient,subject,body,html=send.call_args.args
    assert recipient=='owner@example.com' and 'Seller message received' in subject
    assert 'Please call ASAP' in body and '?lead='+LEAD in body and html is None
    assert db.tables['app_notifications'][EVENT]['read'] is False
    assert db.tables['app_notifications'][EVENT]['metadata']['owner_email_message_id']==mail.email_reference(EVENT)


def test_each_distinct_seller_message_gets_its_own_alert(delivery):
    db,send=delivery;second=str(uuid4())
    db.tables['sms_events'][second]={**db.tables['sms_events'][EVENT],'id':second,'body':'Tomorrow works'}
    db.tables['app_notifications'][second]={'id':second,'metadata':{}}
    mail.notify_reply(db,EVENT);mail.notify_reply(db,second);assert send.call_count==2


@pytest.mark.parametrize('status',['attempting','unknown','accepted','delivered','bounce'])
def test_existing_or_ambiguous_attempt_never_resends(delivery,status):
    db,send=delivery;ref=mail.email_reference(EVENT)
    db.tables['email_messages'][ref]={'id':ref,'recipient':'owner@example.com','status':status}
    assert mail.notify_reply(db,EVENT)['status']==status;send.assert_not_called()


def test_provider_rejection_records_review_without_another_attempt(delivery):
    db,send=delivery;send.return_value=False
    assert mail.notify_reply(db,EVENT)['status']=='unknown'
    assert mail.notify_reply(db,EVENT)['duplicate'];send.assert_called_once()
    assert any(n.get('metadata',{}).get('integration_failure') for n in db.tables['app_notifications'].values())


def test_stop_email_is_internal_and_does_not_change_suppression(delivery):
    db,send=delivery;db.tables['sms_events'][EVENT].update(opt_out=True,body='STOP')
    db.tables['leads'][LEAD]['dnc']=True
    mail.notify_reply(db,EVENT)
    assert 'Seller opted out' in send.call_args.args[1] and 'Do not call or text' in send.call_args.args[2]
    assert db.tables['leads'][LEAD]['dnc'] is True


@pytest.mark.parametrize('field,value',[('provider','retell'),('direction','outbound')])
def test_only_saved_incoming_twilio_receipts_can_send(delivery,field,value):
    db,send=delivery;db.tables['sms_events'][EVENT][field]=value
    assert mail.notify_reply(db,EVENT)['status']=='not_found';send.assert_not_called()


def test_disabled_email_does_not_construct_provider(delivery,monkeypatch):
    db,send=delivery;monkeypatch.setattr(mail.settings,'email_live_enabled',False)
    assert mail.notify_reply(db,EVENT)['status']=='disabled';send.assert_not_called()


def test_configuration_block_is_visible_and_never_falls_back_to_seller_address(delivery,monkeypatch):
    db,send=delivery;monkeypatch.setattr(mail.settings,'email_allowed_recipients','different@example.com')
    with pytest.raises(RuntimeError,match='not claimed'):mail.notify_reply(db,EVENT)
    send.assert_not_called();assert len(db.tables['app_notifications'])==2


def test_signed_receipt_notifies_before_optional_retell_handoff_and_bad_signature_never_emails(setup,monkeypatch):
    client,db=setup;events=[]
    def email(*_):events.append('email');return {'status':'accepted'}
    def queue(*_):events.append('queue');return True
    monkeypatch.setattr(hooks,'notify_reply',email);monkeypatch.setattr(hooks,'queue_app_reply',queue)
    payload={'AccountSid':SID,'MessageSid':MESSAGE,'From':PHONE,'To':SENDER,'Body':'Please call ASAP'}
    assert signed(client,data=payload,signature='bad').status_code==401;assert events==[]
    assert signed(client,data=payload).status_code==200;assert events==['email','queue']
    db.rpc.return_value.execute.side_effect=RuntimeError('offline');events.clear()
    assert signed(client,data=payload).status_code==503;assert events==[]


def test_recovery_endpoint_requires_secret_and_only_exact_saved_event(delivery,monkeypatch):
    db,send=delivery;monkeypatch.setenv('CRON_SECRET','test-worker');monkeypatch.setattr(nurture_api,'_db',lambda:db)
    app=FastAPI();app.include_router(nurture_api.router);client=TestClient(app)
    route='/webhooks/_worker/seller-reply-email/'+EVENT
    assert client.post(route).status_code==401;send.assert_not_called()
    assert client.post(route,headers={'Authorization':'Bearer test-worker'}).json()['provider_accepted']
    assert client.post(route,headers={'Authorization':'Bearer test-worker'}).json()['duplicate'];send.assert_called_once()


def test_owner_email_failure_requests_safe_carrier_retry_without_retell_handoff(setup,monkeypatch):
    client,db=setup
    notify=MagicMock(side_effect=RuntimeError('storage unavailable'))
    handoff=MagicMock();monkeypatch.setattr(hooks,'notify_reply',notify);monkeypatch.setattr(hooks,'queue_app_reply',handoff)
    assert signed(client).status_code==503
    assert db.rpc.call_args.args[0]=='record_twilio_event';handoff.assert_not_called()


def test_notification_link_failure_blocks_email_before_dispatch(delivery,monkeypatch):
    db,send=delivery
    db.tables['app_notifications'].clear()
    with pytest.raises(RuntimeError,match='not committed'):mail.notify_reply(db,EVENT)
    send.assert_not_called()


def test_missing_owner_raises_operator_alert_without_sending(delivery,monkeypatch):
    db,send=delivery;monkeypatch.setattr(mail.settings,'notification_email','')
    assert mail.notify_reply(db,EVENT)['status']=='owner_not_configured'
    send.assert_not_called();assert len(db.tables['app_notifications'])==2
