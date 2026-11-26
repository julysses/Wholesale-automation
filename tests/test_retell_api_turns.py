from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools import retell_api_turns as worker
from tools.retell_api_chat import AgentText

TURN='00000000-0000-4000-8000-000000000001'
SESSION='00000000-0000-4000-8000-000000000002'
LEAD='00000000-0000-4000-8000-000000000003'

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(worker,'ready',lambda:True)
    monkeypatch.setenv('RETELL_SMS_AGENT_ID','agent_test');monkeypatch.setenv('RETELL_SMS_API_KEY','test-secret');monkeypatch.setenv('RETELL_SMS_AGENT_VERSION','2')
    monkeypatch.setattr(worker.settings,'sms_allowed_recipients','+12145550196');monkeypatch.setattr(worker.settings,'twilio_from_number','+14695550100')
    monkeypatch.setattr(worker.SMSClient,'_in_allowed_hours',lambda self:True)
    monkeypatch.setattr(worker,'sms_consent_blocker',lambda *a:None)
    turn={'id':TURN,'session_id':SESSION,'status':'queued','recipient_text':' Real reply.\nDo not rewrite. ',
          'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
    session={'id':SESSION,'lead_id':LEAD,'phone_number':'+12145550196','sender_number':'+14695550100','status':'pending'}
    lead={'id':LEAD,'dnc':False,'status':'new','owner_phone_1':'+12145550196'}
    inquiry={'id':SESSION,'delivery_transport':'app_twilio','status':'accepted'}
    rows={'retell_api_turns':turn,'retell_api_sessions':session,'leads':lead,'retell_form_sms_jobs':inquiry}
    monkeypatch.setattr(worker,'_row',lambda db,table,id:rows[table])
    claim={'claimed':True,'turn_id':TURN,'session_id':SESSION,'lead_id':LEAD,'recipient_text':turn['recipient_text'],'create_session':True,'chat_id':None}
    results={'claim_retell_api_turn':claim,'bind_retell_api_session':{'bound':True,'replayed':False},'save_retell_api_generation':{'saved':True},'hold_retell_api_turn':{'held':True}}
    db=Mock()
    db.rpc.side_effect=lambda name,args:SimpleNamespace(execute=lambda:SimpleNamespace(data=results[name]))
    provider=Mock();provider.create.return_value='chat_test';provider.complete.return_value=(AgentText('m1','Generated response'),)
    constructor=Mock(return_value=provider);monkeypatch.setattr(worker,'RetellAPIChat',constructor)
    return SimpleNamespace(db=db,provider=provider,constructor=constructor,claim=claim,results=results,turn=turn,session=session,lead=lead,inquiry=inquiry)


def test_late_ack_failure_before_generation_prevents_any_provider_call(setup):
    setup.inquiry['status']='review'
    assert worker.process_turn(setup.db,TURN)['status']=='not_eligible'
    setup.provider.create.assert_not_called();setup.provider.complete.assert_not_called()


def test_ack_failure_during_session_creation_prevents_completion(setup):
    def create(*args):
        setup.inquiry['status']='review';setup.session['status']='review'
        return 'chat_test'
    setup.provider.create.side_effect=create
    assert worker.process_turn(setup.db,TURN)['status']=='review'
    setup.provider.complete.assert_not_called()

def test_disabled_is_inert_and_invalid_identity_rejected_before_database(monkeypatch):
    monkeypatch.setattr(worker,'ready',lambda:False);db=Mock()
    assert worker.process_turn(db,TURN)['status']=='disabled';db.rpc.assert_not_called();db.table.assert_not_called()
    with pytest.raises(ValueError):worker.process_turn(db,'bad')

def test_create_and_generate_use_durable_identity_real_text_and_do_not_send(setup):
    result=worker.process_turn(setup.db,TURN)
    assert result=={'status':'generated','message_count':1,'dispatch_authorized':False}
    setup.provider.create.assert_called_once_with(SESSION,LEAD)
    setup.provider.complete.assert_called_once_with('chat_test',setup.turn['recipient_text'],SESSION,LEAD)
    assert [c.args[0] for c in setup.db.rpc.call_args_list]==['claim_retell_api_turn','bind_retell_api_session','save_retell_api_generation']
    assert setup.db.rpc.call_args.args[1]['p_messages']==[{'message_id':'m1','content':'Generated response'}]

def test_existing_api_session_generates_without_recreation(setup):
    setup.claim.update(create_session=False,chat_id='chat_existing')
    assert worker.process_turn(setup.db,TURN)['status']=='generated'
    setup.provider.create.assert_not_called();setup.provider.complete.assert_called_once_with('chat_existing',setup.turn['recipient_text'],SESSION,LEAD)

@pytest.mark.parametrize('patch',[{'claimed':False},{'claimed':True,'turn_id':SESSION},{'claimed':True,'recipient_text':'Fabricated'},{'claimed':True,'session_id':TURN}])
def test_absent_or_mismatched_claim_cannot_call_provider(setup,patch):
    setup.claim.update(patch);worker.process_turn(setup.db,TURN)
    setup.provider.create.assert_not_called();setup.provider.complete.assert_not_called()

@pytest.mark.parametrize('stage',['create','complete','bind','save'])
def test_uncertain_operations_are_held_and_never_retried(setup,stage):
    if stage in {'create','complete'}:getattr(setup.provider,stage).side_effect=RuntimeError('private provider data')
    elif stage=='bind':setup.results['bind_retell_api_session']={}
    else:setup.results['save_retell_api_generation']={}
    result=worker.process_turn(setup.db,TURN)
    assert result['status']=='review';assert result['dispatch_authorized'] is False
    assert setup.provider.create.call_count==1;assert setup.provider.complete.call_count<=1
    if stage in {'create','bind'}:setup.provider.complete.assert_not_called()
    assert 'private' not in setup.db.rpc.call_args.args[1]['p_reason']

def test_replayed_session_binding_does_not_authorize_another_completion(setup):
    setup.results['bind_retell_api_session']={'bound':True,'replayed':True}
    assert worker.process_turn(setup.db,TURN)['status']=='review';setup.provider.complete.assert_not_called()

@pytest.mark.parametrize('condition',['dnc','phone','sender','expired','control','claimed'])
def test_initial_ineligible_context_never_claims_or_calls_provider(setup,condition):
    if condition=='dnc':setup.lead['dnc']=True
    if condition=='phone':setup.lead['owner_phone_1']='+12145550199'
    if condition=='sender':setup.session['sender_number']='+14695550199'
    if condition=='expired':setup.turn['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    if condition=='control':setup.turn['recipient_text']='STOP'
    if condition=='claimed':setup.turn['status']='generating'
    assert worker.process_turn(setup.db,TURN)['status']=='not_eligible'
    setup.db.rpc.assert_not_called();setup.provider.create.assert_not_called();setup.provider.complete.assert_not_called()

def test_consent_revoked_after_session_creation_blocks_completion(setup,monkeypatch):
    checks=iter([None,None,'suppressed'])
    monkeypatch.setattr(worker,'sms_consent_blocker',lambda *a:next(checks))
    assert worker.process_turn(setup.db,TURN)['status']=='review'
    setup.provider.create.assert_called_once();setup.provider.complete.assert_not_called()

def test_hold_failure_is_not_reported_as_persisted_review(setup):
    setup.provider.create.side_effect=RuntimeError();setup.results['hold_retell_api_turn']={'held':False}
    assert worker.process_turn(setup.db,TURN)['status']=='hold_unconfirmed'

@pytest.mark.parametrize('missing',['RETELL_APP_TRANSPORT_ENABLED','RETELL_APP_TEST_APPROVED','RETELL_FORM_SMS_ENABLED','RETELL_SMS_LIVE_ENABLED','RETELL_SMS_TRANSPORT','RETELL_SMS_AGENT_ID','RETELL_SMS_API_KEY','RETELL_SMS_AGENT_VERSION','sms_live_enabled','sms_allowed_recipients'])
def test_app_transport_requires_its_own_approval_and_all_existing_pause_gates(monkeypatch,missing):
    for key,value in {'RETELL_APP_TRANSPORT_ENABLED':'true','RETELL_APP_TEST_APPROVED':'true',
        'RETELL_FORM_SMS_ENABLED':'true','RETELL_SMS_LIVE_ENABLED':'true','RETELL_SMS_TRANSPORT':'app_twilio',
        'RETELL_SMS_AGENT_ID':'agent_test','RETELL_SMS_API_KEY':'test-key','RETELL_SMS_AGENT_VERSION':'2'}.items():
        monkeypatch.setenv(key,value)
    monkeypatch.delenv('RETELL_APP_ACCEPTANCE_VERIFIED',raising=False)
    monkeypatch.setattr(worker.settings,'sms_live_enabled',True)
    monkeypatch.setattr(worker.settings,'sms_allowed_recipients','+12145550196')
    now = datetime.now(timezone.utc)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', SESSION)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT', now.isoformat())
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', (now+timedelta(minutes=15)).isoformat())
    assert worker.ready() is True
    if missing=='sms_live_enabled':monkeypatch.setattr(worker.settings,missing,False)
    elif missing=='sms_allowed_recipients':monkeypatch.setattr(worker.settings,missing,'')
    else:monkeypatch.delenv(missing)
    assert worker.ready() is False


def owner_scope(monkeypatch, setup):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv('RETELL_APP_TEST_APPROVED', 'true')
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', SESSION)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT', (now-timedelta(minutes=1)).isoformat())
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', (now+timedelta(minutes=14)).isoformat())
    setup.db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value.data = [{'id': TURN}]


@pytest.mark.parametrize('case', ['wrong_job', 'second_turn', 'expired', 'blank_target'])
def test_direct_generation_cannot_bypass_owner_scope(setup, monkeypatch, case):
    owner_scope(monkeypatch, setup)
    if case == 'wrong_job': monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', LEAD)
    if case == 'blank_target': monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', '')
    if case == 'expired': monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    if case == 'second_turn':
        setup.db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value.data = [{'id': LEAD}]
    assert worker.process_turn(setup.db, TURN)['status'] == 'not_eligible'
    setup.db.rpc.assert_not_called()
    setup.provider.create.assert_not_called()
    setup.provider.complete.assert_not_called()


def test_owner_deadline_crossed_during_create_holds_without_completion(setup, monkeypatch):
    owner_scope(monkeypatch, setup)
    def create(*args):
        monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
        return 'chat_test'
    setup.provider.create.side_effect = create
    assert worker.process_turn(setup.db, TURN)['status'] == 'review'
    setup.provider.create.assert_called_once()
    setup.provider.complete.assert_not_called()


def test_valid_owner_first_turn_still_generates_exactly_once(setup, monkeypatch):
    owner_scope(monkeypatch, setup)
    assert worker.process_turn(setup.db, TURN)['status'] == 'generated'
    setup.provider.create.assert_called_once()
    setup.provider.complete.assert_called_once()


@pytest.mark.parametrize('code,expected', [('provider_http_200','provider_http_200'),
    ('private credential','provider_or_persistence_failure')])
def test_failure_diagnostic_is_allowlisted_without_replay(setup, code, expected):
    from tools.retell_api_chat import ChatOutcomeUncertain
    setup.provider.complete.side_effect = ChatOutcomeUncertain('secret response', code=code)
    assert worker.process_turn(setup.db,TURN)['status'] == 'review'
    assert setup.db.rpc.call_args.args[1]['p_reason'] == expected + '; no automatic retry'
    assert setup.provider.complete.call_count == 1
