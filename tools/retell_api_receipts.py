"""Archive authenticated API-chat events without manufacturing carrier history."""
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import UUID, NAMESPACE_URL, uuid5


def record_api_chat_event(sb, payload):
    chat = payload['chat']
    metadata = chat.get('metadata')
    if (chat.get('chat_type') != 'api_chat' or not isinstance(metadata, dict)
            or metadata.get('transport') != 'wholesaleos_twilio'
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', str(chat.get('chat_id') or ''))):
        raise ValueError('App API chat ownership is required')
    try:
        session_id = str(UUID(str(metadata.get('operation_id'))))
        lead_id = str(UUID(str(metadata.get('lead_id'))))
    except ValueError:
        raise ValueError('App API chat references are invalid') from None
    rows = sb.table('retell_api_sessions').select('*').eq('id', session_id).limit(1).execute().data
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError('App API session receipt is not yet available')
    session = rows[0]
    if (session.get('id') != session_id or session.get('lead_id') != lead_id
            or metadata != {'operation_id': session_id, 'lead_id': lead_id, 'transport': 'wholesaleos_twilio'}
            or chat.get('agent_id') != session.get('agent_id')
            or type(chat.get('version')) is not int or chat['version'] != session.get('agent_version')
            or (session.get('chat_id') is not None and chat['chat_id'] != session['chat_id'])
            or (session.get('chat_id') is None and session.get('status') not in {'creating', 'review'})):
        raise ValueError('App API chat does not match its claimed session')
    # A create callback can precede the HTTP response/session binding. Archive it
    # without binding, completing, suppressing or treating transcript as SMS.
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    event_id = str(uuid5(NAMESPACE_URL, f'wholesaleos:retell-api-event:{session_id}:{digest}'))
    saved = sb.table('webhook_jobs').upsert({
        'id': event_id, 'source': 'retell_api_chat', 'payload': payload,
        'status': 'done', 'processed_at': datetime.now(timezone.utc).isoformat(),
    }, on_conflict='id').execute().data
    if not saved:
        raise RuntimeError('App API event archive unconfirmed')
    return {'status': 'accepted', 'event': payload['event'], 'dispatch_authorized': False,
            'history_source': 'generation_only'}
