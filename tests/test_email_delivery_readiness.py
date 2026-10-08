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
    monkeypatch.setattr(client, '_claim', lambda *_: True)
    monkeypatch.setattr('tools.crm.get_supabase_client', lambda: MagicMock())
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(client, '_dispatch', dispatch)
    assert client.send(recipient, 'Fixture', 'Test') is expected
    assert dispatch.call_count == int(expected)


def test_email_reports_provider_rejection(monkeypatch):
    monkeypatch.setattr(settings,'sendgrid_api_key','test-key')
    monkeypatch.setattr(settings,'from_email','owner@example.com')
    client=EmailClient('sendgrid')
    monkeypatch.setattr(client,'_claim',lambda *_: True)
    monkeypatch.setattr('tools.crm.get_supabase_client',lambda:MagicMock())
    monkeypatch.setattr(client,'_dispatch',lambda *_: False)
    assert client.send('fixture@example.com','Fixture','Test') is False


@pytest.mark.parametrize('result', [None, {}, {'claimed':False,'suppressed':True}, {'claimed':False,'suppressed':False}])
def test_failed_or_duplicate_claim_blocks_provider(monkeypatch,result):
    monkeypatch.setattr(settings,'sendgrid_api_key','test-key')
    monkeypatch.setattr(settings,'from_email','owner@example.com')
    sb=MagicMock()
    sb.rpc.return_value.execute.return_value.data=result
    monkeypatch.setattr('tools.crm.get_supabase_client',lambda:sb)
    client=EmailClient('sendgrid')
    dispatch=MagicMock()
    monkeypatch.setattr(client,'_dispatch',dispatch)
    assert client.send('fixture@example.com','Fixture','Test') is False
    dispatch.assert_not_called()


def test_unknown_email_outcome_creates_in_app_alert_without_another_send(monkeypatch):
    from tests.test_webhook_completion_delivery import MemoryDB
    from tools import operational_alerts
    monkeypatch.setattr(settings,'sendgrid_api_key','test-key')
    monkeypatch.setattr(settings,'from_email','owner@example.com')
    db=MemoryDB(); monkeypatch.setattr('tools.crm.get_supabase_client',lambda:db)
    client=EmailClient('sendgrid')
    monkeypatch.setattr(client,'_claim',lambda *_:True)
    dispatch=MagicMock(return_value=False); monkeypatch.setattr(client,'_dispatch',dispatch)
    assert client.send('fixture@example.com','Fixture','Test') is False
    dispatch.assert_called_once()
    notice=next(iter(db.tables['app_notifications'].values()))
    assert notice['metadata']['provider']=='sendgrid'
    assert notice['metadata']['status']=='unknown'
