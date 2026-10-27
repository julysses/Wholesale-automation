"""Pure structured inbound tool preparation, after signature verification.

Not an HTTP handler or authorization grant. Persistence must recheck trusted route,
call lifecycle, revision, and idempotency inside one transaction before success.
"""
import hashlib
import json
from uuid import UUID

from tools.acquisition_inbound_events import project_inbound_event
from tools.acquisition_intake import FIELDS, normalize_seller_fields
from tools.facebook_consent import normalize_us_phone

VERSION = 'acquisition-inbound-tools-v1'
NAMES = {'submit_seller_intake', 'request_callback', 'request_human'}


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('INVALID_TOOL_TEXT')
    if any(ord(char) < 32 and char not in '\n\t' for char in value):
        raise ValueError('INVALID_TOOL_TEXT')
    return value


def prepare_inbound_tool(payload, **routing):
    """Validate one wrapped custom function without trusting model scope/authority.

    request_id is an idempotency token, not proof of permission. expected_revision
    is optimistic concurrency input, never a claim that an existing write occurred.
    """
    if not isinstance(payload, dict) or set(payload) != {'name', 'call', 'args'}:
        raise ValueError('INVALID_TOOL_ENVELOPE')
    name = payload['name']
    if not isinstance(name, str) or name not in NAMES:
        raise ValueError('UNSUPPORTED_TOOL')
    call = payload['call']
    # Reuse exact agent/version/number and inbound checks. A tool requires ongoing,
    # not merely registered, state. The persisted ledger must also be nonterminal.
    if not isinstance(call, dict) or call.get('call_status') != 'ongoing':
        raise ValueError('CALL_NOT_ONGOING')
    context = project_inbound_event({'event': 'call_started', 'call': call}, **routing)
    args = payload['args']
    fields = {'submit_seller_intake': {'answers'},
              'request_callback': {'phone', 'preferred_time', 'purpose', 'requested_by_caller'},
              'request_human': {'reason', 'details', 'requested_by_caller'}}[name]
    if not isinstance(args, dict) or set(args) != fields | {'request_id', 'expected_revision'}:
        raise ValueError('INVALID_TOOL_ARGUMENTS')
    identity = args['request_id']
    if not isinstance(identity, str) or str(UUID(identity)) != identity:
        raise ValueError('INVALID_REQUEST_ID')
    revision = args['expected_revision']
    if type(revision) is not int or not 0 <= revision < 1000000000:
        raise ValueError('INVALID_REVISION')
    if name == 'submit_seller_intake':
        answers = args['answers']
        if not isinstance(answers, dict) or not answers or set(answers) - FIELDS:
            raise ValueError('INVALID_INTAKE_FIELDS')
        # Only explicit structured answers. Never mine call transcript or caller ID.
        for value in answers.values():
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('INVALID_INTAKE_ANSWER')
        data = normalize_seller_fields([{'name': key, 'values': [answers[key]]} for key in sorted(answers)])
        evidence = {'answers': dict(sorted(answers.items()))}
    elif name == 'request_callback':
        if args['requested_by_caller'] is not True:
            raise ValueError('CALLBACK_NOT_REQUESTED')
        # Preserve the supplied number as an unverified assertion. Never default
        # to caller ID or grant channel/AI-voice consent from this request.
        evidence = {key: _text(args[key], maximum) for key, maximum in
                    [('phone', 100), ('preferred_time', 500), ('purpose', 500)]}
        evidence['requested_by_caller'] = True
        try:
            normalized_phone = normalize_us_phone(evidence['phone'])
        except ValueError:
            normalized_phone = None
        data = {**evidence, 'status': 'review_required', 'phone_verified': False,
                'eligibility_required': True, 'scheduled_at': None,
                'normalized_phone': normalized_phone,
                'reason_codes': ['CONTACT_ELIGIBILITY_REVIEW_REQUIRED'] +
                    ([] if normalized_phone else ['PHONE_NORMALIZATION_REVIEW_REQUIRED'])}
    else:
        if type(args['requested_by_caller']) is not bool:
            raise ValueError('INVALID_REQUEST_ASSERTION')
        reasons = {'caller_requested', 'unsupported_language', 'failed_transfer',
                   'sensitive_situation', 'unable_to_complete'}
        if not isinstance(args['reason'], str) or args['reason'] not in reasons:
            raise ValueError('INVALID_ESCALATION_REASON')
        if args['reason'] == 'caller_requested' and args['requested_by_caller'] is not True:
            raise ValueError('HUMAN_NOT_REQUESTED')
        evidence = {'reason': args['reason'], 'details': _text(args['details'], 1000),
                    'requested_by_caller': args['requested_by_caller']}
        data = {**evidence, 'status': 'review_required', 'transfer_authorized': False}
    result = {'version': VERSION, 'workspace_id': context['workspace_id'],
              'integration_id': context['integration_id'], 'call_id': context['call_id'],
              'agent_id': context['agent_id'], 'agent_version': context['agent_version'],
              'name': name, 'request_id': identity, 'expected_revision': revision,
              'evidence': evidence, 'prepared': data,
              'contact_permission_granted': False, 'execution_authorized': False}
    result['request_hash'] = hashlib.sha256(json.dumps(result, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return result
