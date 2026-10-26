"""Pending policy cannot be bypassed via a legacy provider or worker path."""
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from tools.acquisition_transport import AcquisitionExecutionRequired, HOLD_REASON, legacy_transport_held


@pytest.fixture
def held(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED', 'true')
    def forbidden(*args, **kwargs):
        raise AssertionError('No provider or database call is authorized')
    monkeypatch.setattr('httpx.Client', forbidden)
    monkeypatch.setattr('requests.post', forbidden)
    db = Mock()
    db.table.side_effect = forbidden
    db.rpc.side_effect = forbidden
    return db


def test_sms_blocks_before_claim_and_direct_sdk_dispatch(held):
    from tools.sms_client import SMSClient
    from schemas.outreach import OutreachMessage, OutreachChannel
    message = OutreachMessage(lead_id=uuid4(),channel=OutreachChannel.SMS,body='Synthetic test',compliance_cleared=True)
    client = object.__new__(SMSClient)
    assert client.send(message, '+12145550101') is False
    assert message.sms_outcome == 'blocked'
    assert message.sms_reason == HOLD_REASON
    assert client._send_twilio(message, '+12145550101') is False


def test_email_public_and_provider_methods_cannot_bypass_gate(held):
    from tools.email_client import EmailClient
    client=object.__new__(EmailClient)
    for method in (client.send,client._send_sendgrid,client._send_mailgun):
        assert method('seller@example.test','Synthetic','Test only') is False


@pytest.mark.parametrize('module,name', [('tools.retell_adapter','RetellAdapter'),('tools.retell_adapter','AirAIAdapter'),
                                         ('tools.retell_adapter','AICallingAdapter'),('tools.vapi_adapter','VapiAdapter')])
def test_voice_adapters_block_before_request_validation_network_or_retry(held, module, name):
    import importlib
    adapter=getattr(importlib.import_module(module),name)
    with pytest.raises(AcquisitionExecutionRequired, match=HOLD_REASON):
        object.__new__(adapter).create_call(None)


def test_native_sms_claim_and_reply_redirect_are_held_without_database_writes(held):
    from tools import retell_form_sms as native
    from tools.retell_reply_routing import reply_redirect
    assert native.enqueue(held, str(uuid4())) == HOLD_REASON
    assert native.activation_ready() is False
    assert native.drain(held) == {'processed':0,'sending_enabled':False}
    with pytest.raises(AcquisitionExecutionRequired):
        native.process_claim(held,{})
    assert reply_redirect(held,{}, {}) is None


def test_app_workers_and_private_submit_do_not_claim_or_alter_held_jobs(held):
    from tools.retell_app_dispatch import dispatch_ready, process_ack, process_reply, _submit
    from tools.retell_app_automatic import step
    from tools.retell_api_turns import ready
    assert dispatch_ready() is False
    assert ready() is False
    assert process_ack(held,str(uuid4()))['dispatch_authorized'] is False
    assert process_reply(held,str(uuid4()))['dispatch_authorized'] is False
    assert step(held)['processed'] == 0
    with pytest.raises(AcquisitionExecutionRequired):
        _submit(held,{})


def test_voice_api_does_not_claim_request_or_advance_batch(held,monkeypatch):
    from web.api import calls_api
    monkeypatch.setattr(calls_api,'_storage',lambda: (_ for _ in ()).throw(AssertionError('No database access')))
    for function,args in ((calls_api.start_call,(None,'operator')), (calls_api.batch_next,(str(uuid4()),'operator'))):
        with pytest.raises(HTTPException) as error:
            function(*args)
        assert error.value.status_code == 409
        assert error.value.detail == HOLD_REASON


def test_flag_is_rechecked_for_existing_clients_and_no_user_payload_can_override(held,monkeypatch):
    from tools.acquisition_transport import require_legacy_transport_allowed
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert legacy_transport_held() is False
    require_legacy_transport_allowed()
    monkeypatch.setenv('ACQUISITION_ENABLED','TRUE')
    with pytest.raises(AcquisitionExecutionRequired):
        require_legacy_transport_allowed()
