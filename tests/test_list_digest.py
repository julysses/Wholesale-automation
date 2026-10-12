from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest
from tools import list_digest as digest

NOW=datetime(2026,10,12,7,5,tzinfo=ZoneInfo('America/Chicago'))
SUMMARY={'day':'2026-10-12','new_leads':7,'stacked_records':2,'sources':[{'source_key':'tx-dallas-probate','status':'blocked','status_reason':'Login required','enabled':True,'received_batches':1,'expected_batches':1,'records_in':0}],'open_incidents':[],'top_ten':[]}

@pytest.fixture
def setup(monkeypatch):
 monkeypatch.setenv('LIST_DIGEST_ENABLED','true')
 monkeypatch.setattr(digest.settings,'notification_email','controlled@example.test')
 db=MagicMock(); sender=MagicMock(); sender.send.return_value=True
 monkeypatch.setattr(digest,'get_supabase_client',lambda:db)
 monkeypatch.setattr(digest,'EmailClient',lambda provider:sender)
 def rpc(name,params):
  if name=='reserve_list_digest':
   value={'day':params['p_day'],'message_id':params['p_message'],'recipient':params['p_recipient'],'summary':deepcopy(SUMMARY),'send_allowed':True}
  else:value={'digests':[{'day':SUMMARY['day'],'status':'accepted','delivered_at':None}]}
  return SimpleNamespace(execute=lambda:SimpleNamespace(data=value))
 db.rpc.side_effect=rpc
 return db,sender

def test_disabled_and_early_worker_never_reads_or_sends(setup,monkeypatch):
 db,sender=setup
 monkeypatch.setenv('LIST_DIGEST_ENABLED','false');assert digest.deliver_digest(SUMMARY,NOW)['status']=='disabled'
 monkeypatch.setenv('LIST_DIGEST_ENABLED','true');assert digest.deliver_digest(SUMMARY,NOW.replace(hour=6))['status']=='waiting_for_window'
 db.rpc.assert_not_called();sender.send.assert_not_called()

def test_digest_uses_reserved_snapshot_not_changed_caller_body(setup):
 db,sender=setup
 caller={**SUMMARY,'new_leads':999}
 result=digest.deliver_digest(caller,NOW)
 args,kwargs=sender.send.call_args
 assert 'New leads: 7' in args[2] and '999' not in args[2]
 assert 'blocked' in args[2] and 'Login required' in args[2]
 assert kwargs['message_id']==result['message_id']
 assert result['digests'][0]['delivered_at'] is None

@pytest.mark.parametrize('key,value',[('message_id','wrong'),('recipient','other@example.test'),('day','2000-01-01'),('send_allowed','true'),('summary',None)])
def test_bad_reservation_ack_never_sends(setup,key,value):
 db,sender=setup;original=db.rpc.side_effect
 def rpc(name,params):
  response=original(name,params);data=response.execute().data;data[key]=value
  return SimpleNamespace(execute=lambda:SimpleNamespace(data=data))
 db.rpc.side_effect=rpc
 with pytest.raises(RuntimeError,match='not confirmed'):digest.deliver_digest(SUMMARY,NOW)
 sender.send.assert_not_called()

def test_lost_ack_never_sends_and_retry_reuses_same_id(setup):
 db,sender=setup;original=db.rpc.side_effect;ids=[]
 def rpc(name,params):
  if name=='reserve_list_digest':
   ids.append(params['p_message'])
   if len(ids)==1:raise RuntimeError('lost acknowledgement')
  return original(name,params)
 db.rpc.side_effect=rpc
 with pytest.raises(RuntimeError):digest.deliver_digest(SUMMARY,NOW)
 sender.send.assert_not_called();digest.deliver_digest(SUMMARY,NOW)
 assert ids[0]==ids[1];sender.send.assert_called_once()

def test_existing_attempt_is_reconciled_without_resend(setup):
 db,sender=setup;original=db.rpc.side_effect
 def rpc(name,params):
  data=original(name,params).execute().data
  if name=='reserve_list_digest':data['send_allowed']=False
  return SimpleNamespace(execute=lambda:SimpleNamespace(data=data))
 db.rpc.side_effect=rpc;digest.deliver_digest(SUMMARY,NOW)
 sender.send.assert_not_called();assert db.rpc.call_args.args[0]=='reconcile_list_digests'

def test_uncertain_send_is_reconciled_without_new_message_id(setup):
 db,sender=setup;sender.send.return_value=False
 result=digest.deliver_digest(SUMMARY,NOW)
 assert result['digests'][0]['delivered_at'] is None
 assert db.rpc.call_args.args[0]=='reconcile_list_digests'

def test_stale_summary_day_cannot_send(setup):
 db,sender=setup
 with pytest.raises(RuntimeError,match='Central date'):digest.deliver_digest({**SUMMARY,'day':'2026-10-11'},NOW)
 db.rpc.assert_not_called();sender.send.assert_not_called()

def test_missing_owner_email_still_reconciles_deadline_alerts(setup,monkeypatch):
 db,sender=setup;monkeypatch.setattr(digest.settings,'notification_email','')
 assert digest.deliver_digest(SUMMARY,NOW)['status']=='owner_email_not_configured'
 db.rpc.assert_called_once_with('reconcile_list_digests',{});sender.send.assert_not_called()
