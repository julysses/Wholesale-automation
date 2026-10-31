"""Explicitly gated public portal runtime; no automatic provisioning or activation."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import os
import re

from fastapi import HTTPException
import httpx

from tools.acquisition_portal_bot import BotConfig, BotUnavailable, configured_bot


@dataclass(frozen=True)
class PortalRuntime:
    bot: BotConfig
    site_key: str
    network_key: bytes = field(repr=False)
    database_url: str
    database_key: str = field(repr=False)


def configured_portal(environ=None):
    env = os.environ if environ is None else environ
    if any(env.get(name) != 'true' for name in (
            'ACQUISITION_ENABLED', 'ACQUISITION_PORTAL_ENABLED', 'ACQUISITION_PORTAL_TRANSPORT_APPROVED')):
        raise HTTPException(404, 'Offer request form is unavailable')
    try:
        bot = configured_bot(env)
        site_key = env.get('ACQUISITION_PORTAL_TURNSTILE_SITE_KEY', '')
        network = env.get('ACQUISITION_PORTAL_NETWORK_KEY_HEX', '')
        url = env.get('SUPABASE_URL', '').rstrip('/')
        key = env.get('SUPABASE_SERVICE_ROLE_KEY', '')
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', site_key)
                or not re.fullmatch(r'[a-fA-F0-9]{64,256}', network) or len(network) % 2
                or not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co', url)
                or not key or len(key) > 16384 or any(c.isspace() for c in key)):
            raise ValueError('Missing configuration')
        return PortalRuntime(bot, site_key, bytes.fromhex(network), url, key)
    except (ValueError, BotUnavailable):
        raise HTTPException(503, 'Offer request form is temporarily unavailable') from None


class PortalStore:
    """Only the three reviewed RPCs; fixed destination, bounded reads, no retries."""
    def __init__(self, client):
        self.client = client

    async def request(self, method, path, *, body):
        if method != 'POST' or path not in {
                'rpc/admit_acquisition_portal_request', 'rpc/read_acquisition_public_form',
                'rpc/complete_acquisition_portal_request'}:
            raise HTTPException(503, 'Offer request operation is unavailable')

        async def send():
            async with self.client.stream(method, path, json=body) as response:
                if response.status_code >= 300:
                    # No SQL details or existence information in public errors.
                    if response.status_code in (400, 401, 403, 404):
                        raise HTTPException(404, 'Offer request form is unavailable')
                    if response.status_code == 409:
                        raise HTTPException(409, 'Request changed; preserve your inquiry and review the form')
                    raise HTTPException(503, 'Request was not confirmed; preserve the same inquiry for retry')
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 65536:
                        raise ValueError('Oversized database response')
                    content.extend(chunk)
                return json.loads(content)
        try:
            return await asyncio.wait_for(send(), timeout=12)
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            raise HTTPException(503, 'Request was not confirmed; preserve the same inquiry for retry') from None


@asynccontextmanager
async def open_portal_store(config):
    async with httpx.AsyncClient(base_url=config.database_url+'/rest/v1/', timeout=10,
                                follow_redirects=False, trust_env=False,
                                headers={'apikey': config.database_key,
                                         'Authorization': 'Bearer '+config.database_key}) as client:
        yield PortalStore(client)
