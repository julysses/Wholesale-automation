"""Internal local scanner observation; never a safe-preview or approval credential.

No environment activation, HTTP endpoint, filesystem document, daemon management,
TCP connection or privileged database credential. Deployment must supply reviewed
local daemon configuration, exact version pin and a short-lived validity window.
"""
import asyncio
import hashlib
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from threading import BoundedSemaphore
from uuid import UUID

from schemas.acquisition_evidence import MAX_EVIDENCE_BYTES
from tools.acquisition_evidence import EvidenceUnavailable, load_registry_state, utcnow, verify_evidence_bytes

_CAPACITY = BoundedSemaphore(2)
SCAN_SECONDS = 30
TOTAL_SECONDS = 60


@dataclass(frozen=True)
class ClamAVPolicy:
    socket_path: str
    expected_version: str
    policy_version: str
    valid_from: datetime
    valid_until: datetime

    def check(self, now):
        try:
            path = PurePosixPath(self.socket_path)
            valid = (isinstance(self.socket_path, str) and self.socket_path.startswith('/')
                     and str(path) == self.socket_path and '..' not in path.parts
                     and len(self.socket_path.encode()) <= 100 and '\0' not in self.socket_path
                     and isinstance(self.expected_version, str)
                     and re.fullmatch(r'ClamAV [0-9]+\.[0-9]+\.[0-9]+/[0-9]+/[\x20-\x7e]{1,100}', self.expected_version)
                     and isinstance(self.policy_version, str)
                     and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', self.policy_version)
                     and all(t.utcoffset() is not None for t in (now, self.valid_from, self.valid_until))
                     and self.valid_from <= now < self.valid_until
                     and self.valid_until - self.valid_from <= timedelta(hours=24))
        except (TypeError, ValueError, AttributeError):
            valid = False
        if not valid:
            raise EvidenceUnavailable('Reviewed evidence scanner configuration is unavailable')


async def _command(path, command, body=None):
    writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(path, limit=512)
        writer.write(command)
        await writer.drain()
        if body is not None:
            for offset in range(0, len(body), 65536):
                chunk = body[offset:offset + 65536]
                writer.write(struct.pack('!I', len(chunk)))
                writer.write(chunk)
                await writer.drain()
            writer.write(b'\0\0\0\0')
            await writer.drain()
        response = await reader.readuntil(b'\0')
        # A single INSTREAM/VERSION reply must terminate and then close. Reject
        # concatenated replies, unexpected diagnostic records and excess bytes.
        if len(response) > 512 or await reader.read(1):
            raise EvidenceUnavailable('Evidence scanner response is invalid')
        return response[:-1]
    finally:
        if writer is not None:
            writer.close()
            try:
                async with asyncio.timeout(1):
                    await writer.wait_closed()
            except (OSError, TimeoutError):
                pass


async def scan_bytes(body: bytes, policy: ClamAVPolicy, *, clock=utcnow):
    """Scan one immutable bounded buffer, pinning daemon version before and after.

    This function is internal; its returned dict is not a trusted caller attestation.
    The version pin includes the engine and signature database, but does not prove
    daemon settings or signature freshness. Those require deployment review.
    """
    if type(body) is not bytes or not 0 < len(body) <= MAX_EVIDENCE_BYTES or type(policy) is not ClamAVPolicy:
        raise EvidenceUnavailable('Evidence scanner input is invalid')
    started = clock()
    policy.check(started)
    try:
        async with asyncio.timeout(SCAN_SECONDS):
            expected = policy.expected_version.encode('ascii')
            if await _command(policy.socket_path, b'zVERSION\0') != expected:
                raise EvidenceUnavailable('Evidence scanner version is not approved')
            response = await _command(policy.socket_path, b'zINSTREAM\0', body)
            if response == b'stream: OK':
                status = 'no_detection'
            elif re.fullmatch(rb'stream: [A-Za-z0-9_.() -]{1,200} FOUND', response):
                status = 'detected'
            else:
                raise EvidenceUnavailable('Evidence scan is unconfirmed')
            if await _command(policy.socket_path, b'zVERSION\0') != expected:
                raise EvidenceUnavailable('Evidence scanner changed during scan')
            checked = clock()
            policy.check(checked)
            if checked < started:
                raise EvidenceUnavailable('Evidence scanner clock is invalid')
            return {'scan_status': status, 'scanner': 'clamav-instream-v1',
                    'scanner_version': policy.expected_version, 'scan_policy_version': policy.policy_version,
                    'scan_checked_at': checked.isoformat(), 'sha256': hashlib.sha256(body).hexdigest(),
                    'byte_size': len(body)}
    except (OSError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        raise EvidenceUnavailable('Evidence scanner is unavailable') from None


async def scan_registered_evidence(client, artifact_id, *, workspace_id, campaign_id, purpose,
                                   policy: ClamAVPolicy, clock=utcnow):
    """Registry → verified bytes → local scan → registry; no persistent clearance."""
    if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, campaign_id))
            or purpose not in ('mail_content', 'mail_destination') or type(policy) is not ClamAVPolicy):
        raise EvidenceUnavailable('Evidence scan identity is invalid')
    started = clock()
    policy.check(started)
    if not _CAPACITY.acquire(blocking=False):
        raise EvidenceUnavailable('Evidence scanner capacity is occupied')
    body = bytearray()
    try:
        async with asyncio.timeout(TOTAL_SECONDS):
            before = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                               campaign_id=campaign_id, purpose=purpose, clock=clock)
            receipt = await verify_evidence_bytes(client, before.descriptor(), workspace_id=workspace_id,
                                                  campaign_id=campaign_id, purpose=purpose, clock=clock,
                                                  _observe_chunk=body.extend)
            current = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                                campaign_id=campaign_id, purpose=purpose, clock=clock)
            if (before.model_dump(exclude={'checked_at'}) != current.model_dump(exclude={'checked_at'})
                    or current.checked_at < before.checked_at
                    or current.checked_at < datetime.fromisoformat(receipt['checked_at']) - timedelta(seconds=5)):
                raise EvidenceUnavailable('Evidence changed before scanning')
            scan = await scan_bytes(bytes(body), policy, clock=clock)
            body.clear()
            after = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                              campaign_id=campaign_id, purpose=purpose, clock=clock)
            completed = clock()
            policy.check(completed)
            if (before.model_dump(exclude={'checked_at'}) != after.model_dump(exclude={'checked_at'})
                    or after.checked_at < current.checked_at or completed < started
                    or datetime.fromisoformat(scan['scan_checked_at']) < datetime.fromisoformat(receipt['checked_at'])
                    or after.checked_at < datetime.fromisoformat(scan['scan_checked_at']) - timedelta(seconds=5)
                    or completed < datetime.fromisoformat(scan['scan_checked_at'])
                    or not after.available_at(completed)
                    or (scan['sha256'], scan['byte_size']) != (receipt['sha256'], receipt['byte_size'])):
                raise EvidenceUnavailable('Evidence changed during scanning')
            return {**receipt, **scan, 'status': 'scan_observed',
                    'registry_verifier_version': 'acquisition-evidence-registry-v1',
                    'retention_policy_id': str(after.retention_policy_id), 'registry_checked_at': after.checked_at.isoformat(),
                    'verification_persisted': False, 'scan_persisted': False, 'preview_authorized': False}
    except TimeoutError:
        raise EvidenceUnavailable('Evidence scan timed out') from None
    finally:
        body.clear()
        _CAPACITY.release()
