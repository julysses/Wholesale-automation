from unittest.mock import MagicMock
import pytest
from config.settings import settings
from tools.email_client import EmailClient


@pytest.fixture(autouse=True)
def email_gate(monkeypatch):
    monkeypatch.setattr(settings, 'email_live_enabled', True)
    monkeypatch.setattr(settings, 'email_allowed_recipients', '')


@pytest.mark.parametrize('key,sender', [('', 'owner@example.com'), ('test-key', '')])
def test_unconfigured_email_cannot_report_delivery(monkeypatch, key, sender):
    monkeypatch.setattr(settings,'sendgrid_api_key',key)
    monkeypatch.setattr(settings,'from_email',sender)
    client=EmailClient('sendgrid')
    dispatch=MagicMock()
    monkeypatch.setattr(client,'_dispatch',dispatch)
    assert client.send('fixture@example.com','Fixture','Test') is False
    dispatch.assert_not_called()


@pytest.mark.parametrize('enabled,allowlist,recipient,expected', [
    (False, '', 'fixture@example.com', False),
    (False, 'fixture@example.com', 'fixture@example.com', False),
    (True, 'fixture@example.com', 'seller@example.com', False),
    (True, 'fixture@example.com', 'fixture@example.com.evil.test', False),
    (True, ' , ', 'fixture@example.com', False),
    (True, 'fixture@example.com', ' FIXTURE@EXAMPLE.COM ', True),
    (True, '', 'fixture@example.com', True),
])
def test_launch_gate_prevents_provider_calls(monkeypatch, enabled, allowlist, recipient, expected):
    monkeypatch.setattr(settings, 'sendgrid_api_key', 'test-key')
    monkeypatch.setattr(settings, 'from_email', 'owner@example.com')
    monkeypatch.setattr(settings, 'email_live_enabled', enabled)
    monkeypatch.setattr(settings, 'email_allowed_recipients', allowlist)
    client = EmailClient('sendgrid')
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(client, '_dispatch', dispatch)
    assert client.send(recipient, 'Fixture', 'Test') is expected
    assert dispatch.call_count == int(expected)


def test_email_reports_provider_rejection(monkeypatch):
    monkeypatch.setattr(settings,'sendgrid_api_key','test-key')
    monkeypatch.setattr(settings,'from_email','owner@example.com')
    client=EmailClient('sendgrid')
    monkeypatch.setattr(client,'_dispatch',lambda *_: False)
    assert client.send('fixture@example.com','Fixture','Test') is False
