"""Durable, finite form-to-Retell SMS handoff. All activation flags default off."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import re
from uuid import NAMESPACE_URL, uuid5
import requests
from tools.facebook_consent import normalize_us_phone
from tools.sms_client import sms_consent_blocker, SMSClient, CONFIRMED_SUPPRESSION
from config.settings import settings


def enabled(name):
    return os.getenv(name, '').lower() == 'true'


def acknowledgement_window(submitted):
    """Keep new inbound inquiries within configured Central-time contact hours.

    Use the original receipt clock, never the retry clock. This does not renew
    old jobs or change the existing seller-initiated weekend policy.
    """
    start, end = settings.tcpa_allowed_start_hour, settings.tcpa_allowed_end_hour
    if submitted.tzinfo is None or not 0 <= start < end <= 24:
        raise ValueError('Invalid contact window')
    local = (submitted.astimezone(timezone.utc) + timedelta(seconds=60)).astimezone(ZoneInfo('America/Chicago'))
    deferred = not start <= local.hour < end
    if deferred:
        day = local.date() + timedelta(days=int(local.hour >= end))
        due = datetime.combine(day, time(start), tzinfo=ZoneInfo('America/Chicago')).astimezone(timezone.utc)
        expires = due + timedelta(minutes=15)
    else:
        due = local.astimezone(timezone.utc)
        expires = submitted.astimezone(timezone.utc) + timedelta(minutes=15)
    return due, expires, deferred


def enqueue(sb, lead_id):
    if not enabled('RETELL_FORM_SMS_ENABLED'):
        return 'disabled'
    receipts = sb.table('lead_form_submissions').select('id,created_at,raw_answers').eq('lead_id', lead_id).order('created_at', desc=True).limit(1).execute().data or []
    if not receipts:
        return 'no_form_receipt'
    receipt = receipts[0]
    try:
        phone = normalize_us_phone(receipt['raw_answers'].get('phone'))
        submitted = datetime.fromisoformat(receipt['created_at'].replace('Z', '+00:00'))
        if submitted.tzinfo is None:
            return 'invalid_submission_time'
    except (ValueError, TypeError, KeyError):
        return 'invalid_form_receipt'
    blocker = sms_consent_blocker(sb, lead_id, phone)
    if blocker:
        # A verified suppression is an intentional no-send outcome. Lookup
        # uncertainty and unmatched consent still require operator review.
        return 'confirmed_suppression' if blocker == CONFIRMED_SUPPRESSION else 'consent_or_suppression_hold'
    try:
        due, expires, deferred = acknowledgement_window(submitted)
    except ValueError:
        return 'contact_window_not_configured'
    job_id = str(uuid5(NAMESPACE_URL, 'wholesaleos:retell-form-sms:' + receipt['id']))
    row = {'id': job_id, 'lead_id': lead_id, 'submission_id': receipt['id'], 'phone_number': phone,
           'due_at': due.isoformat(), 'expires_at': expires.isoformat()}
    saved = sb.table('retell_form_sms_jobs').upsert(row, on_conflict='id', ignore_duplicates=True).execute().data
    if not saved and not sb.table('retell_form_sms_jobs').select('id').eq('id', job_id).execute().data:
        raise RuntimeError('Retell form schedule was not confirmed')
    return 'scheduled_retell_next_contact_window' if deferred else 'scheduled_retell_60_seconds'


def configured_version():
    value = os.getenv('RETELL_SMS_AGENT_VERSION', '')
    if re.fullmatch(r'0|[1-9][0-9]{0,8}', value):
        return int(value)
    # Require a pinned numeric release for controlled production acceptance.
    return None


def activation_ready():
    return (enabled('RETELL_FORM_SMS_ENABLED') and enabled('RETELL_SMS_LIVE_ENABLED')
            and settings.sms_live_enabled
            and (enabled('RETELL_SMS_ACCEPTANCE_VERIFIED') or enabled('RETELL_SMS_LAUNCH_APPROVED'))
            and bool(os.getenv('RETELL_SMS_AGENT_ID')) and configured_version() is not None
            and bool(os.getenv('RETELL_SMS_API_KEY')) and bool(os.getenv('RETELL_SMS_FROM_NUMBER'))
            and bool(os.getenv('RETELL_SMS_SENDER_NAME'))
            and (enabled('RETELL_SMS_ALL_CONSENTED_FORMS') or bool(settings.sms_allowed_recipients)))


def drain(sb):
    if not activation_ready():
        return {'processed': 0, 'sending_enabled': False}
    sms = SMSClient()
    if not sms._in_allowed_hours():
        return {'processed': 0, 'deferred': 'outside_contact_hours'}
    # Never replay an uncertain provider operation, including a process crash.
    sb.table('retell_form_sms_jobs').update({'status': 'review', 'reason': 'Worker outcome unconfirmed; reconcile before retry'}).eq('status', 'processing').lt('claimed_at', (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()).execute()
    jobs = sb.rpc('claim_retell_form_sms', {'p_limit': 3}).execute().data
    if not isinstance(jobs, list):
        raise RuntimeError('Retell SMS claims not confirmed')
    for job in jobs:
        process_claim(sb, job)
    return {'processed': len(jobs), 'sending_enabled': True}


def finish(sb, job, status, reason, chat_id=None):
    saved = sb.table('retell_form_sms_jobs').update({'status': status, 'reason': reason, 'chat_id': chat_id}).eq('id', job['id']).eq('status', 'processing').execute().data
    if not saved:
        raise RuntimeError('Retell SMS outcome not confirmed; do not retry sending')
    saved = sb.table('sms_events').update({'status': {'review': 'unknown', 'stopped': 'blocked'}.get(status, status), 'raw_payload': {'chat_id': chat_id, 'reason': reason}}).eq('id', job['id']).execute().data
    if not saved:
        raise RuntimeError('Retell SMS ledger not confirmed')


def process_claim(sb, job):
    # Recheck immediately before the provider request; no fallback to Twilio.
    if not activation_ready():
        finish(sb, job, 'stopped', 'Sending disabled')
        return
    allowed = {p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()}
    leads = sb.table('leads').select('*').eq('id', job['lead_id']).limit(1).execute().data or []
    lead = leads[0] if leads else {}
    blocker = sms_consent_blocker(sb, job['lead_id'], job['phone_number'])
    try:
        same_phone = normalize_us_phone(lead.get('owner_phone_1')) == job['phone_number']
    except ValueError:
        same_phone = False
    if ((not enabled('RETELL_SMS_ALL_CONSENTED_FORMS') and job['phone_number'] not in allowed)
        or not same_phone or blocker
        or lead.get('dnc') is not False or lead.get('status') in {'dnc','dead','closed','sold','under_contract'}):
        finish(sb, job, 'stopped', 'Recipient, consent, or suppression check blocked dispatch')
        return
    first_name = str(lead.get('owner_first_name') or '').strip()
    street = str(lead.get('property_address') or '').strip()
    if not first_name or not street:
        finish(sb, job, 'stopped', 'Missing form name or property address')
        return
    # Earlier jobs in the same batch can take time. Recheck the deadline and
    # contact window at the actual handoff, not only when the batch was claimed.
    try:
        due = datetime.fromisoformat(job['due_at'].replace('Z', '+00:00'))
        expires = datetime.fromisoformat(job['expires_at'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        within_deadline = due <= now < expires
    except (KeyError, TypeError, ValueError):
        within_deadline = False
    if not within_deadline or not SMSClient()._in_allowed_hours():
        finish(sb, job, 'stopped', 'Dispatch deadline or contact hours no longer valid')
        return
    payload = {'from_number': os.environ['RETELL_SMS_FROM_NUMBER'], 'to_number': job['phone_number'],
               'override_agent_id': os.environ['RETELL_SMS_AGENT_ID'],
               'override_agent_version': configured_version(),
               'honor_internal_dnc': True,
               'metadata': {'lead_id': job['lead_id'], 'submission_id': job['submission_id'], 'sms_job_id': job['id']},
               'retell_llm_dynamic_variables': {'first_name': first_name, 'street_address': street,
                                               'sender_name': os.environ['RETELL_SMS_SENDER_NAME']}}
    try:
        response = requests.post('https://api.retellai.com/create-sms-chat', json=payload,
                                 headers={'Authorization': 'Bearer ' + os.environ['RETELL_SMS_API_KEY']}, timeout=15)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not result.get('chat_id'):
            raise ValueError('Missing chat receipt')
    except Exception:
        finish(sb, job, 'review', 'Provider outcome uncertain; reconcile before retry')
        return
    finish(sb, job, 'accepted', 'Retell accepted; delivery not yet confirmed', result['chat_id'])


def check_connection():
    """Read the configured published release; return only redacted readiness checks."""
    key = os.getenv('RETELL_SMS_API_KEY', '')
    if not key:
        return {'connected': False, 'reason': 'credential_missing', 'dispatch_authorized': False}
    agent_id = os.getenv('RETELL_SMS_AGENT_ID', '')
    version = configured_version()
    if not re.fullmatch(r'agent_[A-Za-z0-9]+', agent_id) or version is None:
        return {'connected': False, 'reason': 'pinned_agent_missing', 'dispatch_authorized': False}
    try:
        response = requests.get('https://api.retellai.com/get-chat-agent/' + agent_id,
            headers={'Authorization': 'Bearer ' + key}, params={'version': version},
            timeout=15, allow_redirects=False)
        if response.status_code != 200:
            return {'connected': False, 'provider_status': response.status_code, 'dispatch_authorized': False}
        data = response.json()
        checks = {'agent_matches': data.get('agent_id') == agent_id,
                  'version_matches': data.get('version') == version,
                  'published': data.get('is_published') is True,
                  'callback_matches': data.get('webhook_url') ==
                      'https://wholesale-automation.vercel.app/webhooks/retell'}
        return {'connected': all(checks.values()), 'checks': checks,
                'dispatch_authorized': False}
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return {'connected': False, 'reason': 'provider_check_failed', 'dispatch_authorized': False}
