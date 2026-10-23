"""Read-only reconciliation of a provider chat against an existing held session."""
import os
import hashlib
from uuid import UUID

import requests

from tools.retell_api_chat import _identifier, matches_agent_version, agent_texts, ChatReviewRequired
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
    checks['pinned_version_valid'] = matches_agent_version(data, session.get('agent_version'))
    history = {}
    for field in ('transcript', 'message_with_tool_calls', 'transcript_with_tool_calls', 'messages'):
        if field in data:
            value = data[field]
            history[field] = {'type': type(value).__name__,
                              'empty': value == '' or value == []}
    result = {'status': 'inspected', 'session_id': target, 'chat_id': chat_id,
            'checks': checks, 'history_shape': history,
            'dispatch_authorized': False}
    # A first-turn recovery needs exact live history, not merely a webhook or
    # an operator-supplied message. Return fingerprints only, never transcript.
    required = ('chat_id', 'chat_type', 'agent_id', 'metadata', 'ongoing', 'pinned_version_valid')
    messages = data.get('message_with_tool_calls')
    if (all(checks[k] for k in required) and isinstance(messages, list) and len(messages) == 2
            and isinstance(messages[0], dict) and messages[0].get('role') == 'user'
            and isinstance(messages[0].get('content'), str)):
        try:
            generated = agent_texts(messages[1:])
            # Distinct provider IDs and no unsupported input media.
            if (not _identifier(messages[0].get('message_id'))
                    or messages[0]['message_id'] == generated[0].message_id
                    or messages[0].get('multimedia')):
                return result
            result['first_turn_proof'] = {
                'user_message_id': messages[0]['message_id'],
                'recipient_sha256': hashlib.sha256(messages[0]['content'].encode()).hexdigest(),
                'message_id': generated[0].message_id,
                'content_sha256': hashlib.sha256(generated[0].content.encode()).hexdigest(),
            }
        except ChatReviewRequired:
            pass
    return result
