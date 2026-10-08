"""Controlled unsubscribe testing must preserve owner alerts and the allowlist."""
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from web.api import email_api


@pytest.fixture
def delivery(monkeypatch):
    monkeypatch.setattr(email_api.settings,'email_live_enabled',True)
    monkeypatch.setattr(email_api.settings,'email_allowed_recipients','owner@example.com, secondary@example.com')
    monkeypatch.setattr(email_api.settings,'notification_email','owner@example.com')
    client=MagicMock()
    client.send.return_value=True
    factory=MagicMock(return_value=client)
    monkeypatch.setattr(email_api,'EmailClient',factory)
    return factory,client


def test_multiple_recipients_default_to_owner(delivery):
    _,client=delivery
    ref=uuid4()
    assert email_api.send_test(ref)['recipient']=='owner@example.com'
    assert client.send.call_args.args[0]=='owner@example.com'
    assert client.send.call_args.kwargs['message_id']==str(ref)


def test_secondary_selected_without_changing_owner(delivery):
    _,client=delivery
    assert email_api.send_test(uuid4(),' SECONDARY@EXAMPLE.COM ')['provider_accepted']
    assert client.send.call_args.args[0]=='secondary@example.com'
    assert email_api.settings.notification_email=='owner@example.com'


@pytest.mark.parametrize('recipient',['seller@example.com','owner@example.com.evil.test',''])
def test_unlisted_recipient_never_constructs_provider(delivery,recipient):
    factory,_=delivery
    with pytest.raises(HTTPException) as error:
        email_api.send_test(uuid4(),recipient)
    assert error.value.status_code==403
    factory.assert_not_called()


@pytest.mark.parametrize('enabled,allowlist,owner',[
    (False,'owner@example.com','owner@example.com'),
    (True,'','owner@example.com'),
    (True,' , ','owner@example.com'),
    (True,'one@example.com,two@example.com','owner@example.com'),
])
def test_unconfigured_or_ambiguous_default_refused(delivery,monkeypatch,enabled,allowlist,owner):
    factory,_=delivery
    monkeypatch.setattr(email_api.settings,'email_live_enabled',enabled)
    monkeypatch.setattr(email_api.settings,'email_allowed_recipients',allowlist)
    monkeypatch.setattr(email_api.settings,'notification_email',owner)
    with pytest.raises(HTTPException) as error:
        email_api.send_test(uuid4())
    assert error.value.status_code==409
    factory.assert_not_called()


def test_original_single_recipient_remains_supported(delivery,monkeypatch):
    monkeypatch.setattr(email_api.settings,'email_allowed_recipients','single@example.com')
    assert email_api.send_test(uuid4())['recipient']=='single@example.com'
