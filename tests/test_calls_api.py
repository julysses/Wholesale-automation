from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
from web.api import calls_api as calls
from tools.facebook_consent import AI_DISCLOSURE,AI_CHECKBOX_KEY,HILLTOP_CONSENT_FORM_ID

PHONE='+12147010100'


@pytest.fixture
def setup(monkeypatch):
    for key,value in {'ai_calling_live_enabled':True,'ai_calling_allowed_recipients':PHONE,
        'retell_api_key':'test-key','retell_agent_id':'agent_test','retell_from_number':'+14698049920',
        'retell_webhook_secret':'test-secret','tcpa_allowed_start_hour':9,'tcpa_allowed_end_hour':19}.items():
        monkeypatch.setattr(calls.settings,key,value)
    body=calls.StartCall(request_id=uuid4(),lead_id=uuid4(),phone_number=PHONE)
    lead={'source':'facebook_lead_ad','dnc':False,'ai_calling_paused':False,'owner_phone_1':PHONE,
        'internal_notes':'FB leadgen_id=test','property_address':'TEST ONLY'}
    receipt={'source':'facebook_native_form','phone':PHONE,'leadgen_id':'test',
        'form_id':HILLTOP_CONSENT_FORM_ID,'submitted_at':'2026-10-07T12:00:00+00:00',
        'raw_responses':[{'checkbox_key':AI_CHECKBOX_KEY,'is_checked':'1'}],
        'ai_calls':{'accepted':True,'disclosure':AI_DISCLOSURE}}
    db=MagicMock()
    def table(name):
        q=MagicMock()
        rows={'leads':[lead],'app_notifications':[{'metadata':{'consent_receipt':receipt}}],
              'retell_call_requests':[]}.get(name,[])
        q.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=rows
        q.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data=rows
        q.upsert.return_value.execute.return_value.data=[{'id':str(body.request_id)}]
        update=q.update.return_value
        update.eq.return_value=update
        update.execute.return_value.data=[{'id':str(body.request_id)}]
        return q
    db.table.side_effect=table
    db.rpc.return_value.execute.return_value.data={'suppressed':False,'claimed':True,'blocker':None}
    monkeypatch.setattr(calls,'get_supabase_client',lambda:db)
    monkeypatch.setattr(calls,'_texas_now',lambda:datetime(2026,10,8,12,tzinfo=ZoneInfo('America/Chicago')))
    provider=MagicMock()
    provider.create_call.return_value=SimpleNamespace(call_id='call_test',status='registered')
    monkeypatch.setattr(calls,'RetellAdapter',lambda:provider)
    return body,lead,receipt,db,provider


def test_authorized_call_claimed_before_provider(setup):
    body,_,_,db,provider=setup
    result=calls.start_call(body,str(uuid4()))
    assert result['call_id']=='call_test'
    assert provider.create_call.call_args.args[0].request_id==str(body.request_id)
    assert any(call.args==('retell_call_requests',) for call in db.table.call_args_list)
    assert provider.create_call.call_count==1


@pytest.mark.parametrize('field,value', [('ai_calling_live_enabled',False),('retell_api_key',''),
    ('retell_webhook_secret',''),('ai_calling_allowed_recipients',''),
    ('ai_calling_allowed_recipients',PHONE+'.evil')])
def test_missing_live_configuration_refuses(setup,monkeypatch,field,value):
    body,_,_,_,provider=setup
    monkeypatch.setattr(calls.settings,field,value)
    with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('field,value',[('dnc',True),('dnc',None),('ai_calling_paused',True),
    ('owner_phone_1','+12145550199'),('internal_notes','unrelated lead')])
def test_lead_and_phone_gates(setup,field,value):
    body,lead,_,_,provider=setup
    lead[field]=value
    with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('field,value',[('phone','+12145550199'),('phone',''),('form_id','unknown'),
    ('submitted_at','invalid'),('submitted_at','2099-01-01T00:00:00+00:00'),
    ('raw_responses',[]),('raw_responses',[{'checkbox_key':AI_CHECKBOX_KEY,'is_checked':'0'}]),
    ('ai_calls',{'disclosure':'different'})])
def test_matching_explicit_ai_consent_required(setup,field,value):
    body,_,receipt,_,provider=setup
    receipt[field]=value
    with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('time',[(8,8),(8,19),(10,12)])
def test_quiet_hours_and_weekends_refuse(setup,monkeypatch,time):
    body,_,_,_,provider=setup
    monkeypatch.setattr(calls,'_texas_now',lambda:datetime(2026,10,time[0],time[1],tzinfo=ZoneInfo('America/Chicago')))
    with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('safety',[None,{}, {'suppressed':True}])
def test_suppression_or_unavailable_check_refuses(setup,safety):
    body,_,_,db,provider=setup
    db.rpc.return_value.execute.return_value.data=safety
    with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    provider.create_call.assert_not_called()


def test_timeout_marked_unknown_never_retried(setup):
    body,_,_,db,provider=setup
    provider.create_call.side_effect=httpx.ReadTimeout('ambiguous')
    with pytest.raises(HTTPException) as error:calls.start_call(body,str(uuid4()))
    assert error.value.status_code==502
    assert provider.create_call.call_count==1


@pytest.mark.parametrize('provider_id',[None,'call_existing'])
def test_existing_reference_does_not_resubmit(setup,provider_id):
    body,_,_,db,provider=setup
    row={'id':str(body.request_id),'lead_id':str(body.lead_id),'phone_number':PHONE,
         'status':'unknown' if provider_id is None else 'accepted','provider_call_id':provider_id}
    q=MagicMock();q.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[row]
    db.table.side_effect=lambda _:q
    if provider_id is None:
        with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    else:
        assert calls.start_call(body,str(uuid4()))['call_id']==provider_id
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('claim_result',[[],RuntimeError('database failure')])
def test_claim_failure_never_calls_provider(setup,claim_result):
    body,_,_,db,provider=setup
    def rpc(name, args):
        q=MagicMock()
        if name=='claim_retell_call':
            if isinstance(claim_result,Exception):q.execute.side_effect=claim_result
            else:q.execute.return_value.data=claim_result
        else:q.execute.return_value.data={'suppressed':False}
        return q
    db.rpc.side_effect=rpc
    with pytest.raises(HTTPException):calls.start_call(body,str(uuid4()))
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('status',['registered','ongoing','ended','not_connected','error'])
def test_status_only_for_recorded_calls(setup,status):
    body,_,_,db,provider=setup
    q=MagicMock()
    q.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'id':str(body.request_id)}]
    q.update.return_value.eq.return_value.execute.return_value.data=[{'id':str(body.request_id)}]
    db.table.side_effect=lambda _:q
    provider.get_call_status.return_value={'call_id':'call_test','call_status':status}
    assert calls.call_status('call_test')['call_status']==status
    assert q.update.called is (status in ('ended','not_connected','error'))


def test_unknown_call_status_cannot_query_provider(setup):
    _,_,_,_,provider=setup
    with pytest.raises(HTTPException) as error:calls.call_status('call_unknown')
    assert error.value.status_code==404
    provider.get_call_status.assert_not_called()


@pytest.mark.parametrize('field,value',[('call_id','different'),('call_status','dry_run')])
def test_invalid_provider_status_refuses(setup,field,value):
    body,_,_,db,provider=setup
    q=MagicMock();q.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'id':str(body.request_id)}]
    db.table.side_effect=lambda _:q
    provider.get_call_status.return_value={'call_id':'call_test','call_status':'ended',field:value}
    with pytest.raises(HTTPException) as error:calls.call_status('call_test')
    assert error.value.status_code==502
    q.update.assert_not_called()


@pytest.mark.parametrize('event,status,expected',[
    ('call_started','unknown','accepted'),('call_ended','unknown','completed'),
    ('call_analyzed','accepted','completed'),('call_started','completed',None)])
def test_signed_callback_reconciles_without_downgrading(setup,event,status,expected):
    body,_,_,db,_=setup
    row={'id':str(body.request_id),'lead_id':str(body.lead_id),'phone_number':PHONE,'status':status,'provider_call_id':None}
    q=MagicMock();q.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[row]
    update=q.update.return_value;update.eq.return_value=update;update.is_.return_value=update;update.execute.return_value.data=[row]
    db.table.side_effect=lambda _:q
    calls.reconcile_call({'event':event,'call':{'call_id':'call_test','to_number':PHONE,
        'metadata':{'request_id':str(body.request_id),'lead_id':str(body.lead_id)}}})
    if expected:
        assert q.update.call_args.args[0]=={'provider_call_id':'call_test','status':expected}
    else:q.update.assert_not_called()


@pytest.mark.parametrize('field,value',[('lead_id',str(uuid4())),('phone_number','+12145550199'),('provider_call_id','call_other')])
def test_callback_must_match_claim(setup,field,value):
    body,_,_,db,_=setup
    row={'id':str(body.request_id),'lead_id':str(body.lead_id),'phone_number':PHONE,'status':'unknown','provider_call_id':None,field:value}
    q=MagicMock();q.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[row]
    db.table.side_effect=lambda _:q
    with pytest.raises(ValueError):
        calls.reconcile_call({'event':'call_ended','call':{'call_id':'call_test','to_number':PHONE,
            'metadata':{'request_id':str(body.request_id),'lead_id':str(body.lead_id)}}})
    q.update.assert_not_called()


def test_approved_admin_observes_disabled_gate(setup,monkeypatch):
    from fastapi.testclient import TestClient
    from web.app import app
    from web import auth
    body,_,_,_,provider=setup
    identity=MagicMock()
    identity.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id=str(uuid4())))
    identity.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'status':'approved','role':'admin'}]
    monkeypatch.setattr(auth,'get_supabase_client',lambda:identity)
    monkeypatch.setattr(calls.settings,'ai_calling_live_enabled',False)
    response=TestClient(app).post('/api/calls/retell',headers={'Authorization':'Bearer admin'},json=body.model_dump(mode='json'))
    assert response.status_code==409
    assert 'disabled' in response.json()['detail']
    provider.create_call.assert_not_called()


def test_readiness_checks_without_contacting_provider(setup):
    body,lead,_,db,provider=setup
    # The empty unresolved-recipient lookup is separate from the latest attempt.
    original=db.table.side_effect
    def table(name):
        q=original(name)
        q.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value.data=[]
        return q
    db.table.side_effect=table
    lead['ai_calling_paused']=True
    result=calls.lead_readiness(body.lead_id)
    assert result['can_review'] is True
    assert result['can_call'] is False
    assert result['consent']['accepted'] is True
    provider.create_call.assert_not_called()


def test_unresolved_recipient_on_another_lead_blocks_review(setup):
    body,lead,_,db,provider=setup
    lead['ai_calling_paused']=True
    original=db.table.side_effect
    def table(name):
        q=original(name)
        if name=='retell_call_requests':
            query=q.select.return_value.eq.return_value
            query.neq.return_value.order.return_value.limit.return_value.execute.return_value.data=[{
                'id':str(uuid4()),'lead_id':str(uuid4()),'phone_number':PHONE,
                'status':'unknown','provider_call_id':None}]
        return q
    db.table.side_effect=table
    result=calls.lead_readiness(body.lead_id)
    assert result['can_review'] is False
    assert 'unresolved' in ' '.join(result['blockers'])
    provider.create_call.assert_not_called()


@pytest.mark.parametrize('acknowledged',[False,None])
def test_review_requires_explicit_acknowledgement(setup,acknowledged):
    body,_,_,db,provider=setup
    with pytest.raises(HTTPException):calls.review_lead(body.lead_id,acknowledged,str(uuid4()))
    db.table.assert_not_called()
    provider.create_call.assert_not_called()


def test_disabled_launch_cannot_unpause_through_review(setup,monkeypatch):
    body,lead,_,db,provider=setup
    lead['ai_calling_paused']=True
    monkeypatch.setattr(calls.settings,'ai_calling_live_enabled',False)
    with pytest.raises(HTTPException):calls.review_lead(body.lead_id,True,str(uuid4()))
    provider.create_call.assert_not_called()


def test_review_audits_before_unpause_without_placing_call(setup,monkeypatch):
    body,_,_,db,provider=setup
    readiness={'can_review':True,'blockers':[],'consent':{'submitted_at':'2026-10-07T12:00:00Z'}}
    monkeypatch.setattr(calls,'lead_readiness',lambda _:readiness)
    queries={}
    original=db.table.side_effect
    def table(name):
        queries.setdefault(name,original(name))
        return queries[name]
    db.table.side_effect=table
    calls.review_lead(body.lead_id,True,'operator_test')
    notice=queries['app_notifications'].upsert.call_args.args[0]
    assert notice['metadata']['operator_id']=='operator_test'
    assert queries['leads'].update.call_args.args[0]=={'ai_calling_paused':False}
    assert ('dnc',False) in [c.args for c in queries['leads'].update.return_value.eq.call_args_list]
    provider.create_call.assert_not_called()


def test_failed_review_receipt_cannot_unpause(setup,monkeypatch):
    body,_,_,db,provider=setup
    monkeypatch.setattr(calls,'lead_readiness',lambda _:{'can_review':True,'blockers':[],
        'consent':{'submitted_at':'2026-10-07T12:00:00Z'}})
    receipt_query=MagicMock();receipt_query.upsert.return_value.execute.side_effect=RuntimeError('unavailable')
    lead_query=MagicMock()
    db.table.side_effect=lambda name:receipt_query if name=='app_notifications' else lead_query
    with pytest.raises(HTTPException) as error:calls.review_lead(body.lead_id,True,'operator_test')
    assert error.value.status_code==503
    lead_query.update.assert_not_called()
    provider.create_call.assert_not_called()
