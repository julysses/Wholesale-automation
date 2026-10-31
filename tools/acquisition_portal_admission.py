"""Durable portal admission client. No public receiver or provider execution."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import re
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator


class PortalAdmission(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    attempt_id: UUID
    form_key: str
    purpose: Literal['display', 'submit']
    admitted: StrictBool
    checked_at: AwareDatetime
    expires_at: AwareDatetime | None
    retry_after_seconds: int = Field(strict=True, ge=0, le=60)
    policy_revision: int = Field(strict=True, ge=1)

    @model_validator(mode='after')
    def coherent(self):
        if self.admitted:
            if self.expires_at != self.checked_at + timedelta(seconds=30) or self.retry_after_seconds != 0:
                raise ValueError('Invalid admission lifetime')
        elif self.expires_at is not None or self.retry_after_seconds < 1:
            raise ValueError('Invalid denial')
        return self


def portal_network_hash(address: str, key: bytes) -> str:
    """Pseudonymous identity from an already trusted transport address.

    Never pass an unvalidated Forwarded/X-Forwarded-For header. Deployment must
    verify proxy trust before exposing the receiver. IPv6 uses a /64 grouping;
    IPv4-mapped IPv6 is normalized to the same IPv4 identity. No raw IP is saved.
    """
    if not isinstance(key, bytes) or not 32 <= len(key) <= 128:
        raise ValueError('Portal network key is not configured')
    if not isinstance(address, str) or '%' in address or len(address) > 45:
        raise ValueError('Trusted client address required')
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        raise ValueError('Trusted client address required') from None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    identity = ('v4:' + str(ip) if isinstance(ip, ipaddress.IPv4Address)
                else 'v6:' + str(ipaddress.ip_network((ip, 64), strict=False)))
    return hmac.new(key, ('portal-network-v1:' + identity).encode('ascii'), hashlib.sha256).hexdigest()


async def admit_portal_request(store, *, form_key: str, network_hash: str, purpose: str,
                               submission_id: UUID | None = None, request_hash: str | None = None, clock=None):
    valid = (isinstance(form_key, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', form_key)
             and isinstance(network_hash, str) and re.fullmatch('[a-f0-9]{64}', network_hash)
             and ((purpose == 'display' and submission_id is None and request_hash is None)
                  or (purpose == 'submit' and isinstance(submission_id, UUID)
                      and isinstance(request_hash, str) and re.fullmatch('[a-f0-9]{64}', request_hash))))
    if not valid:
        raise HTTPException(422, 'Portal request identity is invalid', headers={'Cache-Control': 'no-store'})
    attempt = uuid4()  # New for every HTTP attempt; never accepted from a browser.
    try:
        raw = await store.request('POST', 'rpc/admit_acquisition_portal_request', body={
            'p_attempt': str(attempt), 'p_form_key': form_key, 'p_network_hash': network_hash, 'p_purpose': purpose,
            'p_submission': str(submission_id) if submission_id else None, 'p_request_hash': request_hash})
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise
    try:
        result = PortalAdmission.model_validate(raw)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        if ((result.attempt_id, result.form_key, result.purpose) != (attempt, form_key, purpose)
                or now.utcoffset() is None or not now-timedelta(seconds=15) <= result.checked_at <= now+timedelta(seconds=5)
                or (result.admitted and result.expires_at <= now)):
            raise ValueError('Stale or mismatched admission')
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(503, 'Portal capacity could not be confirmed', headers={'Cache-Control': 'no-store'}) from None
    if not result.admitted:
        raise HTTPException(429, 'Please wait before trying again',
                            headers={'Cache-Control': 'no-store', 'Retry-After': str(result.retry_after_seconds)})
    return result
