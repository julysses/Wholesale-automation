from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from tools import retell_app_test_scope as scope

JOB = '00000000-0000-4000-8000-000000000001'
PHONE = '+12145550196'


def test_owner_approval_without_target_cannot_enable_exact_workers(monkeypatch):
    monkeypatch.setenv('RETELL_APP_TEST_APPROVED', 'true')
    monkeypatch.delenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', raising=False)
    monkeypatch.delenv('RETELL_APP_ACCEPTANCE_VERIFIED', raising=False)
    assert scope.launch_allowed() is False
    monkeypatch.setenv('RETELL_APP_ACCEPTANCE_VERIFIED', 'true')
    assert scope.launch_allowed() is True
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', '')
    assert scope.launch_allowed() is False


def test_slow_first_turn_lookup_cannot_reuse_expired_authority(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv('RETELL_APP_TEST_APPROVED', 'true')
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_JOB_ID', JOB)
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT', (now-timedelta(minutes=1)).isoformat())
    monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', (now+timedelta(minutes=14)).isoformat())
    monkeypatch.setattr(scope.settings, 'sms_allowed_recipients', PHONE)
    db = Mock()
    result = db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value
    def execute():
        monkeypatch.setenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', (now-timedelta(seconds=1)).isoformat())
        result.data = [{'id': JOB}]
        return result
    db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.limit.return_value.execute.side_effect = execute
    assert scope.operation_allowed(db, JOB, PHONE, JOB) is False
