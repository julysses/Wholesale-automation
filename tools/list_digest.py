"""Owner-only daily digest. Existing email ledger is the final atomic send gate."""
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
import os

from config.settings import settings
from tools.crm import get_supabase_client
from tools.email_client import EmailClient

CENTRAL = ZoneInfo('America/Chicago')


def _text(value, limit=250):
    return ' '.join(str(value if value is not None else 'unknown').split())[:limit]


def render_digest(summary):
    lines = [f"WholesaleOS daily list report — {_text(summary.get('day'))}",
             'Dallas and Collin counties. Collection coverage is limited to configured sources.',
             f"New leads: {_text(summary.get('new_leads'))}; stacked observations: {_text(summary.get('stacked_records'))}.", '', 'Sources:']
    for source in summary.get('sources', [])[:50]:
        lines.append(f"- {_text(source.get('source_key'))}: {_text(source.get('status'))}; "
                     f"{'enabled' if source.get('enabled') else 'disabled'}; "
                     f"batches {_text(source.get('received_batches'))}/{_text(source.get('expected_batches'))}; "
                     f"records {_text(source.get('records_in'))}; {_text(source.get('status_reason'))}")
    lines += ['', 'Open incidents:']
    for incident in summary.get('open_incidents', [])[:100]:
        lines.append(f"- {_text(incident.get('day'))} / {_text(incident.get('source_id'))}: {_text(incident.get('kind'))}")
    if len(summary.get('open_incidents', [])) > 100:
        lines.append('Additional incidents are available in the CRM; this email is truncated.')
    lines += ['', 'Top scored leads (stored evaluations; permission to contact must be checked separately):']
    for lead in summary.get('top_ten', [])[:10]:
        lines.append(f"- Lead {_text(lead.get('lead_id'))}: score {_text(lead.get('score'))}; route {_text(lead.get('route'))}")
    lines += ['', 'No seller contact or offer was authorized by this report. Review source receipts and follow-up tasks in the CRM.']
    return '\n'.join(lines)


def deliver_digest(summary, now=None):
    """Reserve immutable content, attempt at most one claimed email, reconcile evidence."""
    if os.getenv('LIST_DIGEST_ENABLED', 'false').lower() != 'true':
        return {'status': 'disabled'}
    now = (now or datetime.now(CENTRAL)).astimezone(CENTRAL)
    # Begin at 07:00 to allow reconciliation before the 07:30 delivery target.
    if now.hour < 7:
        return {'status': 'waiting_for_window'}
    day = now.date().isoformat()
    if not isinstance(summary, dict) or summary.get('day') != day:
        raise RuntimeError('Digest day does not match the current Central date')
    recipient = settings.notification_email.strip().lower()
    sb = get_supabase_client()
    if sb is None:
        raise RuntimeError('Digest storage unavailable')
    if not recipient:
        evidence = sb.rpc('reconcile_list_digests', {}).execute().data
        if not isinstance(evidence, dict) or not isinstance(evidence.get('digests'), list):
            raise RuntimeError('Missing owner delivery alert was not confirmed')
        return {'status': 'owner_email_not_configured', **evidence}
    message_id = str(uuid5(NAMESPACE_URL, f'wholesaleos:list-digest:{day}'))
    receipt = sb.rpc('reserve_list_digest', {'p_day': day, 'p_recipient': recipient, 'p_message': message_id}).execute().data
    if (not isinstance(receipt, dict) or receipt.get('day') != day
            or receipt.get('message_id') != message_id or receipt.get('recipient') != recipient
            or not isinstance(receipt.get('summary'), dict) or type(receipt.get('send_allowed')) is not bool):
        raise RuntimeError('Digest reservation was not confirmed')
    # Shared EmailClient handles suppression, recipient allowlist, live flag,
    # atomic claims and ambiguous provider outcomes. Never use a fresh retry ID.
    if receipt['send_allowed']:
        EmailClient('sendgrid').send(recipient, f'WholesaleOS daily lists — {day}',
                                     render_digest(receipt['summary']), message_id=message_id)
    result = sb.rpc('reconcile_list_digests', {}).execute().data
    if not isinstance(result, dict) or not (isinstance(result.get('digests'), list) or result.get('busy') is True):
        raise RuntimeError('Digest delivery reconciliation was not confirmed')
    return {'message_id': message_id, **result}
