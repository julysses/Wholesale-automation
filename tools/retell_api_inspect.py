"""Read-only reconciliation of a provider chat against an existing held session."""
import os
from uuid import UUID

import requests

from tools.retell_api_chat import _identifier
from tools.retell_api_turns import _row


def inspect_session(sb, session_id, chat_id):
    target = str(UUID(str(session_id)))
    if not _identifier(chat_id):
        raise ValueError('Invalid chat identifier')
    session = _row(sb, 'retell_api_sessions', target)
    if session.get('chat_id') not in {None, chat_id}:
        return {'status': 'saved_chat_mismatch', 'dispatch_authorized': False}
    key = os.getenv('RETELL_SMS_API_KEY')
    if not key:
        return {'status': 'unconfigured', 'dispatch_authorized': False}
    # GET only: never create, complete, bind, recover, or authorize dispatch.
    try:
        response = requests.get('https://api.retellai.com/get-chat/' + chat_id,
            headers={'Authorization': 'Bearer ' + key}, timeout=(5, 20), allow_redirects=False)
        if response.status_code != 200:
            return {'status': 'provider_lookup_failed', 'http_status': response.status_code,
                    'dispatch_authorized': False}
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('Invalid receipt')
    except (requests.RequestException, ValueError, TypeError):
        return {'status': 'provider_lookup_unconfirmed', 'dispatch_authorized': False}
    metadata = {'operation_id': target, 'lead_id': session['lead_id'], 'transport': 'wholesaleos_twilio'}
    checks = {'chat_id': data.get('chat_id') == chat_id,
              'chat_type': data.get('chat_type') == 'api_chat',
              'agent_id': data.get('agent_id') == session.get('agent_id'),
              'metadata': data.get('metadata') == metadata,
              'ongoing': data.get('chat_status') == 'ongoing'}
    # Only field presence, types and comparisons leave the server; never expose
    # transcript, arbitrary metadata, provider error bodies or credentials.
    for field in ('version', 'agent_version'):
        checks[field + '_present'] = field in data
        checks[field + '_integer'] = type(data.get(field)) is int
        checks[field + '_matches'] = (type(data.get(field)) is int
                                     and data[field] == session.get('agent_version'))
    return {'status': 'inspected', 'checks': checks, 'dispatch_authorized': False}
