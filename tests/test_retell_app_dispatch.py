from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools import retell_app_dispatch as dispatch
from tools.twilio_receipts import reconcile_twilio_receipt
from tests.test_twilio_receipt_reconciliation import DB, PHONE, SID

LEAD='00000000-0000-4000-8000-000000000001'
SESSION='00000000-0000-4000-8000-000000000002'
SENDER='+14695550100'

@pytest.mark.parametrize('now,expiry,seconds',[
 ('2026-10-16T18:00:00-05:00','2026-10-16T18:15:00-05:00',300),
 ('2026-10-16T18:59:00-05:00','2026-10-16T19:10:00-05:00',50),
 ('2026-10-16T18:00:00-05:00','2026-10-16T18:00:30-05:00',20),
 ('2026-10-16T18:59:45-05:00','2026-10-16T19:10:00-05:00',0),
 ('2026-10-16T19:00:00-05:00','2026-10-16T19:10:00-05:00',0),
 ('2026-10-16T08:59:59-05:00','2026-10-16T09:15:00-05:00',0),
 ('2026-11-01T18:59:00-06:00','2026-11-01T19:15:00-06:00',50),
 ('2026-10-16T18:00:00-05:00','2026-10-16T17:59:59-05:00',0),
 ('2026-10-16T18:00:00-05:00','2026-10-16T18:15:00',0),
])
def test_queue_deadline_respects_contact_close_expiry_and_dst(monkeypatch,now,expiry,seconds):
    monkeypatch.setattr(dispatch.settings,'tcpa_allowed_start_hour',9);monkeypatch.setattr(dispatch.settings,'tcpa_allowed_end_hour',19)
    assert dispatch.queue_validity(expiry,datetime.fromisoformat(now))==seconds

@pytest.fixture
def setup(monkeypatch):
    db=DB('submitting');claim={'message_id':db.reference,'session_id':SESSION,'lead_id':LEAD,
        'phone_number':PHONE,'sender_number':SENDER,'body':'Original consented message',
        'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
    db.rows[0]['lead_id']=LEAD;db.rows[0]['raw_payload']={'transport':'app_twilio','sender_number':SENDER,'form_job_id':SESSION}
    monkeypatch.setattr(dispatch,'dispatch_ready',lambda:True);monkeypatch.setattr(dispatch,'_eligible',lambda *a:True)
    monkeypatch.setattr(dispatch,'queue_validity',lambda *a:120)
    monkeypatch.setattr(dispatch.settings,'twilio_webhook_base_url','https://wholesale-automation.vercel.app')
    monkeypatch.setattr(dispatch.settings,'twilio_messaging_service_sid','MG'+'a'*32)
    alerts=Mock();monkeypatch.setattr(dispatch,'record_provider_alert',alerts)
    def sync(db,id):
        row=db.rows[0];return {'synced':True,'carrier_status':row['status'],
             'carrier_accepted':row['status'] in dispatch.PROGRESS and bool(row['raw_payload'].get('provider_sid'))}
    monkeypatch.setattr(dispatch,'sync_outcome',sync)
    provider=Mock();provider.messages.create.return_value=SimpleNamespace(sid=SID,status='queued')
    constructor=Mock(return_value=provider);monkeypatch.setattr('twilio.rest.Client',constructor)
    return SimpleNamespace(db=db,claim=claim,provider=provider,constructor=constructor,alerts=alerts)

def test_one_provider_request_has_exact_callback_service_and_finite_validity(setup):
    result=dispatch._submit(setup.db,setup.claim)
    assert result['status']=='queued';assert result['carrier_accepted'] is True
    setup.provider.messages.create.assert_called_once()
    payload=setup.provider.messages.create.call_args.kwargs
    assert payload['status_callback'].endswith('?message_id='+setup.db.reference)
    assert payload['messaging_service_sid']=='MG'+'a'*32
    assert payload['from_']==SENDER and payload['to']==PHONE and payload['validity_period']==120
    assert setup.db.rows[0]['raw_payload']['provider_sid']==SID
    assert setup.db.rows[0]['raw_payload']['form_job_id']==SESSION

@pytest.mark.parametrize('provider_returns',['success','timeout'])
def test_early_callback_wins_over_late_http_result_without_second_send(setup,provider_returns):
    def create(**kwargs):
        reconcile_twilio_receipt(setup.db,setup.db.reference,PHONE,SID,'delivered')
        if provider_returns=='timeout':raise TimeoutError('private provider error')
        return SimpleNamespace(sid=SID,status='accepted')
    setup.provider.messages.create.side_effect=create
    result=dispatch._submit(setup.db,setup.claim)
    assert result['status']=='delivered';assert result['carrier_accepted'] is True
    assert setup.provider.messages.create.call_count==1;setup.alerts.assert_not_called()

def test_unknown_timeout_is_parked_and_cannot_reuse_claim(setup):
    setup.provider.messages.create.side_effect=TimeoutError()
    assert dispatch._submit(setup.db,setup.claim)['status']=='unknown'
    with pytest.raises(RuntimeError,match='claim mismatch'):dispatch._submit(setup.db,setup.claim)
    assert setup.provider.messages.create.call_count==1;setup.alerts.assert_called_once()

@pytest.mark.parametrize('failure',['failed','undelivered'])
def test_provider_returned_failure_is_not_reported_as_success(setup,failure):
    setup.provider.messages.create.return_value=SimpleNamespace(sid=SID,status=failure)
    result=dispatch._submit(setup.db,setup.claim)
    assert result['status']==failure;assert result['carrier_accepted'] is False
    setup.alerts.assert_called_once()

@pytest.mark.parametrize('field,value',[('body','Different'),('phone_number','+12145550199'),('lead_id',SESSION),('status','accepted')])
def test_mismatched_or_previously_consumed_ledger_cannot_send(setup,field,value):
    setup.db.rows[0][field]=value
    with pytest.raises(RuntimeError):dispatch._submit(setup.db,setup.claim)
    setup.provider.messages.create.assert_not_called()

def test_suppression_after_claim_blocks_without_provider(setup,monkeypatch):
    monkeypatch.setattr(dispatch,'_eligible',lambda *a:False)
    assert dispatch._submit(setup.db,setup.claim)['status']=='blocked'
    setup.provider.messages.create.assert_not_called()

def test_expired_last_boundary_blocks_without_provider(setup,monkeypatch):
    monkeypatch.setattr(dispatch,'queue_validity',lambda *a:0)
    assert dispatch._submit(setup.db,setup.claim)['status']=='blocked'
    setup.provider.messages.create.assert_not_called()

def test_disabled_entrypoints_never_read_claim_or_send(monkeypatch):
    monkeypatch.setattr(dispatch,'dispatch_ready',lambda:False);db=Mock()
    assert dispatch.process_ack(db,SESSION)['status']=='disabled'
    assert dispatch.process_reply(db,SESSION)['status']=='disabled'
    db.table.assert_not_called();db.rpc.assert_not_called()

def test_conflicting_provider_sid_preserves_callback_but_holds_operation(setup):
    def create(**kwargs):
        reconcile_twilio_receipt(setup.db,setup.db.reference,PHONE,SID,'delivered')
        return SimpleNamespace(sid='SM'+'c'*32,status='accepted')
    setup.provider.messages.create.side_effect=create
    setup.db.rpc=Mock(return_value=SimpleNamespace(execute=lambda:SimpleNamespace(data={'held':True})))
    with pytest.raises(RuntimeError,match='requires review'):dispatch._submit(setup.db,setup.claim)
    assert setup.db.rows[0]['status']=='delivered'
    assert setup.db.rows[0]['raw_payload']['provider_sid']==SID
    assert setup.db.rpc.call_args.args[0]=='review_retell_app_dispatch'
    assert setup.provider.messages.create.call_count==1
    setup.alerts.assert_called_once()

@pytest.mark.parametrize('won',[[],[{'id':LEAD}],[{'id':SESSION},{'id':SESSION}],None])
def test_ack_wrapper_never_sends_without_single_exact_new_claim(monkeypatch,won):
    monkeypatch.setattr(dispatch,'dispatch_ready',lambda:True);monkeypatch.setattr(dispatch,'_eligible',lambda *a:True)
    job={'id':SESSION,'lead_id':LEAD,'delivery_transport':'app_twilio','status':'scheduled',
         'delivery_body':dispatch.APP_ACKNOWLEDGMENT,'phone_number':PHONE,'delivery_sender':SENDER,'expires_at':'2026-10-17T15:00:00+00:00'}
    monkeypatch.setattr(dispatch,'_row',lambda *a:job)
    submit=Mock();monkeypatch.setattr(dispatch,'_submit',submit)
    db=Mock();db.rpc.return_value.execute.return_value.data=won
    if won==[]:assert dispatch.process_ack(db,SESSION)['status']=='not_claimed'
    else:
        with pytest.raises(RuntimeError):dispatch.process_ack(db,SESSION)
    submit.assert_not_called()

def test_reply_wrapper_refuses_a_claim_for_another_turn(monkeypatch):
    monkeypatch.setattr(dispatch,'dispatch_ready',lambda:True);monkeypatch.setattr(dispatch,'_eligible',lambda *a:True)
    rows={'retell_api_turns':{'id':LEAD,'session_id':SESSION,'status':'generated','expires_at':'2026-10-17T15:00:00+00:00'},
          'retell_api_sessions':{'id':SESSION,'lead_id':LEAD,'phone_number':PHONE,'sender_number':SENDER}}
    monkeypatch.setattr(dispatch,'_row',lambda sb,table,id:rows[table])
    submit=Mock();monkeypatch.setattr(dispatch,'_submit',submit)
    db=Mock();db.rpc.return_value.execute.return_value.data={'claimed':True,'turn_id':SESSION,'session_id':SESSION}
    with pytest.raises(RuntimeError):dispatch.process_reply(db,LEAD)
    submit.assert_not_called()
