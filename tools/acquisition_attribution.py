"""Read-only attribution projection over immutable Facebook retrieval evidence.

No campaign matching, spend estimation, permission inference or external requests.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

ID_FIELDS = ('id', 'form_id', 'campaign_id', 'adset_id', 'ad_id')


def facebook_attribution(prepared):
    result = {'provider': 'facebook', 'projection_version': 'facebook-attribution-v1',
              'status': 'requires_review', 'reason_codes': [], 'missing_fields': [],
              'external_lead_id': None, 'form_id': None, 'campaign_id': None,
              'adset_id': None, 'ad_id': None, 'submitted_at': None,
              'is_organic': None, 'platform': None, 'evidence_hash': None,
              'internal_campaign_id': None, 'spend_cents': None, 'currency': None}
    if not isinstance(prepared, dict) or prepared.get('source_type') != 'facebook_native_form':
        result['reason_codes'] = ['UNSUPPORTED_SOURCE']
        return result
    evidence = prepared.get('provider_evidence')
    fingerprint = prepared.get('provider_evidence_hash')
    try:
        encoded = json.dumps(evidence, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        valid = (isinstance(evidence, dict) and len(encoded) <= 524288 and isinstance(fingerprint, str)
                 and bool(re.fullmatch('[a-f0-9]{64}', fingerprint))
                 and hmac.compare_digest(hashlib.sha256(encoded).hexdigest(), fingerprint))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        result['reason_codes'] = ['PROVIDER_EVIDENCE_UNVERIFIED']
        return result
    result['evidence_hash'] = fingerprint
    for key in ID_FIELDS:
        value = evidence.get(key)
        destination = 'external_lead_id' if key == 'id' else key
        if value is None or value == '':
            result['missing_fields'].append(destination)
        elif not isinstance(value, str) or not re.fullmatch('[0-9]{1,200}', value):
            result['reason_codes'].append('INVALID_'+destination.upper())
        else:
            result[destination] = value
    if result['external_lead_id'] != prepared.get('external_lead_id') or result['form_id'] != prepared.get('provider_form_id'):
        result['reason_codes'].append('INTAKE_IDENTITY_MISMATCH')
    stamp = evidence.get('created_time')
    if stamp is None or stamp == '':
        result['missing_fields'].append('submitted_at')
    else:
        try:
            if not isinstance(stamp, str) or len(stamp) > 200:
                raise ValueError('Invalid timestamp')
            value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if value.tzinfo is None:
                raise ValueError('Timezone required')
            result['submitted_at'] = value.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError):
            result['reason_codes'].append('INVALID_SUBMITTED_AT')
    organic = evidence.get('is_organic')
    if organic is None:
        result['missing_fields'].append('is_organic')
    elif type(organic) is not bool:
        result['reason_codes'].append('INVALID_IS_ORGANIC')
    else:
        result['is_organic'] = organic
    platform = evidence.get('platform')
    if platform is None or platform == '':
        result['missing_fields'].append('platform')
    elif not isinstance(platform, str) or not re.fullmatch('[A-Za-z0-9_ -]{1,64}', platform):
        result['reason_codes'].append('INVALID_PLATFORM')
    else:
        result['platform'] = platform
    result['status'] = 'requires_review' if result['reason_codes'] else 'partial' if result['missing_fields'] else 'available'
    return result
