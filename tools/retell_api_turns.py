"""One-shot generation worker for app-owned SMS replies; no delivery capability.

Mounted only on an authenticated exact-turn endpoint. Durable RPCs own claims; all
provider ambiguity stays held. Dispatch must use a separate verified outbox.
"""
from datetime import datetime, timezone
import os
from uuid import UUID

from config.settings import settings
from tools.facebook_consent import normalize_us_phone
from tools.retell_form_sms import configured_version, enabled
from tools.retell_api_chat import RetellAPIChat
from tools.sms_client import SMSClient, sms_consent_blocker
from tools.sms_controls import is_control


def all_consented_forms():
    return enabled('RETELL_APP_ACCEPTANCE_VERIFIED') and enabled('RETELL_APP_ALL_CONSENTED_FORMS')


def recipient_allowed(phone):
    allowed = {p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()}
    return phone in allowed or all_consented_forms()


def ready():
    return (enabled('RETELL_APP_TRANSPORT_ENABLED') and os.getenv('RETELL_SMS_TRANSPORT') == 'app_twilio'
            and enabled('RETELL_FORM_SMS_ENABLED') and enabled('RETELL_SMS_LIVE_ENABLED')
            and settings.sms_live_enabled
            and (enabled('RETELL_APP_ACCEPTANCE_VERIFIED') or enabled('RETELL_APP_TEST_APPROVED'))
            and (bool(settings.sms_allowed_recipients) or all_consented_forms()) and configured_version() is not None
            and bool(os.getenv('RETELL_SMS_AGENT_ID')) and bool(os.getenv('RETELL_SMS_API_KEY')))


def _row(sb, table, identity):
    rows = sb.table(table).select('*').eq('id', identity).limit(1).execute().data
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get('id') != identity:
        raise RuntimeError('Generation context is missing or ambiguous')
    return rows[0]


def _eligible(sb, turn, session):
    if not ready() or not SMSClient()._in_allowed_hours():
        return False
    if not recipient_allowed(session.get('phone_number')) or session.get('sender_number') != settings.twilio_from_number:
        return False
    current = _row(sb, 'retell_api_sessions', session['id'])
    inquiry = _row(sb, 'retell_form_sms_jobs', session['id'])
    if (current.get('status') not in {'pending', 'creating', 'ready'}
            or inquiry.get('status') != 'accepted' or inquiry.get('delivery_transport') != 'app_twilio'):
        return False
    try:
        expires = datetime.fromisoformat(turn['expires_at'].replace('Z', '+00:00'))
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            return False
        lead = _row(sb, 'leads', session['lead_id'])
        same_phone = normalize_us_phone(lead.get('owner_phone_1')) == session['phone_number']
    except (ValueError, KeyError, TypeError):
        return False
    return (same_phone and lead.get('dnc') is False
            and lead.get('status') not in {'dnc','dead','closed','sold','under_contract'}
            and not is_control({'Body': turn.get('recipient_text')})
            and not sms_consent_blocker(sb, session['lead_id'], session['phone_number']))


def _hold(sb, turn_id, expected, reason):
    result = sb.rpc('hold_retell_api_turn', {'p_turn': turn_id, 'p_expected': expected,
                                           'p_reason': reason}).execute().data
    return {'status': 'review' if isinstance(result, dict) and result.get('held') is True else 'hold_unconfirmed',
            'dispatch_authorized': False}


def process_turn(sb, turn_id):
    """Process exactly one queued carrier reply; never reclaim uncertain work."""
    target = str(UUID(str(turn_id)))
    if not ready():
        return {'status': 'disabled', 'dispatch_authorized': False}
    turn = _row(sb, 'retell_api_turns', target)
    session = _row(sb, 'retell_api_sessions', turn['session_id'])
    if turn.get('status') != 'queued' or not _eligible(sb, turn, session):
        return {'status': 'not_eligible', 'dispatch_authorized': False}
    agent, version = os.environ['RETELL_SMS_AGENT_ID'], configured_version()
    # Validate configuration before consuming the durable claim.
    provider = RetellAPIChat(os.environ['RETELL_SMS_API_KEY'], agent, version)
    claim = sb.rpc('claim_retell_api_turn', {'p_turn': target,'p_agent': agent,'p_version': version}).execute().data
    if not isinstance(claim, dict):
        raise RuntimeError('Generation claim unconfirmed; do not call provider')
    if claim.get('claimed') is not True:
        return {'status': 'not_claimed', 'dispatch_authorized': False}
    stage = 'creating_session' if claim.get('create_session') is True else 'generating'
    if (claim.get('turn_id') != target or claim.get('session_id') != session['id']
        or claim.get('lead_id') != session['lead_id'] or claim.get('recipient_text') != turn['recipient_text']
        or type(claim.get('create_session')) is not bool):
        return _hold(sb, target, stage, 'Generation claim identity mismatch; no provider call')
    try:
        if not _eligible(sb, turn, session):
            return _hold(sb, target, stage, 'Consent or dispatch window changed before generation')
        if claim['create_session']:
            chat_id = provider.create(session['id'], session['lead_id'])
            result = sb.rpc('bind_retell_api_session', {'p_turn': target,'p_chat': chat_id}).execute().data
            # A replayed binding is evidence to reconcile, not permission to
            # repeat a completion that another invocation might have submitted.
            if not isinstance(result, dict) or result.get('bound') is not True or result.get('replayed') is not False:
                return _hold(sb, target, stage, 'Session binding unconfirmed; do not recreate or complete')
            stage = 'generating'
        else:
            chat_id = claim.get('chat_id')
        if not _eligible(sb, turn, session):
            return _hold(sb, target, stage, 'Consent or dispatch window changed before completion')
        generated = provider.complete(chat_id, turn['recipient_text'], session['id'], session['lead_id'])
        messages = [{'message_id': m.message_id, 'content': m.content} for m in generated]
        saved = sb.rpc('save_retell_api_generation', {'p_turn': target,'p_messages': messages}).execute().data
        if not isinstance(saved, dict) or saved.get('saved') is not True:
            return _hold(sb, target, stage, 'Generation persistence unconfirmed; do not regenerate')
        return {'status': 'generated', 'message_count': len(messages), 'dispatch_authorized': False}
    except Exception:
        # No provider response, message text or credentials are exposed here.
        # Holding may itself fail; the already claimed state still blocks replay.
        return _hold(sb, target, stage, 'Provider or persistence outcome requires review; no automatic retry')
