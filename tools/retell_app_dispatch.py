"""App-owned Twilio outbox dispatch. No route or scheduler activates this module.

Only a freshly won durable initial/reply claim may call the provider, once.
Retell generates reply text separately; it never owns this SMS transport.
"""
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo
import re

from config.settings import settings
from tools.retell_api_turns import ready, _row
from tools.sms_client import SMSClient, sms_consent_blocker
from tools.facebook_consent import normalize_us_phone
from tools.twilio_receipts import reconcile_twilio_receipt, PROGRESS, FAILURES
from tools.operational_alerts import record_provider_alert

APP_ACKNOWLEDGMENT = ('Hilltop Home Co. (The Jays Dallas, LLC): Thanks for your property inquiry. '
                       'Julio will follow up. Reply STOP to opt out or HELP for help.')


def queue_validity(expires_at, now=None):
    """Bound Twilio's queue to 5 minutes and the remaining dispatch window.

    Ten seconds of handoff allowance; this cannot bound carrier-side latency.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return 0
    try:
        expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        start, end = settings.tcpa_allowed_start_hour, settings.tcpa_allowed_end_hour
        if expiry.tzinfo is None or not 0 <= start < end <= 24:
            return 0
        local = now.astimezone(ZoneInfo('America/Chicago'))
        if not start <= local.hour < end:
            return 0
        close = datetime.combine(local.date(), time(end % 24), tzinfo=local.tzinfo)
        if end == 24:
            close += timedelta(days=1)
        seconds = int((min(expiry, close.astimezone(timezone.utc)) - now).total_seconds()) - 10
        return min(300, seconds) if seconds > 5 else 0
    except (ValueError, TypeError, AttributeError):
        return 0


def dispatch_ready():
    base = urlsplit(settings.twilio_webhook_base_url)
    return (ready() and bool(settings.twilio_account_sid) and bool(settings.twilio_auth_token)
            and re.fullmatch(r'MG[0-9a-fA-F]{32}', settings.twilio_messaging_service_sid or '') is not None
            and base.scheme == 'https' and bool(base.hostname) and not base.username and not base.password
            and not base.query and not base.fragment and base.path in ('','/'))


def _eligible(sb, claim):
    if not dispatch_ready() or not SMSClient()._in_allowed_hours() or not queue_validity(claim.get('expires_at')):
        return False
    allowed = {p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()}
    if claim.get('phone_number') not in allowed or claim.get('sender_number') != settings.twilio_from_number:
        return False
    lead = _row(sb, 'leads', claim['lead_id'])
    try:
        matches = normalize_us_phone(lead.get('owner_phone_1')) == claim['phone_number']
    except (ValueError, TypeError):
        matches = False
    return (matches and lead.get('dnc') is False
            and lead.get('status') not in {'dnc','dead','closed','sold','under_contract'}
            and not sms_consent_blocker(sb, claim['lead_id'], claim['phone_number']))


def sync_outcome(sb, message_id):
    result = sb.rpc('sync_retell_app_outcome', {'p_message': message_id}).execute().data
    if not isinstance(result, dict) or result.get('synced') is not True:
        raise RuntimeError('App SMS outcome synchronization unconfirmed; do not resend')
    return result


def _park(sb, claim, status):
    sb.table('sms_events').update({'status': status}).eq('id', claim['message_id']).eq('status','submitting').execute()
    # A callback that won the race must survive a timeout or local block.
    receipt = sync_outcome(sb, claim['message_id'])
    if receipt.get('carrier_status') in FAILURES | {'unknown','blocked'}:
        record_provider_alert(sb, 'twilio', claim['message_id'], receipt['carrier_status'], claim['lead_id'])
    return {'status': receipt.get('carrier_status'), 'carrier_accepted': receipt.get('carrier_accepted') is True,
            'message_id': claim['message_id']}


def _submit(sb, claim):
    """Private: accepts only the new claim returned in this worker invocation."""
    message_id = str(UUID(str(claim['message_id'])))
    ledger = _row(sb, 'sms_events', message_id)
    metadata = ledger.get('raw_payload') or {}
    if (ledger.get('provider') != 'twilio' or ledger.get('direction') != 'outbound'
        or ledger.get('status') != 'submitting' or ledger.get('lead_id') != claim['lead_id']
        or ledger.get('phone_number') != claim['phone_number'] or ledger.get('body') != claim['body']
        or metadata.get('transport') != 'app_twilio' or metadata.get('sender_number') != claim['sender_number']
        or metadata.get('form_job_id') != claim['session_id']
        or metadata.get('api_turn_id') != claim.get('turn_id')):
        raise RuntimeError('App SMS durable claim mismatch; no provider call')
    if not _eligible(sb, claim):
        return _park(sb, claim, 'blocked')
    from twilio.rest import Client
    from twilio.http.http_client import TwilioHttpClient
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token,
                    http_client=TwilioHttpClient(timeout=5, max_retries=0))
    # Recheck the remaining finite window at the exact request boundary.
    validity = queue_validity(claim['expires_at'])
    if not dispatch_ready() or not validity:
        return _park(sb, claim, 'blocked')
    try:
        result = client.messages.create(body=claim['body'], from_=claim['sender_number'],
            messaging_service_sid=settings.twilio_messaging_service_sid, to=claim['phone_number'],
            status_callback=f"{settings.twilio_webhook_base_url.rstrip('/')}/webhooks/twilio/status?message_id={message_id}",
            validity_period=validity)
    except Exception:
        return _park(sb, claim, 'unknown')
    try:
        # Honor a known failure returned directly by Twilio, not just callbacks.
        status = getattr(result, 'status', None)
        status = status if status in PROGRESS.keys() | FAILURES else 'accepted'
        reconcile_twilio_receipt(sb, message_id, claim['phone_number'], result.sid, status)
        receipt = sync_outcome(sb, message_id)
        if receipt.get('carrier_status') in FAILURES | {'unknown'}:
            record_provider_alert(sb, 'twilio', message_id, receipt['carrier_status'], claim['lead_id'])
        return {'status': receipt.get('carrier_status'), 'carrier_accepted': receipt.get('carrier_accepted') is True,
                'message_id': message_id}
    except Exception:
        # The ledger may already contain a terminal callback; never overwrite it.
        _park(sb, claim, 'unknown')
        review = sb.rpc('review_retell_app_dispatch', {'p_message': message_id,
            'p_reason': 'Provider response or local persistence requires review; retain carrier evidence and do not resend'}).execute().data
        if not isinstance(review, dict) or review.get('held') is not True:
            raise RuntimeError('App SMS review hold unconfirmed; do not resend') from None
        record_provider_alert(sb, 'twilio', message_id, 'unknown', claim['lead_id'])
        raise RuntimeError('Provider outcome requires review; do not repeat the send') from None


def process_ack(sb, job_id):
    target = str(UUID(str(job_id)))
    if not dispatch_ready():
        return {'status':'disabled','dispatch_authorized':False}
    job = _row(sb, 'retell_form_sms_jobs', target)
    if (job.get('delivery_transport') != 'app_twilio' or job.get('status') != 'scheduled'
        or job.get('delivery_body') != APP_ACKNOWLEDGMENT):
        return {'status':'not_eligible','dispatch_authorized':False}
    claim = {'message_id':target,'session_id':target,'lead_id':job['lead_id'],'phone_number':job['phone_number'],
             'sender_number':job['delivery_sender'],'body':job['delivery_body'],'expires_at':job['expires_at']}
    if not _eligible(sb, claim):
        return {'status':'not_eligible','dispatch_authorized':False}
    won = sb.rpc('claim_retell_app_ack',{'p_job':target}).execute().data
    if not isinstance(won,list):
        raise RuntimeError('App acknowledgment claim unconfirmed; no provider call')
    if not won:
        return {'status':'not_claimed','dispatch_authorized':False}
    if len(won)!=1 or won[0].get('id')!=target:
        raise RuntimeError('App acknowledgment claim mismatch; no provider call')
    return _submit(sb,claim)


def process_reply(sb, turn_id):
    target = str(UUID(str(turn_id)))
    if not dispatch_ready():
        return {'status':'disabled','dispatch_authorized':False}
    turn = _row(sb,'retell_api_turns',target)
    session = _row(sb,'retell_api_sessions',turn['session_id'])
    context = {'lead_id':session['lead_id'],'phone_number':session['phone_number'],
               'sender_number':session['sender_number'],'expires_at':turn['expires_at']}
    if turn.get('status')!='generated' or not _eligible(sb,context):
        return {'status':'not_eligible','dispatch_authorized':False}
    claim = sb.rpc('claim_retell_app_reply',{'p_turn':target}).execute().data
    if not isinstance(claim,dict):
        raise RuntimeError('Reply dispatch claim unconfirmed; no provider call')
    if claim.get('claimed') is not True:
        return {'status':'not_claimed','dispatch_authorized':False}
    if (claim.get('turn_id')!=target or claim.get('session_id')!=session['id']
        or any(claim.get(k)!=v for k,v in context.items() if k!='expires_at')):
        raise RuntimeError('Reply dispatch claim identity mismatch; no provider call')
    # Expiry comes from the immutable SQL turn; compare instants despite JSON formatting.
    if datetime.fromisoformat(claim['expires_at'].replace('Z','+00:00')) != datetime.fromisoformat(turn['expires_at'].replace('Z','+00:00')):
        raise RuntimeError('Reply dispatch deadline mismatch; no provider call')
    return _submit(sb,claim)
