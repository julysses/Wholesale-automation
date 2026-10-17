"""Disabled-by-default carrier reply handoff; never initiate a new SMS chat.

TwiML redirect must pass a real owner-only provider acceptance test before
production activation. Keeping the carrier receipt first preserves STOP routing.
"""
import os
import re
from tools.retell_form_sms import activation_ready, enabled
from tools.sms_controls import is_control
from tools.sms_client import SMSClient, sms_consent_blocker
from config.settings import settings

# Fixed destination: payloads and environment variables cannot redirect private
# messages to an arbitrary host or another Retell workspace.
RETELL_REPLY_URL = 'https://api.retellai.com/twilio-sms-webhook/org_A7WQTvreWdPMlzic'

def reply_redirect(sb, data, receipt):
    """Return a target only after the carrier receipt and all sending gates pass."""
    if (not enabled('RETELL_SMS_REPLY_ROUTING_ENABLED') or not activation_ready()
            or receipt.get('saved') is not True or receipt.get('duplicate') is not False
            or receipt.get('suppressed') is not False or receipt.get('opt_out') is not False
            or not receipt.get('lead_id') or is_control(data)):
        return None
    phone = data.get('From', '')
    allowed = {p.strip() for p in settings.sms_allowed_recipients.split(',') if p.strip()}
    if (phone not in allowed or not re.fullmatch(r'\+1\d{10}', phone)
            or data.get('To') != os.getenv('RETELL_SMS_FROM_NUMBER')
            or not SMSClient()._in_allowed_hours()):
        return None
    # Only a known outbound form chat can be continued. Never create an inbound
    # conversation for an unknown sender or guess among multiple CRM identities.
    # SELECT * remains compatible with the old schema while allowing explicit
    # ownership checks after migration. An API chat never belongs on this path.
    jobs = sb.table('retell_form_sms_jobs').select('*').eq(
        'phone_number', phone).eq('status', 'accepted').limit(2).execute().data or []
    if (len(jobs) != 1 or jobs[0].get('lead_id') != receipt['lead_id'] or not jobs[0].get('chat_id')
            or jobs[0].get('delivery_transport', 'retell_native') != 'retell_native'):
        return None
    if sms_consent_blocker(sb, receipt['lead_id'], phone):
        return None
    return RETELL_REPLY_URL
