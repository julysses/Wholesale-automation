"""Retell SMS preparation only: no network client or sending capability."""
import re
from uuid import NAMESPACE_URL, uuid5

INITIAL_MESSAGE = (
    'Hi {{first_name}}, this is {{sender_name}} with Hilltop Home Co. '
    'We’re a local investor in Dallas interested in buying your property on {{street_address}}. '
    'We can provide a straightforward offer within 24 hours and close on your timeline—as soon as 10 days, '
    'subject to title clearance and closing requirements. Reply STOP to opt out.'
)

SMS_REVIEW_HEADERS = ['DraftID', 'LeadID', 'ContactName', 'Phone', 'PropertyAddress', 'City',
                     'State', 'Zip', 'County', 'TraceRequestID', 'FollowUpTaskID',
                     'FirstName', 'SenderName', 'MessageDraft', 'SMSReady', 'HoldReason']


def sms_review_row(row):
    """Use existing screened review rows; never turn a review into clearance."""
    lead, name, phone, street, city, state, zipcode, county, trace, task, dnc = row[:11]
    # A traced contact can be an associate, estate or entity. Do not infer seller identity.
    message = INITIAL_MESSAGE.replace('{{street_address}}', street or '{{street_address}}')
    holds = ['Sending disabled', 'Seller identity and first name require confirmation',
             'Sender identity required', 'Documented SMS consent required',
             'Fresh channel clearance required', 'Retell SMS setup and acceptance pending']
    if dnc != 'clear':
        holds.append('DNC status unresolved')
    if not street:
        holds.append('Property street address missing')
    return [str(uuid5(NAMESPACE_URL, f'wholesaleos:retell-sms:{lead}:{phone}')),
            lead, name, phone, street, city, state, zipcode, county, trace, task,
            '', '', message, 'false', '; '.join(holds)]


def recipient_opted_out(messages):
    """Inspect only recipient turns; agent's 'Reply STOP' must never suppress."""
    keyword = re.compile(r"^\s*(?:stop|stopall|unsubscribe|cancel|end|quit|revoke|opt\s*out)[.!?\s]*$", re.I)
    request = re.compile(r"\b(?:do not|don't|dont|never)\s+(?:call|text|contact)\b|"
                         r"\bstop\s+(?:calling|texting|contacting)\b|\bremove\s+me\b|\bwrong\s+number\b", re.I)
    return any(isinstance(m, dict) and m.get('role') == 'user'
               and (keyword.search(str(m.get('content') or ''))
                    or request.search(str(m.get('content') or '').replace('’', "'"))) for m in messages)



def record_chat_event(sb, payload):
    """Persist signed chat receipts and human review tasks; never reply or enroll."""
    import hashlib
    import json
    from datetime import datetime, timezone
    chat = payload.get('chat')
    if not isinstance(chat, dict) or not chat.get('chat_id'):
        raise ValueError('Chat ID required')
    metadata = chat.get('metadata') or {}
    if not isinstance(metadata, dict):
        raise ValueError('Chat metadata must be an object')
    if chat.get('chat_type') == 'api_chat' or metadata.get('transport') == 'wholesaleos_twilio':
        from tools.retell_api_receipts import record_api_chat_event
        return record_api_chat_event(sb, payload)
    lead_id = metadata.get('lead_id')
    phone = chat.get('from_number') if chat.get('direction') == 'inbound' else chat.get('to_number')
    if not lead_id or not phone:
        # The documented chat response may omit telephone fields. Resolve the
        # exact provider chat receipt, never a newest lead or phone match.
        jobs = sb.table('retell_form_sms_jobs').select('lead_id,phone_number').eq(
            'chat_id', chat['chat_id']).limit(2).execute().data or []
        if (len(jobs) != 1 or (lead_id and jobs[0].get('lead_id') != lead_id)
                or (phone and jobs[0].get('phone_number') != phone)):
            raise ValueError('Chat must identify an existing CRM lead')
        lead_id = jobs[0].get('lead_id')
        phone = jobs[0].get('phone_number')
        if not phone:
            raise ValueError('Chat recipient must be known')
    leads = sb.table('leads').select('id,dnc').eq('id', lead_id).limit(1).execute().data if lead_id else []
    if not leads:
        raise ValueError('Chat must identify an existing CRM lead')
    chat_id = chat['chat_id']
    task_id = str(uuid5(NAMESPACE_URL, f'wholesaleos:retell-sms-task:{chat_id}'))
    messages = chat.get('message_with_tool_calls') or []
    if not isinstance(messages, list):
        raise ValueError('Chat messages must be a list')
    # Persist individual messages for CRM SMS history and cross-provider reply checks.
    # Message IDs, not event IDs, keep successive full transcripts from duplicating turns.
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in {'user', 'agent'}:
            continue
        content = str(message.get('content') or '')
        message_key = message.get('message_id') or hashlib.sha256(
            json.dumps(message, sort_keys=True).encode()).hexdigest()
        saved = sb.table('sms_events').upsert({
            'id': str(uuid5(NAMESPACE_URL, f'wholesaleos:retell-sms-message:{chat_id}:{message_key}')),
            'lead_id': lead_id, 'provider': 'retell',
            'direction': 'inbound' if message['role'] == 'user' else 'outbound',
            'phone_number': phone, 'body': content, 'status': 'received' if message['role'] == 'user' else 'recorded',
            'opt_out': bool(recipient_opted_out([message])),
            'raw_payload': {'chat_id': chat_id, 'message_id': message_key, 'source': 'retell_chat_transcript'},
        }, on_conflict='id', ignore_duplicates=True).execute()
        if not saved.data and not sb.table('sms_events').select('id').eq('id', str(uuid5(
            NAMESPACE_URL, f'wholesaleos:retell-sms-message:{chat_id}:{message_key}'))).execute().data:
            raise RuntimeError('SMS message history not confirmed')
    analysis = chat.get('chat_analysis') or {}
    custom = analysis.get('custom_analysis_data') or {}
    opted_out = recipient_opted_out(messages) or custom.get('disposition') == 'dnc'
    if opted_out:
        result = sb.table('dnc_registry').upsert({
            'id': str(uuid5(NAMESPACE_URL, f'wholesaleos:retell-sms-optout:{chat_id}')),
            'lead_id': lead_id, 'phone_number': phone or None, 'reason': 'sms_opt_out',
            'source': 'retell', 'raw_payload': payload,
        }, on_conflict='id').execute()
        if not result.data:
            raise RuntimeError('SMS suppression receipt not confirmed')
        result = sb.table('leads').update({'dnc': True, 'status': 'dnc',
            'ai_calling_paused': True, 'sms_sequence_active': False}).eq('id', lead_id).execute()
        if not result.data:
            raise RuntimeError('SMS lead suppression not confirmed')
    # On every later/retried event, cancel a pending task if already suppressed.
    suppressed = opted_out or leads[0].get('dnc') is not False
    if suppressed:
        pending = sb.table('tasks').select('id').eq('id', task_id).eq('status', 'pending').execute().data
        if pending:
            result = sb.table('tasks').update({'status': 'cancelled'}).eq('id', task_id).eq('status', 'pending').execute()
            if not result.data:
                raise RuntimeError('SMS follow-up cancellation not confirmed')
    elif any(isinstance(m, dict) and m.get('role') == 'user' for m in messages):
        paused = sb.table('leads').update({'ai_calling_paused': True, 'sms_sequence_active': False}).eq(
            'id', lead_id).eq('dnc', False).execute()
        if not paused.data:
            current = sb.table('leads').select('dnc').eq('id', lead_id).limit(1).execute().data
            if not current or current[0].get('dnc') is not True:
                raise RuntimeError('SMS reply automation pause not confirmed')
        recipient_text = '\n'.join(str(m.get('content') or '') for m in messages
                                   if isinstance(m, dict) and m.get('role') == 'user')[-3000:]
        result = sb.table('tasks').upsert({
            'id': task_id, 'lead_id': lead_id, 'title': 'Retell SMS reply: review and follow up',
            'description': f'Chat: {chat_id}\nReview the saved SMS receipt before outreach. '
                           'No reply, call, or SMS has been scheduled.\nRecipient replies (unverified):\n' + recipient_text,
            'priority': 'high', 'status': 'pending', 'type': 'acquisition_review',
        }, on_conflict='id', ignore_duplicates=True).execute()
        if not result.data and not sb.table('tasks').select('id').eq('id', task_id).execute().data:
            raise RuntimeError('SMS follow-up not confirmed')
        # A concurrent opt-out may have cancelled before this task was inserted.
        # Recheck after insertion so the late reply cannot leave a fresh pending task.
        current = sb.table('leads').select('dnc').eq('id', lead_id).limit(1).execute().data
        if not current:
            raise RuntimeError('SMS reply suppression recheck not confirmed')
        if current[0].get('dnc') is not False:
            sb.table('tasks').update({'status': 'cancelled'}).eq('id', task_id).eq('status', 'pending').execute()
            if sb.table('tasks').select('id').eq('id', task_id).eq('status', 'pending').execute().data:
                raise RuntimeError('Late SMS task suppression not confirmed')
    # Archive after side effects: retries repair partial failures. The digest keeps
    # successive transcript updates distinct and duplicate deliveries identical.
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    result = sb.table('webhook_jobs').upsert({
        'id': str(uuid5(NAMESPACE_URL, f'wholesaleos:retell-sms-event:{chat_id}:{digest}')),
        'source': 'retell_sms', 'payload': payload, 'status': 'done',
        'processed_at': datetime.now(timezone.utc).isoformat(),
    }, on_conflict='id').execute()
    if not result.data:
        raise RuntimeError('SMS event receipt not confirmed')
    return {'status': 'accepted', 'event': payload['event'], 'dispatch_authorized': False}
