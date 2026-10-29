"""Synthetic daemon protocol and authenticated byte flow; no installed scanner."""
import asyncio
import hashlib
import json
import struct
import socket
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from tests.test_acquisition_evidence import ARTIFACT, AUTH, BODY, CAMPAIGN, NOW, WORKSPACE, Stream, registry_payload
from tools.acquisition_evidence import EvidenceUnavailable
from tools import acquisition_evidence_scan as scanning
from tools.acquisition_evidence_scan import ClamAVPolicy, scan_bytes, scan_registered_evidence

VERSION = b'ClamAV 1.4.3/12345/Thu Oct 29 00:00:00 2026'
POLICY = ClamAVPolicy('/run/clamav/clamd.sock', VERSION.decode(), 'reviewed-test-v1', NOW-timedelta(hours=1), NOW+timedelta(hours=1))


class Writer:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        await asyncio.sleep(0)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def daemon(monkeypatch, replies=None):
    replies = list(replies if replies is not None else [VERSION+b'\0', b'stream: OK\0', VERSION+b'\0'])
    writers = []

    async def connect(path, *, limit):
        assert path == POLICY.socket_path and limit == 512
        reader = asyncio.StreamReader(limit=limit)
        reader.feed_data(replies.pop(0))
        reader.feed_eof()
        writer = Writer()
        writers.append(writer)
        return reader, writer

    monkeypatch.setattr(scanning.asyncio, 'open_unix_connection', connect)
    return writers


def scan(body=BODY, policy=POLICY, clock=lambda: NOW):
    return asyncio.run(scan_bytes(body, policy, clock=clock))


def test_exact_version_pin_big_endian_frames_and_no_authority(monkeypatch):
    writers = daemon(monkeypatch)
    body = b'x'*70000
    result = scan(body)
    assert [bytes(w.data[:9]) for w in writers] == [b'zVERSION\0', b'zINSTREAM', b'zVERSION\0']
    assert bytes(writers[1].data) == b'zINSTREAM\0'+struct.pack('!I',65536)+body[:65536]+struct.pack('!I',4464)+body[65536:]+b'\0'*4
    assert all(w.closed for w in writers)
    assert result['scan_status'] == 'no_detection'
    assert result['sha256'] == hashlib.sha256(body).hexdigest() and result['byte_size'] == 70000
    assert result['scanner_version'] == VERSION.decode()
    assert not {'body','url','signature','approved','safe'} & result.keys()


def test_detection_does_not_expose_signature_or_claim_clearance(monkeypatch):
    daemon(monkeypatch, [VERSION+b'\0', b'stream: Synthetic.Test-Signature FOUND\0', VERSION+b'\0'])
    result = scan()
    assert result['scan_status'] == 'detected'
    assert 'Synthetic.Test-Signature' not in json.dumps(result)


@pytest.mark.parametrize('response', [b'', b'stream: OK', b'stream: OK\0extra', b'stream: OK\n',
    b'stream: OK\0stream: Bad FOUND\0', b'other: OK\0', b'INSTREAM size limit exceeded. ERROR\0',
    b'stream: Access denied ERROR\0', b'stream: \nprivate FOUND\0', b'x'*513+b'\0'])
def test_ambiguous_error_truncated_or_excess_response_never_clears(monkeypatch, response):
    writers = daemon(monkeypatch, [VERSION+b'\0', response])
    with pytest.raises(EvidenceUnavailable): scan()
    assert all(w.closed for w in writers)


@pytest.mark.parametrize('position', [0,2])
def test_unapproved_or_changed_version_is_rejected(monkeypatch, position):
    replies = [VERSION+b'\0',b'stream: OK\0',VERSION+b'\0']
    replies[position] = VERSION.replace(b'/12345/',b'/12346/')+b'\0'
    writers = daemon(monkeypatch,replies)
    with pytest.raises(EvidenceUnavailable): scan()
    assert len(writers) == position+1 and all(w.closed for w in writers)


@pytest.mark.parametrize('changes', [dict(socket_path='127.0.0.1:3310'),dict(socket_path='/run/../other'),
    dict(socket_path='/run//clamd.sock'),dict(socket_path='/run/evil\0'),dict(socket_path='/'+'a'*101),
    dict(expected_version='unknown'),dict(expected_version='ClamAV 1.4.3/12345/\n'),dict(policy_version=''),
    dict(valid_until=NOW),dict(valid_from=NOW+timedelta(seconds=1)),dict(valid_until=NOW+timedelta(days=2)),
    dict(valid_until=NOW.replace(tzinfo=None))])
def test_invalid_expired_or_unbounded_config_prevents_connection(monkeypatch, changes):
    writers = daemon(monkeypatch)
    with pytest.raises(EvidenceUnavailable): scan(policy=replace(POLICY, **changes))
    assert writers == []


@pytest.mark.parametrize('body', [b'',bytearray(BODY),b'x'*(10*1024*1024+1),'text'])
def test_input_is_bounded_immutable_bytes(monkeypatch, body):
    writers = daemon(monkeypatch)
    with pytest.raises(EvidenceUnavailable): scan(body)
    assert not writers


def test_policy_expiry_during_scan_and_clock_regression(monkeypatch):
    for completed in (POLICY.valid_until,NOW-timedelta(seconds=1)):
        daemon(monkeypatch)
        times = iter([NOW,completed])
        with pytest.raises(EvidenceUnavailable): scan(clock=lambda:next(times))


def test_timeout_cancellation_and_socket_failure_are_closed(monkeypatch):
    async def execute(cancel=False):
        reader = asyncio.StreamReader(limit=512)
        writer = Writer()
        async def connect(*args,**kwargs): return reader,writer
        monkeypatch.setattr(scanning.asyncio,'open_unix_connection',connect)
        monkeypatch.setattr(scanning,'SCAN_SECONDS',0.02)
        task = asyncio.create_task(scan_bytes(BODY,POLICY,clock=lambda:NOW))
        await asyncio.sleep(0.005)
        if cancel: task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else EvidenceUnavailable): await task
        assert writer.closed
    asyncio.run(execute())
    asyncio.run(execute(True))
    async def failed(*args,**kwargs): raise OSError('secret socket failure')
    monkeypatch.setattr(scanning.asyncio,'open_unix_connection',failed)
    with pytest.raises(EvidenceUnavailable,match='^Evidence scanner is unavailable$'): scan()


def registered(*, after=None, current=None, body=BODY, policy=POLICY):
    requests = []
    states = iter([registry_payload(),current or registry_payload(),after or registry_payload()])
    def handle(request):
        requests.append(request)
        if request.method == 'POST':
            return httpx.Response(200,headers={'content-type':'application/json'},stream=Stream([json.dumps(next(states)).encode()]))
        return httpx.Response(200,headers={'content-type':'text/plain'},stream=Stream([body]))
    async def execute():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',headers=AUTH,transport=httpx.MockTransport(handle)) as client:
            return await scan_registered_evidence(client,ARTIFACT,workspace_id=WORKSPACE,campaign_id=CAMPAIGN,
                                                   purpose='mail_content',policy=policy,clock=lambda:NOW)
    return execute,requests


@pytest.mark.parametrize('verdict', [b'stream: OK\0',b'stream: Test FOUND\0'])
def test_registry_flow_binds_scanned_bytes_and_retains_false_authority(monkeypatch,verdict):
    writers = daemon(monkeypatch,[VERSION+b'\0',verdict,VERSION+b'\0'])
    execute,requests = registered()
    result = asyncio.run(execute())
    assert [r.method for r in requests] == ['POST','GET','POST','POST']
    assert all(r.headers['authorization'] == AUTH['Authorization'] for r in requests)
    assert bytes(writers[1].data) == b'zINSTREAM\0'+struct.pack('!I',len(BODY))+BODY+b'\0'*4
    assert result['status'] == 'scan_observed' and result['scan_status'] == ('no_detection' if b'OK' in verdict else 'detected')
    assert all(result[k] is False for k in ('verification_persisted','scan_persisted','preview_authorized','content_approved','execution_authorized'))
    assert result['sha256'] == hashlib.sha256(BODY).hexdigest()


@pytest.mark.parametrize('changes', [dict(status='revoked',revoked_at=NOW.isoformat()),dict(status='policy_review_required'),
    dict(expected_sha256='b'*64),dict(retention_policy_id=str(ARTIFACT)),dict(retain_until=NOW.isoformat())])
def test_changed_registry_after_scan_returns_no_receipt(monkeypatch,changes):
    daemon(monkeypatch)
    execute,_ = registered(after=registry_payload(**changes))
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())


def test_hash_mismatch_never_sends_bytes_to_scanner(monkeypatch):
    writers = daemon(monkeypatch)
    execute,requests = registered(body=b'wrong')
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not writers and [r.method for r in requests] == ['POST','GET']


def test_revocation_before_scan_never_sends_verified_bytes(monkeypatch):
    writers = daemon(monkeypatch)
    execute,requests = registered(current=registry_payload(status='revoked',revoked_at=NOW.isoformat()))
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not writers and len(requests) == 3


def test_real_local_socket_framing_and_close(monkeypatch):
    """Paired Unix sockets preserve the offline guard; synthetic daemon only."""
    async def execute():
        observed = []
        finished = []
        async def handler(reader,writer):
            try:
                command = await reader.readuntil(b'\0')
                if command == b'zVERSION\0':
                    writer.write(VERSION+b'\0')
                else:
                    assert command == b'zINSTREAM\0'
                    payload = bytearray()
                    while True:
                        size = struct.unpack('!I',await reader.readexactly(4))[0]
                        if not size: break
                        assert 0 < size <= 65536
                        payload.extend(await reader.readexactly(size))
                    observed.append(bytes(payload))
                    writer.write(b'stream: OK\0')
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                finished.append(True)
        tasks = []
        async def paired_connection(path, *, limit):
            assert path == POLICY.socket_path
            client_socket, server_socket = socket.socketpair(socket.AF_UNIX)
            server_reader, server_writer = await asyncio.open_connection(sock=server_socket)
            tasks.append(asyncio.create_task(handler(server_reader, server_writer)))
            return await asyncio.open_connection(sock=client_socket, limit=limit)
        monkeypatch.setattr(scanning.asyncio, 'open_unix_connection', paired_connection)
        result = await scan_bytes(BODY,POLICY,clock=lambda:NOW)
        await asyncio.gather(*tasks)
        assert result['scan_status'] == 'no_detection' and observed == [BODY] and len(finished) == 3
    asyncio.run(execute())


def test_outer_cancellation_releases_capacity_and_clears_collected_bytes(monkeypatch):
    collected = []
    real_read = scanning.verify_evidence_bytes
    async def observe(*args,**kwargs):
        collected.append(kwargs['_observe_chunk'].__self__)
        return await real_read(*args,**kwargs)
    entered = None
    async def waiting(*args,**kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(scanning,'verify_evidence_bytes',observe)
    monkeypatch.setattr(scanning,'scan_bytes',waiting)
    async def execute():
        nonlocal entered
        entered = asyncio.Event()
        run,_ = registered()
        task = asyncio.create_task(run())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(execute())
    assert collected == [bytearray()]
    assert scanning._CAPACITY.acquire(False) and scanning._CAPACITY.acquire(False)
    scanning._CAPACITY.release(); scanning._CAPACITY.release()


def test_process_capacity_denies_before_registry_and_is_released_on_error(monkeypatch):
    assert scanning._CAPACITY.acquire(False) and scanning._CAPACITY.acquire(False)
    try:
        execute,requests = registered()
        with pytest.raises(EvidenceUnavailable,match='capacity'): asyncio.run(execute())
        assert not requests
    finally:
        scanning._CAPACITY.release(); scanning._CAPACITY.release()
    daemon(monkeypatch,[b'bad\0'])
    execute,_ = registered()
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert scanning._CAPACITY.acquire(False) and scanning._CAPACITY.acquire(False)
    scanning._CAPACITY.release(); scanning._CAPACITY.release()
