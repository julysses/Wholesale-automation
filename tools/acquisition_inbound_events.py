"""Pure inbound lifecycle projection. No transport, persistence or execution authority.

Call only after raw-body authentication and server-side routing resolution. Routing
arguments are trusted configuration, never values copied from webhook metadata.
"""
from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID

VERSION = 'acquisition-inbound-events-v1'
LIFECYCLE = {'call_started', 'call_ended', 'call_analyzed'}
STATUSES = {'registered', 'ongoing', 'ended', 'error', 'not_connected'}
SENSITIVE = {'transcript', 'transcript_object', 'transcript_with_tool_calls', 'recording_url',
             'recording_multi_channel_url', 'scrubbed_recording_url', 'scrubbed_transcript',
             'public_log_url', 'call_analysis'}


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise ValueError('INVALID_PROVIDER_ID')
    return value


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('INVALID_SCOPE')
    return value


def _stamp(value):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 253402300799999:
        raise ValueError('INVALID_TIMESTAMP')
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def project_inbound_event(payload, *, workspace_id, integration_id, agent_id, agent_version, acquisition_number):
    """Strip caller identity and content; prove only event/configuration consistency.

    Does not prove signature, caller ownership, consent, routing approval or that
    recording/transcription is disabled at the provider.
    """
    workspace_id, integration_id = _uuid(workspace_id), _uuid(integration_id)
    agent_id = _id(agent_id)
    if type(agent_version) is not int or agent_version < 0:
        raise ValueError('INVALID_AGENT_VERSION')
    if not isinstance(acquisition_number, str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', acquisition_number):
        raise ValueError('INVALID_ROUTING_NUMBER')
    if not isinstance(payload, dict) or not isinstance(payload.get('event'), str) or payload['event'] not in LIFECYCLE:
        # Transfer attempts need a verified attempt identity, not call-wide dedup.
        raise ValueError('UNSUPPORTED_INBOUND_EVENT')
    call = payload.get('call')
    if not isinstance(call, dict):
        raise ValueError('INVALID_CALL_OBJECT')
    if call.get('call_type') != 'phone_call' or call.get('direction') != 'inbound':
        raise ValueError('NOT_INBOUND_PHONE_CALL')
    if (call.get('agent_id') != agent_id or type(call.get('agent_version')) is not int
            or call['agent_version'] != agent_version or call.get('to_number') != acquisition_number):
        raise ValueError('INBOUND_ROUTING_MISMATCH')
    call_id = _id(call.get('call_id'))
    status = call.get('call_status')
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError('UNSUPPORTED_CALL_STATUS')
    start, end = _stamp(call.get('start_timestamp')), _stamp(call.get('end_timestamp'))
    if start is not None and end is not None and end < start:
        raise ValueError('INVALID_CALL_INTERVAL')
    event = payload['event']
    if event == 'call_started' and (status not in {'registered', 'ongoing'} or end is not None):
        raise ValueError('CONFLICTING_LIFECYCLE')
    if event in {'call_ended', 'call_analyzed'} and status not in {'ended', 'error', 'not_connected'}:
        raise ValueError('CONFLICTING_LIFECYCLE')
    # Deliberate allowlist: never spread raw call/metadata/analysis into this object.
    result = dict(version=VERSION, workspace_id=workspace_id, integration_id=integration_id,
                  call_id=call_id, event=event, agent_id=agent_id, agent_version=agent_version,
                  direction='inbound', call_status=status, start_timestamp=start, end_timestamp=end,
                  sensitive_content_present=any(call.get(key) is not None for key in SENSITIVE),
                  execution_authorized=False)
    result['event_key'] = _digest([VERSION, workspace_id, integration_id, event, call_id])
    result['projection_hash'] = _digest(result)
    return result


def reconcile_inbound_lifecycle(events):
    """Order-independent bounded metadata reconciliation, never qualification.

    A changed retry or contradictory terminal snapshot requires review. A missing
    call_started is allowed because failed/unconnected calls may omit that event.
    """
    if not isinstance(events, list) or not events or len(events) > 100:
        raise ValueError('INVALID_EVENT_BATCH')
    unique = {}; reasons = set(); scope = None
    expected = {'version','workspace_id','integration_id','call_id','event','agent_id','agent_version',
                'direction','call_status','start_timestamp','end_timestamp','sensitive_content_present',
                'execution_authorized','event_key','projection_hash'}
    for row in events:
        if not isinstance(row, dict) or set(row) != expected or row['version'] != VERSION or row['execution_authorized'] is not False:
            raise ValueError('INVALID_PROJECTED_EVENT')
        if type(row['sensitive_content_present']) is not bool:
            raise ValueError('INVALID_PROJECTED_EVENT')
        call = {key: row[key] for key in ('call_id','agent_id','agent_version','direction','call_status','start_timestamp','end_timestamp')}
        call.update(call_type='phone_call', to_number='+10000000000')
        if row['sensitive_content_present']:
            call['transcript'] = ''  # Boolean marker only; no original content.
        rebuilt = project_inbound_event({'event':row['event'],'call':call},
            workspace_id=row['workspace_id'], integration_id=row['integration_id'],
            agent_id=row['agent_id'], agent_version=row['agent_version'], acquisition_number='+10000000000')
        if rebuilt != row:
            raise ValueError('PROJECTED_EVENT_CHANGED')
        current = tuple(row[key] for key in ('workspace_id','integration_id','call_id','agent_id','agent_version'))
        if scope is not None and scope != current:
            raise ValueError('MIXED_CALL_SCOPE')
        scope = current
        if row['event'] not in LIFECYCLE or row['event_key'] != _digest([VERSION,row['workspace_id'],row['integration_id'],row['event'],row['call_id']]):
            raise ValueError('INVALID_EVENT_IDENTITY')
        prior = unique.get(row['event'])
        if prior and prior != row:
            reasons.add('CONFLICTING_EVENT_RETRY')
        else:
            unique[row['event']] = row
    terminal = [row for row in events if row['event'] != 'call_started']
    statuses = {row['call_status'] for row in terminal}
    if len(statuses) > 1:
        reasons.add('CONFLICTING_TERMINAL_STATUS')
    for field in ('start_timestamp','end_timestamp'):
        if len({row[field] for row in events if row[field] is not None}) > 1:
            reasons.add('CONFLICTING_CALL_TIMESTAMPS')
    if reasons:
        state = 'review'
    elif terminal:
        state = {'ended':'ended','error':'failed','not_connected':'not_connected'}[terminal[0]['call_status']]
    else:
        state = 'in_progress'
    return dict(version=VERSION, workspace_id=scope[0], integration_id=scope[1], call_id=scope[2],
                state=state, reason_codes=sorted(reasons), received_events=sorted(unique),
                analysis_event_received='call_analyzed' in unique,
                sensitive_content_present=any(row['sensitive_content_present'] for row in events),
                qualification_status='not_evaluated', permitted_actions=[], execution_authorized=False)
