"""Server-only Turnstile adapter; no public route, receipt write or activation.

A caller must first obtain durable admission, then supply a server-prepared
request hash. Verification is anti-abuse evidence, never contact permission.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from typing import Mapping
from uuid import UUID, uuid5

import httpx

SITEVERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
ACTION = 'acquisition_offer'
_NAMESPACE = UUID('32c074f8-362c-4d9a-a84c-1851f32e67b4')
_MAX_RESPONSE = 16384


class BotUnavailable(Exception):
    """Configuration, transport or response uncertainty: do not accept inquiry."""


class BotRejected(Exception):
    """A new browser challenge is required; no provider detail is public."""


@dataclass(frozen=True)
class BotConfig:
    secret: str = field(repr=False)
    hostname: str

    def __post_init__(self):
        if (not isinstance(self.secret, str) or not 1 <= len(self.secret) <= 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in self.secret)
                or not isinstance(self.hostname, str) or len(self.hostname) > 253
                or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', self.hostname)):
            raise BotUnavailable('Bot verification is not configured')


def configured_bot(environ: Mapping[str, str] | None = None) -> BotConfig:
    env = os.environ if environ is None else environ
    if env.get('ACQUISITION_PORTAL_BOT_ENABLED') != 'true':
        raise BotUnavailable('Bot verification is not enabled')
    return BotConfig(secret=env.get('ACQUISITION_PORTAL_TURNSTILE_SECRET', ''),
                     hostname=env.get('ACQUISITION_PORTAL_HOSTNAME', ''))


@dataclass(frozen=True)
class BotVerification:
    submission_id: UUID
    request_hash: str
    token_hash: str
    verification_id: UUID
    hostname: str
    action: str
    challenged_at: datetime
    verified_at: datetime
    expires_at: datetime
    provider: str = 'turnstile'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Ambiguous response')
        result[key] = value
    return result


def _interpret(raw: bytes, *, config: BotConfig, submission_id: UUID, request_hash: str,
               token_hash: str, verification_id: UUID, now: datetime) -> BotVerification:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid JSON number')))
        if not isinstance(value, dict) or type(value.get('success')) is not bool:
            raise ValueError('Invalid verification result')
        errors = value.get('error-codes', [])
        if not isinstance(errors, list) or any(not isinstance(e, str) for e in errors):
            raise ValueError('Invalid provider errors')
        if not value['success']:
            if any(e in {'internal-error', 'missing-input-secret', 'invalid-input-secret', 'bad-request'} for e in errors):
                raise BotUnavailable('Bot verification is unavailable')
            raise BotRejected('Complete a new verification challenge')
        if errors:
            raise ValueError('Conflicting verification result')
        if (value.get('hostname') != config.hostname or value.get('action') != ACTION
                or value.get('cdata') != str(submission_id)):
            raise BotRejected('Verification does not match this request')
        stamp = value.get('challenge_ts')
        if not isinstance(stamp, str) or len(stamp) > 64:
            raise ValueError('Invalid challenge time')
        challenged = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if challenged.tzinfo is None or challenged.utcoffset() is None:
            raise ValueError('Challenge time must include timezone')
        challenged = challenged.astimezone(timezone.utc)
        expires = challenged + timedelta(seconds=300)
        if challenged > now + timedelta(seconds=5) or expires <= now:
            raise BotRejected('Complete a new verification challenge')
        return BotVerification(submission_id, request_hash, token_hash, verification_id,
                               config.hostname, ACTION, challenged, now, expires)
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise BotUnavailable('Bot verification returned an invalid response') from None


async def verify_portal_bot(config: BotConfig, *, token: str, submission_id: UUID, request_hash: str,
                            transport: httpx.AsyncBaseTransport | None = None) -> BotVerification:
    """One bounded provider attempt, exact retry identity, no automatic retries.

    A fresh challenge for an uncertain inquiry may have a new token; the inquiry
    keeps its submission UUID and exact payload for database reconciliation.
    Never use this result alone to authorize a database write or outreach.
    """
    if (not isinstance(token, str) or not 1 <= len(token) <= 2048
            or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise BotRejected('Complete a new verification challenge')
    if not isinstance(submission_id, UUID) or not isinstance(request_hash, str) or not re.fullmatch('[0-9a-f]{64}', request_hash):
        raise BotUnavailable('A prepared inquiry identity is required')
    token_hash = hashlib.sha256(token.encode('ascii')).hexdigest()
    verification_id = uuid5(_NAMESPACE, f'{submission_id}:{request_hash}:{token_hash}')
    try:
        async with asyncio.timeout(8):
            # Dedicated client prevents inherited database credentials, proxy
            # environment, redirects and automatic transport retries.
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False, transport=transport) as client:
                async with client.stream('POST', SITEVERIFY, json={
                    'secret': config.secret, 'response': token, 'idempotency_key': str(verification_id),
                }, headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'}) as response:
                    if (response.status_code != 200
                            or response.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json'
                            or response.headers.get('content-encoding', 'identity').lower() != 'identity'):
                        raise BotUnavailable('Bot verification is unavailable')
                    size = response.headers.get('content-length')
                    if size is not None and (len(size) > 6 or not size.isdecimal() or int(size) > _MAX_RESPONSE):
                        raise BotUnavailable('Bot verification response is unavailable')
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > _MAX_RESPONSE:
                            raise BotUnavailable('Bot verification response is unavailable')
                        body.extend(chunk)
                    return _interpret(bytes(body), config=config, submission_id=submission_id, request_hash=request_hash,
                                      token_hash=token_hash, verification_id=verification_id, now=datetime.now(timezone.utc))
    except (httpx.HTTPError, TimeoutError):
        raise BotUnavailable('Bot verification is unavailable') from None
