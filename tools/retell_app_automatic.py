"""One bounded automatic queue step. Sending and automation default off."""
import re
from uuid import UUID

from config.settings import settings
from tools.retell_form_sms import enabled
from tools.retell_api_turns import process_turn, all_consented_forms
from tools.retell_app_dispatch import dispatch_ready, process_ack, process_reply
from tools.sms_client import SMSClient
from tools.retell_app_test_scope import test_selected, test_window


def scope():
    if not enabled('RETELL_APP_AUTOMATION_ENABLED') or not dispatch_ready():
        return None
    phones = [p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()]
    if any(not re.fullmatch(r'\+1\d{10}', p) for p in phones):
        return None
    # Test mode is explicitly selected by the presence of a target; an invalid
    # or expired target must never fall back to all production inquiries.
    if test_selected():
        window = test_window()
        if window is None:
            return None
        return {'p_job': window['job'], 'p_first_turn_only': True, 'p_phones': window['phones']}
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
