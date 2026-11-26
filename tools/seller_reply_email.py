"""Owner-only email for a durably recorded inbound SMS; never sends seller SMS."""
from uuid import NAMESPACE_URL, UUID, uuid5

from config.settings import settings
from tools.email_client import EmailClient
from tools.operational_alerts import record_provider_alert


def email_reference(event_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f'wholesaleos:seller-reply-email:{UUID(event_id)}'))


def _one(sb, table, columns, identity):
    rows = sb.table(table).select(columns).eq('id', identity).limit(1).execute().data
    if not isinstance(rows, list):
        raise RuntimeError('Owner email evidence could not be read')
    return rows[0] if rows else None


def notify_reply(sb, event_id: str) -> dict:
    """The existing atomic email claim is the final gate, including concurrent retries.

    Read the saved carrier receipt, never a caller-provided recipient/message. An
    accepted, attempting or uncertain email is never resent. Email remains separate
    from seller outreach hours, consent and the SMS pause.
    """
    event_id = str(UUID(event_id))
    reference = email_reference(event_id)
    if not settings.email_live_enabled:
        return {'status': 'disabled', 'message_id': reference, 'provider_accepted': False}
    receipt = _one(sb, 'sms_events', 'id,provider,direction,lead_id,phone_number,body,opt_out,created_at', event_id)
    if not receipt or receipt.get('provider') != 'twilio' or receipt.get('direction') != 'inbound':
        return {'status': 'not_found', 'message_id': reference, 'provider_accepted': False}
    notification = _one(sb, 'app_notifications', 'id,metadata', event_id)
    if not notification:
        raise RuntimeError('Incoming SMS notification is not committed')
    # Link the operator-visible receipt to the email delivery ledger before sending.
    metadata = {**(notification.get('metadata') or {}), 'owner_email_message_id': reference}
    if not sb.table('app_notifications').update({'metadata': metadata}).eq('id', event_id).execute().data:
        raise RuntimeError('Owner email reference was not saved')
    existing = _one(sb, 'email_messages', 'id,status,recipient', reference)
    if existing:
        return {'status': existing['status'], 'message_id': reference,
                'provider_accepted': existing['status'] in ('accepted', 'delivered'), 'duplicate': True}
    recipient = settings.notification_email.strip().lower()
    if not recipient:
        record_provider_alert(sb, 'sendgrid', reference, 'owner_not_configured', receipt.get('lead_id'))
        return {'status': 'owner_not_configured', 'message_id': reference, 'provider_accepted': False}
    lead_id = str(UUID(receipt['lead_id'])) if receipt.get('lead_id') else None
    lead = _one(sb, 'leads', 'id,property_address,owner_first_name,owner_last_name', lead_id) if lead_id else None
    lead = lead or {}
    address = ' '.join(str(lead.get('property_address') or 'Unmatched property').split())[:200]
    name = ' '.join(str(lead.get(key) or '') for key in ('owner_first_name', 'owner_last_name')).strip() or 'Unknown sender'
    subject = ('Seller opted out' if receipt.get('opt_out') else 'Seller message received') + f' — {address}'
    link = f'https://wholesale-automation.vercel.app/leads?lead={lead_id}' if lead_id else 'https://wholesale-automation.vercel.app/leads'
    body = (f'{subject}\n\nFrom: {name}\nPhone: {receipt.get("phone_number", "")}\n'
            f'Received: {receipt.get("created_at", "")}\n\nSeller message:\n'
            f'{str(receipt.get("body") or "[Message has no text]")[:10000]}\n\n'
            + ('This seller opted out. Do not call or text them. Review the CRM suppression record.\n' if receipt.get('opt_out') else
               'Review the conversation in WholesaleOS before following up.\n')
            + f'Open CRM record: {link}\n\nThis is an internal owner alert. Replying to this email does not message the seller.')
    accepted = EmailClient().send(to_email=recipient, subject=subject, body=body, message_id=reference)
    outcome = _one(sb, 'email_messages', 'id,status,recipient', reference)
    if not outcome:
        # Includes disabled credentials, suppression and failures before a claim.
        # A durable operator alert exposes the failure; a carrier retry can safely
        # recheck because no email attempt was committed.
        record_provider_alert(sb, 'sendgrid', reference, 'not_claimed', lead_id)
        raise RuntimeError('Owner email was not claimed; review email configuration')
    return {'status': outcome['status'], 'message_id': reference, 'provider_accepted': bool(accepted)}
