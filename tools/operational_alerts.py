"""Durable operator alerts; never retry an external message to report failure."""
from uuid import NAMESPACE_URL, uuid5


LABELS = {'twilio': 'SMS', 'sendgrid': 'Email', 'retell': 'AI call', 'test': 'Launch drill'}


def record_provider_alert(sb, provider: str, reference: str, status: str, lead_id=None) -> str:
    if provider not in LABELS or not reference:
        raise ValueError('A known provider and reference are required')
    notification_id = str(uuid5(NAMESPACE_URL, f'wholesaleos:provider-alert:{provider}:{reference}:{status}'))
    drill = provider == 'test'
    alert = {
        'id': notification_id, 'recipient_role': 'admin', 'type': 'system',
        'title': 'TEST — launch failure alert' if drill else f'{LABELS[provider]} delivery needs review',
        'body': ('This is an authorized in-app launch drill. No external message or call was sent.' if drill else
                 f'{LABELS[provider]} outcome: {status}. Review the provider receipt and follow up manually. '
                 'Do not resend an uncertain attempt until its outcome is reconciled.'),
        'action_url': '/setup', 'action_label': 'Review delivery',
        'metadata': {'integration_failure': True, 'provider': provider, 'reference': reference,
                     'status': status, 'test_drill': drill},
    }
    if lead_id:
        alert['lead_id'] = str(lead_id)
    saved = sb.table('app_notifications').upsert(alert, on_conflict='id', ignore_duplicates=True).execute().data
    if not saved and not sb.table('app_notifications').select('id').eq('id', notification_id).limit(1).execute().data:
        raise RuntimeError('Operator failure alert was not confirmed')
    return notification_id
