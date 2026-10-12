"""Route-level launch guards; no live providers or database are contacted."""
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock
import pytest
from fastapi.testclient import TestClient
from web.app import app
from web import auth, api
from web.api import list_pipeline_api as lists

@pytest.fixture
def client(monkeypatch):
    db = MagicMock()
    db.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='00000000-0000-4000-8000-000000000001'))
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{'status':'approved','role':'user'}])
    monkeypatch.setattr(auth,'get_supabase_client',lambda: db)
    return TestClient(app)

@pytest.mark.parametrize('method,path',[
    ('get','/api/operations/lists'),('post','/api/operations/lists/scan'),
    ('post','/api/operations/lists/resolve'),('patch','/api/operations/lists/sources/tx-dallas-probate'),
])
def test_list_routes_require_admin(client,monkeypatch,method,path):
    rpc=AsyncMock(); monkeypatch.setattr(lists,'rpc',rpc)
    assert getattr(client,method)(path).status_code==401
    assert getattr(client,method)(path,headers={'Authorization':'Bearer test'}).status_code==403
    rpc.assert_not_called()

def test_worker_secret_fails_closed_then_runs_once(client,monkeypatch):
    rpc=AsyncMock(return_value={'missing_sources':0});monkeypatch.setattr(lists,'rpc',rpc)
    path='/webhooks/_worker/daily-lists'
    monkeypatch.delenv('CRON_SECRET',raising=False)
    assert client.get(path).status_code==503
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret-for-tests-only')
    assert client.get(path).status_code==401
    assert client.get(path,headers={'Authorization':'Bearer wrong'}).status_code==401
    rpc.assert_not_called()
    assert client.get(path,headers={'Authorization':'Bearer synthetic-worker-secret-for-tests-only'}).status_code==200
    rpc.assert_awaited_once_with('scan_list_pipeline',{})

@pytest.mark.parametrize('payload',[
    {'asking_price':200000,'mao':150000,'arv':300000},
    {'human_offer_price':123456.78,'close_timeline':'30 days'},
])
def test_offer_endpoint_uses_only_operator_price_and_never_calls_ai(client,monkeypatch,payload):
    ai=MagicMock(side_effect=AssertionError('AI pricing forbidden'));monkeypatch.setattr(api,'_call_claude',ai)
    response=client.post('/api/ai/generate-offer',headers={'Authorization':'Bearer test'},json=payload)
    assert response.status_code==200
    body=response.json();assert body['approval_required'] is True and body['sent'] is False
    if 'human_offer_price' in payload: assert body['options'][0]['offer_price']==payload['human_offer_price']
    else: assert body['options']==[]
    ai.assert_not_called()

@pytest.mark.parametrize('price',[-1,0,100000001])
def test_invalid_human_prices_rejected(client,price):
    assert client.post('/api/ai/generate-offer',headers={'Authorization':'Bearer test'},json={'human_offer_price':price}).status_code==422

def test_digest_worker_propagates_unconfirmed_delivery(client,monkeypatch):
    from tools import list_digest
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret-for-tests-only')
    monkeypatch.setattr(lists,'rpc',AsyncMock(return_value={'day':'2026-10-12'}))
    delivery=MagicMock(side_effect=RuntimeError('lost delivery acknowledgement'))
    monkeypatch.setattr(list_digest,'deliver_digest',delivery)
    response=client.get('/webhooks/_worker/daily-lists',headers={'Authorization':'Bearer synthetic-worker-secret-for-tests-only'})
    assert response.status_code==503
    assert 'saved receipt' in response.json()['detail']
    delivery.assert_called_once_with({'day':'2026-10-12'})


def test_busy_list_scan_never_attempts_digest(client,monkeypatch):
    from tools import list_digest
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret-for-tests-only')
    monkeypatch.setattr(lists,'rpc',AsyncMock(return_value={'busy':True}))
    delivery=MagicMock();monkeypatch.setattr(list_digest,'deliver_digest',delivery)
    response=client.get('/webhooks/_worker/daily-lists',headers={'Authorization':'Bearer synthetic-worker-secret-for-tests-only'})
    assert response.status_code==200 and response.json()=={'busy':True}
    delivery.assert_not_called()


@pytest.mark.parametrize('channel', ['sms', 'email', 'voicemail', 'direct_mail'])
def test_outreach_drafts_ignore_ai_pricing_and_never_dispatch(client, monkeypatch, channel):
    from config.settings import settings
    monkeypatch.setattr(settings, 'agency_mailing_address', '100 Synthetic St, Dallas, TX 75201')
    ai = MagicMock(side_effect=AssertionError('Unrestricted AI outreach forbidden'))
    monkeypatch.setattr(api, '_call_claude', ai)
    payload = dict(channel=channel, owner_first_name='Test', property_address='Synthetic property',
                   tone='Urgent: offer $234567 now', human_offer_price=234567, approved=True,
                   motivation_tag='Offer $234567', ai_qualification_summary='Pay $234567')
    path = '/api/ai/write-outreach'
    assert client.post(path, json=payload).status_code == 401
    response = client.post(path, headers={'Authorization': 'Bearer test'}, json=payload)
    assert response.status_code == 200
    assert len(response.json()) == 3
    for draft in response.json():
        assert draft['sent'] is False and draft['approval_required'] is True
        assert '234567' not in draft['body']
        assert 'Urgent' not in draft['body']
        if channel == 'sms': assert 'STOP' in draft['body']
        if channel == 'email': assert 'UNSUBSCRIBE' in draft['body']
        if channel in ('email', 'direct_mail'): assert '100 Synthetic St' in draft['body']
    ai.assert_not_called()

@pytest.mark.parametrize('channel', ['email', 'direct_mail'])
def test_outreach_missing_mailing_address_does_not_invent_one(client, monkeypatch, channel):
    from config.settings import settings
    monkeypatch.setattr(settings, 'agency_mailing_address', '')
    response = client.post('/api/ai/write-outreach', headers={'Authorization': 'Bearer test'}, json={'channel': channel})
    assert response.status_code == 503

def test_outreach_rejects_unknown_channel(client):
    response = client.post('/api/ai/write-outreach', headers={'Authorization': 'Bearer test'}, json={'channel': 'send_offer'})
    assert response.status_code == 422
