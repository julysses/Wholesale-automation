import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from config.settings import settings
from web.api import sendgrid_webhooks as webhook


@pytest.fixture
def setup(monkeypatch):
    private=ec.generate_private_key(ec.SECP256R1())
    public=private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setattr(settings,'sendgrid_webhook_public_key',base64.b64encode(public).decode())
    sb=MagicMock()
    sb.rpc.return_value.execute.return_value.data={'saved':True}
    monkeypatch.setattr(webhook,'get_supabase_client',lambda:sb)
    app=FastAPI()
    app.include_router(webhook.router)
    return TestClient(app),private,sb


def signed(private,body,timestamp='1791389900'):
    sig=private.sign(timestamp.encode()+body,ec.ECDSA(hashes.SHA256()))
    return {'x-twilio-email-event-webhook-timestamp':timestamp,
            'x-twilio-email-event-webhook-signature':base64.b64encode(sig).decode()}


def test_signed_event_commits_before_ack(setup):
    client,private,sb=setup
    body=json.dumps([{'email':'Fixture@Example.com','event':'delivered','timestamp':1791389900,'sg_event_id':'test-event'}]).encode()
    response=client.post('/webhooks/sendgrid/events',content=body,headers=signed(private,body))
    assert response.status_code==200
    assert sb.rpc.call_args.args[0]=='record_sendgrid_events'
    assert sb.rpc.call_args.args[1]['p_events'][0]['email']=='fixture@example.com'


@pytest.mark.parametrize('mutation',['body','signature','timestamp'])
def test_tampering_rejected_without_database(setup,mutation):
    client,private,sb=setup
    body=b'[]'
    headers=signed(private,body)
    if mutation=='body': body=b'[{}]'
    if mutation=='signature': headers['x-twilio-email-event-webhook-signature']='invalid'
    if mutation=='timestamp': headers['x-twilio-email-event-webhook-timestamp']='123'
    assert client.post('/webhooks/sendgrid/events',content=body,headers=headers).status_code==401
    sb.rpc.assert_not_called()


def test_db_failure_is_retryable(setup):
    client,private,sb=setup
    sb.rpc.return_value.execute.side_effect=RuntimeError('offline')
    assert client.post('/webhooks/sendgrid/events',content=b'[]',headers=signed(private,b'[]')).status_code==503


def test_missing_key_fails_closed(setup,monkeypatch):
    client,private,sb=setup
    monkeypatch.setattr(settings,'sendgrid_webhook_public_key','')
    assert client.post('/webhooks/sendgrid/events',content=b'[]').status_code==503
    sb.rpc.assert_not_called()


@pytest.mark.parametrize('event',[{}, {'event':'delivered','email':'a@b.co','timestamp':float('nan')},
    {'event':'delivered','email':'a@b.co','timestamp':1,'app_message_id':'bad-id'}])
def test_invalid_signed_payload_never_persists(setup,event):
    client,private,sb=setup
    body=json.dumps([event]).encode()
    assert client.post('/webhooks/sendgrid/events',content=body,headers=signed(private,body)).status_code==400
    sb.rpc.assert_not_called()


@pytest.mark.parametrize('event',['bounce','dropped','spamreport'])
def test_tracked_failure_alert_is_confirmed_before_ack(setup,event,monkeypatch):
    from uuid import uuid4
    client,private,sb=setup
    message_id=str(uuid4())
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'id':message_id}]
    alert=MagicMock()
    monkeypatch.setattr(webhook,'record_provider_alert',alert)
    body=json.dumps([{'email':'fixture@example.com','event':event,'timestamp':1791389900,
                     'sg_event_id':'failure-test','app_message_id':message_id}]).encode()
    assert client.post('/webhooks/sendgrid/events',content=body,headers=signed(private,body)).status_code==200
    alert.assert_called_once_with(sb,'sendgrid',message_id,event)
    alert.side_effect=RuntimeError('notification write unavailable')
    assert client.post('/webhooks/sendgrid/events',content=body,headers=signed(private,body)).status_code==503


def test_untracked_failure_does_not_create_misleading_operator_alert(setup,monkeypatch):
    from uuid import uuid4
    client,private,sb=setup
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
    alert=MagicMock();monkeypatch.setattr(webhook,'record_provider_alert',alert)
    body=json.dumps([{'email':'fixture@example.com','event':'bounce','timestamp':1791389900,'app_message_id':str(uuid4())}]).encode()
    assert client.post('/webhooks/sendgrid/events',content=body,headers=signed(private,body)).status_code==200
    alert.assert_not_called()
