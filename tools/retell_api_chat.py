"""Retell generation-only adapter for the planned app-owned Twilio transport.

Used by the exact-turn generation worker, never a native SMS sender. Callers claim
one operation before calling, serialize each chat, and never retry uncertain
POSTs. Generated text is not an SMS or a delivery receipt.
"""
from dataclasses import dataclass
import re
from uuid import UUID

import requests
from tools.sms_controls import is_control
from tools.sms_reply_budget import short_sms_reply


class ChatOutcomeUncertain(RuntimeError):
    """The provider may have consumed the operation; park it for reconciliation."""


class ChatReviewRequired(ValueError):
    """Output cannot be automatically used as an SMS response."""


@dataclass(frozen=True)
class AgentText:
    message_id: str
    content: str


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None


def matches_agent_version(data, expected):
    """Accept the live agent_version or documented version alias, never conflicts.

    Retell's live API-chat GET and signed webhooks use agent_version. Some
    published examples use version. Every supplied field must be an exact int
    matching the pinned release; a valid alias cannot mask an invalid one.
    """
    fields = [field for field in ('agent_version', 'version') if field in data]
    return (type(expected) is int and bool(fields)
            and all(type(data[field]) is int and data[field] == expected for field in fields))


def agent_texts(messages):
    """Extract only agent text; reject tools, unknown roles and unsupported media.

    Holding the whole completion prevents partially sending a response that also
    contains a tool action requiring a separate, verified CRM side effect.
    """
    if not isinstance(messages, list) or not 1 <= len(messages) <= 20:
        raise ChatReviewRequired('Missing or oversized generated turn')
    result, seen = [], set()
    for message in messages:
        if not isinstance(message, dict) or message.get('role') != 'agent':
            raise ChatReviewRequired('Generated turn contains a non-text action')
        mid, content = message.get('message_id'), message.get('content')
        if not _identifier(mid) or mid in seen:
            raise ChatReviewRequired('Generated message identity is missing or repeated')
        if not isinstance(content, str) or not content.strip() or len(content) > 1600:
            raise ChatReviewRequired('Generated message text requires review')
        if message.get('multimedia') or any(ord(c) < 32 and c not in '\n\r\t' for c in content):
            raise ChatReviewRequired('Unsupported generated message content')
        seen.add(mid)
        result.append(AgentText(mid, content))
    if not short_sms_reply('\n'.join(m.content for m in result)):
        raise ChatReviewRequired('Combined generated reply exceeds the short SMS budget')
    return tuple(result)


class RetellAPIChat:
    """Fixed API-chat endpoints; never invokes create-sms-chat or Twilio."""

    def __init__(self, api_key, agent_id, agent_version):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('Retell API credential is required')
        if not _identifier(agent_id) or type(agent_version) is not int or not 0 <= agent_version <= 999999999:
            raise ValueError('A specific agent and numeric published version are required')
        self._key, self._agent, self._version = api_key, agent_id, agent_version

    def _post(self, endpoint, payload):
        try:
            response = requests.post('https://api.retellai.com/' + endpoint, json=payload,
                headers={'Authorization': 'Bearer ' + self._key}, timeout=(5, 20), allow_redirects=False)
            # Treat every unexpected status conservatively. Never retry a POST,
            # follow a redirect or expose provider response bodies in logs/errors.
            if response.status_code != 201:
                raise ChatOutcomeUncertain('Retell operation requires reconciliation')
            data = response.json()
            if not isinstance(data, dict):
                raise ChatOutcomeUncertain('Retell operation has no usable receipt')
            return data
        except (requests.RequestException, ValueError, TypeError):
            raise ChatOutcomeUncertain('Retell operation requires reconciliation') from None

    def _metadata(self, operation_id, lead_id):
        return {'operation_id': str(UUID(str(operation_id))), 'lead_id': str(UUID(str(lead_id))),
                'transport': 'wholesaleos_twilio'}

    def _verify_session(self, data, metadata, chat_id=None):
        if (not isinstance(data, dict) or not _identifier(data.get('chat_id'))
            or (chat_id is not None and data.get('chat_id') != chat_id)
            or data.get('chat_type') != 'api_chat' or data.get('agent_id') != self._agent
            or not matches_agent_version(data, self._version)
            or data.get('chat_status') != 'ongoing' or data.get('metadata') != metadata):
            raise ChatOutcomeUncertain('Retell session receipt does not match the claimed operation')

    def create(self, operation_id, lead_id):
        # Only internal references go to metadata. No invented user message,
        # arbitrary prompt variable or private record is submitted by this call.
        metadata = self._metadata(operation_id, lead_id)
        data = self._post('create-chat', {'agent_id': self._agent, 'agent_version': self._version,
                                        'metadata': metadata})
        self._verify_session(data, metadata)
        # Startup transcript is not dispatched. Only a completion in response to
        # an actual persisted inbound message can become a reply candidate.
        return data['chat_id']

    def complete(self, chat_id, recipient_text, session_operation_id, lead_id):
        if not _identifier(chat_id):
            raise ValueError('Invalid saved API chat identity')
        if not isinstance(recipient_text, str) or not recipient_text.strip() or len(recipient_text) > 1600:
            raise ValueError('A bounded actual recipient message is required')
        if is_control({'Body': recipient_text}):
            raise ChatReviewRequired('Control messages stay in the carrier/CRM handler')
        metadata = self._metadata(session_operation_id, lead_id)
        # Never submit to a native SMS chat: its autonomous delivery behavior is
        # outside this transport. Verify identity/type/version before every turn.
        try:
            response = requests.get('https://api.retellai.com/get-chat/' + chat_id,
                headers={'Authorization': 'Bearer ' + self._key}, timeout=(5, 20), allow_redirects=False)
            if response.status_code != 200:
                raise ChatOutcomeUncertain('Retell session verification failed; no completion attempted')
            self._verify_session(response.json(), metadata, chat_id)
        except (requests.RequestException, ValueError, TypeError):
            raise ChatOutcomeUncertain('Retell session verification failed; no completion attempted') from None
        # Consent and durable claiming remain caller responsibilities. Never
        # invent an input turn, truncate recipient text, or send an SMS here.
        data = self._post('create-chat-completion', {'chat_id': chat_id, 'content': recipient_text})
        return agent_texts(data.get('messages'))
