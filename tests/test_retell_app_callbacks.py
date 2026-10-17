from unittest.mock import Mock
import pytest
from tests.test_twilio_integration import setup, signed, SENDER
from tests.test_twilio_receipt_reconciliation import DB, PHONE, SID
from tools.twilio_receipts import reconcile_twilio_callback
from web.api import twilio_webhooks as hooks

@pytest.mark.parametrize('status',['queued','delivered','undelivered'])
def test_signed_app_callback_updates_operational_state_even_when_sending_paused(setup,monkeypatch,status):
    client,_=setup;db=DB('submitting');db.rows[0]['raw_payload']={'transport':'app_twilio'}
    monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',reconcile_twilio_callback)
    sync=Mock();monkeypatch.setattr(hooks,'sync_app_outcome',sync)
    monkeypatch.setattr(hooks,'record_provider_alert',Mock())
    data={'AccountSid':'AC'+'a'*32,'MessageSid':SID,'From':SENDER,'To':PHONE,'MessageStatus':status}
    assert hooks.settings.sms_live_enabled is False
    assert signed(client,'status',data,'?message_id='+db.reference).status_code==200
    sync.assert_called_once_with(db,db.reference)
    assert db.rows[0]['status']==status

def test_sync_failure_keeps_verified_receipt_and_requests_callback_retry(setup,monkeypatch):
    client,_=setup;db=DB('submitting');db.rows[0]['raw_payload']={'transport':'app_twilio'}
    monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',reconcile_twilio_callback)
    sync=Mock(side_effect=RuntimeError('temporary DB failure'));monkeypatch.setattr(hooks,'sync_app_outcome',sync)
    data={'AccountSid':'AC'+'a'*32,'MessageSid':SID,'From':SENDER,'To':PHONE,'MessageStatus':'delivered'}
    assert signed(client,'status',data,'?message_id='+db.reference).status_code==503
    assert db.rows[0]['status']=='delivered'
    sync.side_effect=None
    assert signed(client,'status',data,'?message_id='+db.reference).status_code==200
    assert db.rows[0]['status']=='delivered'

def test_unrelated_twilio_receipt_does_not_require_new_app_transport_schema(setup,monkeypatch):
    client,_=setup;db=DB('submitting');monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',reconcile_twilio_callback)
    sync=Mock();monkeypatch.setattr(hooks,'sync_app_outcome',sync)
    data={'AccountSid':'AC'+'a'*32,'MessageSid':SID,'From':SENDER,'To':PHONE,'MessageStatus':'delivered'}
    assert signed(client,'status',data,'?message_id='+db.reference).status_code==200
    sync.assert_not_called()
