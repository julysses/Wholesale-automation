"""Persist actual carrier replies for app-owned conversations; never send here."""
from uuid import UUID

from tools.retell_form_sms import enabled
from tools.sms_controls import is_control


def queue_reply(sb, data, receipt, event_id):
    """Return True when app ownership forbids the native TwiML handoff.

    The durable receipt RPC has already committed suppression and human follow-up.
    Repeated callbacks may repair an enqueue failure, using the same carrier event
    identity. SQL verifies the original saved receipt, not the retry's text.
    """
    if receipt.get('saved') is not True or is_control(data):
        return False
    if not (enabled('RETELL_APP_TRANSPORT_ENABLED') or enabled('RETELL_SMS_REPLY_ROUTING_ENABLED')):
        return False
    jobs = sb.table('retell_form_sms_jobs').select('*').eq('phone_number', data.get('From')).in_(
        'status', ['accepted', 'processing', 'review']).limit(2).execute().data
    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
        raise RuntimeError('Reply transport ownership unconfirmed')
    if len(jobs) >= 2:
        # A truncated/ambiguous set must not hide another app conversation and
        # let the native router pick its sole accepted row from a different set.
        return True
    if not any(j.get('delivery_transport') == 'app_twilio' for j in jobs):
        return False
    # Never choose a newest/nearest inquiry, route around a hold, or guess a lead.
    if jobs[0].get('status') != 'accepted':
        return True
    job = jobs[0]
    if job.get('delivery_sender') != data.get('To'):
        return True
    result = sb.rpc('enqueue_retell_api_turn', {
        'p_job': str(UUID(str(job['id']))), 'p_event': str(UUID(str(event_id))),
    }).execute().data
    if not isinstance(result, dict) or type(result.get('queued')) is not bool:
        raise RuntimeError('Reply queue persistence unconfirmed')
    if result['queued'] and (result.get('turn_id') != event_id or result.get('session_id') != job['id']):
        raise RuntimeError('Reply queue identity unconfirmed')
    if not result['queued'] and (not isinstance(result.get('reason'), str)
            or (result['reason'] == 'existing_turn' and result.get('turn_id') != event_id)):
        raise RuntimeError('Reply queue hold unconfirmed')
    return True
