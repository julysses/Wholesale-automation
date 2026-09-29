from unittest.mock import MagicMock
import pytest
from config.settings import settings
from tools.email_client import EmailClient


@pytest.mark.parametrize('key,sender', [('', 'owner@example.com'), ('test-key', '')])
def test_unconfigured_email_cannot_report_delivery(monkeypatch, key, sender):
    monkeypatch.setattr(settings,'sendgrid_api_key',key)
    monkeypatch.setattr(settings,'from_email',sender)
    client=EmailClient('sendgrid')
    dispatch=MagicMock()
    monkeypatch.setattr(client,'_dispatch',dispatch)
    assert client.send('fixture@example.com','Fixture','Test') is False
    dispatch.assert_not_called()


def test_email_reports_provider_rejection(monkeypatch):
    monkeypatch.setattr(settings,'sendgrid_api_key','test-key')
    monkeypatch.setattr(settings,'from_email','owner@example.com')
    client=EmailClient('sendgrid')
    monkeypatch.setattr(client,'_dispatch',lambda *_: False)
    assert client.send('fixture@example.com','Fixture','Test') is False
