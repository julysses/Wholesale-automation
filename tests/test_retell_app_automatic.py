from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tools import retell_app_automatic as auto
from tools import retell_api_turns as generation
from web.api import nurture_api

JOB='00000000-0000-4000-8000-000000000001'
TURN='00000000-0000-4000-8000-000000000002'
PHONE='+12145550196'


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setenv('RETELL_APP_AUTOMATION_ENABLED','true')
    monkeypatch.setenv('RETELL_APP_ACCEPTANCE_VERIFIED','true')
    monkeypatch.delenv('RETELL_APP_AUTOMATION_TEST_JOB_ID',raising=False)
    monkeypatch.delenv('RETELL_APP_ALL_CONSENTED_FORMS',raising=False)
    monkeypatch.setattr(auto,'dispatch_ready',lambda:True)
    monkeypatch.setattr(auto.settings,'sms_allowed_recipients',PHONE)
    monkeypatch.setattr(auto.SMSClient,'_in_allowed_hours',lambda _:True)
    db=Mock();db.rpc.return_value.execute.return_value.data={'selected':True,'action':'ack','reference':JOB,'job_id':JOB}
    workers={name:Mock(return_value={'status':'test_outcome'}) for name in ['process_ack','process_turn','process_reply']}
    for name,worker in workers.items():monkeypatch.setattr(auto,name,worker)
    return db,workers


@pytest.mark.parametrize('action,worker,reference',[('ack','process_ack',JOB),('generate','process_turn',TURN),('reply','process_reply',TURN)])
def test_one_queue_step_invokes_only_one_exact_worker(production,action,worker,reference):
    db,workers=production
    db.rpc.return_value.execute.return_value.data.update(action=action,reference=reference)
    result=auto.step(db)
    assert result['processed']==1 and result['action']==action
    db.rpc.assert_called_once_with('pick_retell_app_work',{'p_job':None,'p_first_turn_only':False,'p_phones':[PHONE]})
    for name,callback in workers.items():
        if name==worker:callback.assert_called_once_with(db,reference)
        else:callback.assert_not_called()


@pytest.mark.parametrize('gate',['automation','dispatch','acceptance','hours'])
def test_off_or_outside_hours_is_inert(production,monkeypatch,gate):
    db,workers=production
    if gate=='automation':monkeypatch.delenv('RETELL_APP_AUTOMATION_ENABLED')
    if gate=='dispatch':monkeypatch.setattr(auto,'dispatch_ready',lambda:False)
    if gate=='acceptance':monkeypatch.delenv('RETELL_APP_ACCEPTANCE_VERIFIED')
    if gate=='hours':monkeypatch.setattr(auto.SMSClient,'_in_allowed_hours',lambda _:False)
    assert auto.step(db)['processed']==0
    db.rpc.assert_not_called()
    for worker in workers.values():worker.assert_not_called()


def configure_test(monkeypatch):
    now=datetime.now(timezone.utc)
    monkeypatch.setenv('RETELL_APP_TEST_APPROVED','true')
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID',JOB)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT',(now-timedelta(minutes=1)).isoformat())
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT',(now+timedelta(minutes=14)).isoformat())


def test_owner_mode_scopes_every_selection_to_one_job_first_turn_and_allowlist(production,monkeypatch):
    db,_=production;configure_test(monkeypatch)
    monkeypatch.delenv('RETELL_APP_ACCEPTANCE_VERIFIED')
    auto.step(db)
    db.rpc.assert_called_once_with('pick_retell_app_work',{'p_job':JOB,'p_first_turn_only':True,'p_phones':[PHONE]})


@pytest.mark.parametrize('kind',['expired','future','too_long','naive','bad_id','empty_id','no_start','no_approval','no_phones'])
def test_invalid_test_scope_never_falls_back_to_verified_production(production,monkeypatch,kind):
    db,_=production;configure_test(monkeypatch);now=datetime.now(timezone.utc)
    if kind=='expired':monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT',(now-timedelta(seconds=1)).isoformat())
    if kind=='future':monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT',(now+timedelta(minutes=1)).isoformat())
    if kind=='too_long':monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT',(now+timedelta(hours=1)).isoformat())
    if kind=='naive':monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT',now.replace(tzinfo=None).isoformat())
    if kind=='bad_id':monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID','bad')
    if kind=='empty_id':monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID','')
    if kind=='no_start':monkeypatch.delenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT')
    if kind=='no_approval':monkeypatch.delenv('RETELL_APP_TEST_APPROVED')
    if kind=='no_phones':monkeypatch.setattr(auto.settings,'sms_allowed_recipients','')
    assert auto.scope() is None and auto.step(db)['status']=='disabled'
    db.rpc.assert_not_called()


def test_pausing_after_selection_does_not_call_worker(production,monkeypatch):
    db,workers=production
    def select(*args):
        monkeypatch.setenv('RETELL_APP_AUTOMATION_ENABLED','false')
        return SimpleNamespace(execute=lambda:SimpleNamespace(data={'selected':True,'action':'ack','reference':JOB,'job_id':JOB}))
    db.rpc.side_effect=select
    assert auto.step(db)['status']=='disabled'
    for worker in workers.values():worker.assert_not_called()


@pytest.mark.parametrize('selected',[None,{}, {'selected':True,'action':'unknown','reference':JOB,'job_id':JOB},
    {'selected':True,'action':'ack','reference':TURN,'job_id':JOB}])
def test_invalid_selection_cannot_invoke_provider_worker(production,selected):
    db,workers=production;db.rpc.return_value.execute.return_value.data=selected
    with pytest.raises((ValueError,RuntimeError)):auto.step(db)
    for worker in workers.values():worker.assert_not_called()


def test_out_of_scope_selection_is_rejected_in_test_mode(production,monkeypatch):
    db,workers=production;configure_test(monkeypatch)
    db.rpc.return_value.execute.return_value.data.update(job_id=TURN,reference=TURN)
    with pytest.raises(RuntimeError):auto.step(db)
    for worker in workers.values():worker.assert_not_called()


def test_worker_failure_does_not_fall_back_or_run_next_operation(production):
    db,workers=production;workers['process_ack'].side_effect=RuntimeError('uncertain')
    with pytest.raises(RuntimeError):auto.step(db)
    assert workers['process_ack'].call_count==1
    workers['process_turn'].assert_not_called();workers['process_reply'].assert_not_called()


def test_general_consented_mode_requires_explicit_verified_acceptance(production,monkeypatch):
    monkeypatch.setenv('RETELL_APP_ALL_CONSENTED_FORMS','true')
    monkeypatch.setattr(auto.settings,'sms_allowed_recipients','')
    assert auto.scope()=={'p_job':None,'p_first_turn_only':False,'p_phones':None}
    assert generation.recipient_allowed('+12145550199') is True
    monkeypatch.delenv('RETELL_APP_ACCEPTANCE_VERIFIED')
    monkeypatch.setenv('RETELL_APP_TEST_APPROVED','true')
    assert auto.scope() is None
    assert generation.recipient_allowed('+12145550199') is False


def test_automatic_route_is_post_authenticated_and_disabled_before_storage(production,monkeypatch):
    monkeypatch.setenv('CRON_SECRET','auto-test');monkeypatch.setenv('RETELL_APP_AUTOMATION_ENABLED','false')
    get_db=Mock();monkeypatch.setattr(nurture_api,'_db',get_db)
    app=FastAPI();app.include_router(nurture_api.router);client=TestClient(app)
    path='/webhooks/_worker/retell-app/automatic';auth={'Authorization':'Bearer auto-test'}
    assert client.get(path,headers=auth).status_code==405
    assert client.post(path).status_code==401
    assert client.post(path,headers=auth).json()['status']=='disabled'
    get_db.assert_not_called()


@pytest.mark.parametrize('action,reference,expected', [('generate', TURN, True), ('reply', TURN, True),
    ('ack', JOB, False), ('generate', JOB, False), ('reply', JOB, False)])
def test_exact_reply_retest_cannot_repeat_ack_or_select_any_other_input(production, monkeypatch, action, reference, expected):
    db, workers = production; configure_test(monkeypatch)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_TURN_ID', TURN)
    db.rpc.return_value.execute.return_value.data.update(action=action, reference=reference)
    result = auto.step(db)
    db.rpc.assert_called_once_with('pick_retell_app_work', {'p_job': JOB, 'p_first_turn_only': False, 'p_phones': [PHONE]})
    assert result['processed'] == (1 if expected else 0)
    assert sum(worker.call_count for worker in workers.values()) == (1 if expected else 0)


def test_invalid_exact_reply_target_cannot_fall_back_to_first_turn(production, monkeypatch):
    db, workers = production; configure_test(monkeypatch)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_TURN_ID', 'invalid')
    assert auto.step(db)['status'] == 'disabled'
    db.rpc.assert_not_called()
