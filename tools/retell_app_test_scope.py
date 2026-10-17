"""Owner-test limits shared by selection and each exact provider worker."""
from datetime import datetime, timedelta, timezone
import os
import re
from uuid import UUID

from config.settings import settings
from tools.retell_form_sms import enabled


def test_selected():
    return 'RETELL_APP_AUTOMATION_TEST_JOB_ID' in os.environ


def test_window(now=None):
    """Invalid or expired explicit test mode never falls back to production."""
    if not test_selected() or not enabled('RETELL_APP_TEST_APPROVED'):
        return None
    try:
        job = str(UUID(os.environ['RETELL_APP_AUTOMATION_TEST_JOB_ID']))
        start = datetime.fromisoformat(os.getenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT', '').replace('Z', '+00:00'))
        end = datetime.fromisoformat(os.getenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', '').replace('Z', '+00:00'))
        now = now or datetime.now(timezone.utc)
        phones = [p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()]
        if (not phones or any(not re.fullmatch(r'\+1\d{10}', p) for p in phones)
                or start.tzinfo is None or end.tzinfo is None or now.tzinfo is None
                or not start <= now < end or not timedelta(0) < end-start <= timedelta(minutes=30)):
            return None
        return {'job': job, 'expires': end, 'phones': phones}
    except (ValueError, TypeError):
        return None


def launch_allowed():
    if test_selected():
        return test_window() is not None
    return enabled('RETELL_APP_ACCEPTANCE_VERIFIED')


def operation_allowed(sb, job_id, phone, turn_id=None):
    """Recheck exact job and first persisted turn even for direct worker calls."""
    if not test_selected():
        return True  # Normal readiness still requires verified production acceptance.
    window = test_window()
    if window is None or job_id != window['job'] or phone not in window['phones']:
        return False
    if turn_id is not None:
        rows = (sb.table('retell_api_turns').select('id').eq('session_id', job_id)
                .order('created_at').order('id').limit(1).execute().data)
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get('id') != turn_id:
            return False
    # The lookup can cross the deadline; never reuse the earlier time decision.
    return test_window() == window
