"""One bounded automatic queue step. Sending and automation default off."""
from datetime import datetime, timezone, timedelta
import os
import re
from uuid import UUID

from config.settings import settings
from tools.retell_form_sms import enabled
from tools.retell_api_turns import process_turn, all_consented_forms
from tools.retell_app_dispatch import dispatch_ready, process_ack, process_reply
from tools.sms_client import SMSClient


def scope():
    if not enabled('RETELL_APP_AUTOMATION_ENABLED') or not dispatch_ready():
        return None
    phones = [p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()]
    if any(not re.fullmatch(r'\+1\d{10}', p) for p in phones):
        return None
    # Test mode is explicitly selected by the presence of a target; an invalid
    # or expired target must never fall back to all production inquiries.
    target = os.getenv('RETELL_APP_AUTOMATION_TEST_JOB_ID')
    if target is not None:
        if not enabled('RETELL_APP_TEST_APPROVED') or not phones:
            return None
        try:
            target = str(UUID(target))
            started = datetime.fromisoformat(os.getenv('RETELL_APP_AUTOMATION_TEST_STARTED_AT', '').replace('Z', '+00:00'))
            expiry = datetime.fromisoformat(os.getenv('RETELL_APP_AUTOMATION_TEST_EXPIRES_AT', '').replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (started.tzinfo is None or expiry.tzinfo is None
                    or not started <= now < expiry or not timedelta(0) < expiry-started <= timedelta(minutes=30)):
                return None
        except (ValueError, TypeError):
            return None
        # Only the first actual carrier turn qualifies: maximum one acknowledgment,
        # one creation/completion, and one conversational reply; no retries.
        return {'p_job': target, 'p_first_turn_only': True, 'p_phones': phones}
    if not enabled('RETELL_APP_ACCEPTANCE_VERIFIED'):
        return None
    if not all_consented_forms() and not phones:
        return None
    return {'p_job': None, 'p_first_turn_only': False,
            'p_phones': None if all_consented_forms() else phones}


def step(sb):
    selected_scope = scope()
    if selected_scope is None:
        return {'status': 'disabled', 'processed': 0, 'dispatch_authorized': False}
    if not SMSClient()._in_allowed_hours():
        return {'status': 'deferred', 'processed': 0, 'dispatch_authorized': False}
    selected = sb.rpc('pick_retell_app_work', selected_scope).execute().data
    if not isinstance(selected, dict) or type(selected.get('selected')) is not bool:
        raise RuntimeError('Automatic queue selection unconfirmed')
    if not selected['selected']:
        return {'status': 'idle', 'processed': 0, 'dispatch_authorized': False}
    action = selected.get('action')
    reference = str(UUID(str(selected.get('reference'))))
    job = str(UUID(str(selected.get('job_id'))))
    if (action not in {'ack', 'generate', 'reply'} or (action == 'ack' and reference != job)
            or (selected_scope['p_job'] is not None and job != selected_scope['p_job'])):
        raise RuntimeError('Automatic queue selection identity mismatch')
    # The selection lease is not a provider claim or authority to send. Recheck
    # mode/expiry after selection and use the existing exact worker/SQL claims.
    if scope() != selected_scope:
        return {'status': 'disabled', 'processed': 0, 'dispatch_authorized': False}
    worker = {'ack': process_ack, 'generate': process_turn, 'reply': process_reply}[action]
    outcome = worker(sb, reference)
    return {'status': 'processed', 'processed': 1, 'action': action,
            'reference': reference, 'outcome': outcome}
