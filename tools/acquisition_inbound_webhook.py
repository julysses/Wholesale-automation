"""Dedicated inbound authentication/configuration and metadata-only receipt client."""
from dataclasses import dataclass
import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx


class InboundUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class InboundConfig:
    secret: str
    service_key: str
    database_url: str
    workspace_id: str
    integration_id: str
    agent_id: str
    agent_version: int
    acquisition_number: str

    @property
    def routing(self):
        return {key: getattr(self, key) for key in ('workspace_id', 'integration_id',
                'agent_id', 'agent_version', 'acquisition_number')}


def load_config():
    """One explicit route per endpoint deployment; never infer scope from callers."""
    if any(os.getenv(key, '').lower() != 'true' for key in
           ('ACQUISITION_ENABLED', 'ACQUISITION_INBOUND_WEBHOOK_ENABLED')):
        raise InboundUnavailable('Inbound acquisition disabled')
    try:
        values = {key: os.environ['ACQUISITION_INBOUND_' + key.upper()] for key in
                  ('secret', 'service_key', 'workspace_id', 'integration_id', 'agent_id',
                   'agent_version', 'acquisition_number')}
        if not values['secret'].strip() or not values['service_key'].strip():
            raise ValueError()
        for key in ('workspace_id', 'integration_id'):
            if str(UUID(values[key])) != values[key]:
                raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', values['agent_id']):
            raise ValueError()
        if not re.fullmatch(r'0|[1-9][0-9]{0,9}', values['agent_version']):
            raise ValueError()
        values['agent_version'] = int(values['agent_version'])
        if values['agent_version'] > 2147483647:
            raise ValueError()
        if not re.fullmatch(r'\+[1-9][0-9]{7,14}', values['acquisition_number']):
            raise ValueError()
        url = os.environ['SUPABASE_URL'].rstrip('/')
        parsed = urlsplit(url)
        parsed.port
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError()
        return InboundConfig(database_url=url, **values)
    except (KeyError, ValueError):
        raise InboundUnavailable('Inbound acquisition configuration unavailable') from None


def verify_signature(raw, signature, secret):
    """Retell v=milliseconds,d=hex: HMAC over original bytes then timestamp."""
    match = re.fullmatch(r'v=([0-9]{1,16}),d=([0-9a-f]{64})', signature)
    if not match or abs(int(time.time() * 1000) - int(match[1])) > 300000:
        return False
    expected = hmac.new(secret.encode(), raw + match[1].encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, match[2])


async def accept_inbound_event(config, projection):
    """Single attempt. Unknown response is retryable by the signed provider."""
    try:
        async with httpx.AsyncClient(base_url=config.database_url + '/rest/v1/', timeout=10.0,
                follow_redirects=False, headers={'apikey': config.service_key,
                'Authorization': 'Bearer ' + config.service_key}) as client:
            response = await client.post('rpc/accept_acquisition_inbound_event', json={
                'p_integration': config.integration_id, 'p_number': config.acquisition_number,
                'p_data': projection})
        if response.status_code != 200:
            raise InboundUnavailable('Inbound receipt unconfirmed')
        result = response.json()
        if (not isinstance(result, dict) or set(result) != {'id', 'workspace_id', 'duplicate', 'execution_authorized'}
                or result['workspace_id'] != config.workspace_id or type(result['duplicate']) is not bool
                or result['execution_authorized'] is not False or not isinstance(result['id'], str)
                or str(UUID(result['id'])) != result['id']):
            raise InboundUnavailable('Inbound receipt unconfirmed')
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        raise InboundUnavailable('Inbound receipt unconfirmed') from None
