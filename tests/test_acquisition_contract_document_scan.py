"""Synthetic registry and local scanner; no installed daemon or activation."""
import asyncio
import hashlib
import json
import struct
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from tests.test_acquisition_contract_documents import artifact, BODY, NOW, uid
from tests.test_acquisition_evidence import Stream
from tests.test_acquisition_evidence_scan import daemon, VERSION, POLICY as MAIL_POLICY
from tools import acquisition_evidence_scan as scanning
from tools import acquisition_contract_documents as documents
from tools.acquisition_evidence import EvidenceUnavailable

POLICY = replace(MAIL_POLICY, valid_from=NOW-timedelta(hours=1), valid_until=NOW+timedelta(hours=1))


def registry(**changes):
    value = artifact().model_dump(mode='json')
    value.update(artifact_id=value.pop('id'), expected_sha256=value.pop('sha256'), expected_byte_size=value.pop('byte_size'),
                 retention_policy_id=str(uid(8)), status='pending_verification', bytes_verified=False,
                 legal_review_approved=False, execution_authorized=False, checked_at=NOW.isoformat())
    return value | changes


def registered(*, before=None, current=None, after=None, body=BODY, scope=None):
    requests = []
    states = iter([registry(**(before or {})), registry(**(current or {})), registry(**(after or {}))])
    def handle(request):
        requests.append(request)
        if request.method == 'POST':
            assert request.url.path == '/rest/v1/rpc/contract_document_state'
            assert json.loads(request.content) == {'p_workspace': str(uid(2)), 'p_contract': str(uid(3)), 'p_version': 2, 'p_artifact': str(uid(1))}
            return httpx.Response(200, headers={'content-type':'application/json'}, stream=Stream([json.dumps(next(states)).encode()]))
        return httpx.Response(200, headers={'content-type':'application/pdf'}, stream=Stream([body]))
    async def execute():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/', headers={'Authorization':'Bearer synthetic-user', 'apikey':'synthetic-public'}, transport=httpx.MockTransport(handle)) as client:
            return await documents.scan_registered_contract_document(client, uid(1), **(dict(workspace_id=uid(2), contract_id=uid(3), contract_version=2,
                purpose='purchase_contract', policy=POLICY, clock=lambda:NOW) | (scope or {})))
    return execute, requests


@pytest.mark.parametrize('verdict,status', [(b'stream: OK\0','no_detection'), (b'stream: Test FOUND\0','detected')])
def test_exact_version_and_bytes_are_scanned_without_approval(monkeypatch, verdict, status):
    writers = daemon(monkeypatch, [VERSION+b'\0', verdict, VERSION+b'\0'])
    execute, requests = registered()
    result = asyncio.run(execute())
    assert [r.method for r in requests] == ['POST','GET','POST','POST']
    assert all(r.headers['authorization'] == 'Bearer synthetic-user' for r in requests)
    assert bytes(writers[1].data) == b'zINSTREAM\0'+struct.pack('!I',len(BODY))+BODY+b'\0'*4
    assert result['contract_id'] == str(uid(3)) and result['contract_version'] == 2
    assert result['purpose'] == 'purchase_contract' and result['scan_status'] == status
    assert result['sha256'] == hashlib.sha256(BODY).hexdigest()
    assert result['registry_verifier_version'] == 'acquisition-contract-document-registry-v1'
    assert all(result[k] is False for k in ('verification_persisted','scan_persisted','preview_authorized','legal_review_approved','execution_authorized'))
    assert not {'body','url','campaign_id','content_approved','signature'} & result.keys()


@pytest.mark.parametrize('scope', [{'contract_version':True},{'contract_version':0},{'contract_version':2147483648},
    {'contract_id':'not-a-uuid'},{'workspace_id':'not-a-uuid'},{'purpose':'mail_content'},{'policy':None}])
def test_invalid_identity_never_reads_or_scans(monkeypatch, scope):
    writers = daemon(monkeypatch)
    execute, requests = registered(scope=scope)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not requests and not writers


@pytest.mark.parametrize('stage', ['before','current','after'])
@pytest.mark.parametrize('change', [{'contract_version':3},{'workspace_id':str(uid(9))},{'contract_id':str(uid(9))},
    {'purpose':'title_report'},{'status':'revoked','revoked_at':NOW.isoformat()}, {'status':'policy_review_required'},
    {'retain_until':NOW.isoformat()},{'checked_at':(NOW-timedelta(seconds=31)).isoformat()}])
def test_current_authority_required_around_bytes_and_scan(monkeypatch, stage, change):
    writers = daemon(monkeypatch)
    execute, requests = registered(**{stage:change})
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert len(requests) == {'before':1,'current':3,'after':4}[stage]
    assert len(writers) == (3 if stage == 'after' else 0)


def test_bad_bytes_never_reach_scanner(monkeypatch):
    writers = daemon(monkeypatch)
    execute, requests = registered(body=b'wrong')
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not writers and len(requests) == 2


def test_mail_and_contract_share_capacity_before_any_registry_read():
    assert scanning._CAPACITY.acquire(False) and scanning._CAPACITY.acquire(False)
    try:
        execute, requests = registered()
        with pytest.raises(EvidenceUnavailable, match='capacity'): asyncio.run(execute())
        assert not requests
    finally:
        scanning._CAPACITY.release(); scanning._CAPACITY.release()


def test_cancellation_erases_buffer_and_returns_shared_capacity(monkeypatch):
    collected = []
    real_verify = documents.verify_contract_document_bytes
    async def observe(*args, **kwargs):
        collected.append(kwargs['_observe_chunk'].__self__)
        return await real_verify(*args, **kwargs)
    monkeypatch.setattr(documents, 'verify_contract_document_bytes', observe)
    async def execute():
        entered = asyncio.Event()
        async def wait(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(scanning, 'scan_bytes', wait)
        run, _ = registered()
        task = asyncio.create_task(run())
        await entered.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(execute())
    assert collected == [bytearray()]
    assert scanning._CAPACITY.acquire(False) and scanning._CAPACITY.acquire(False)
    scanning._CAPACITY.release(); scanning._CAPACITY.release()


def test_store_preserves_contract_scope_and_policy(monkeypatch):
    from tools.acquisition_store import AcquisitionStore
    calls = []
    client = object()
    async def scan(actual, artifact_id, **kwargs):
        calls.append((actual, artifact_id, kwargs)); return {'scan_persisted':False}
    monkeypatch.setattr(documents, 'scan_registered_contract_document', scan)
    args = dict(workspace_id=uid(2), contract_id=uid(3), contract_version=2, purpose='purchase_contract', policy=POLICY)
    assert asyncio.run(AcquisitionStore(client).scan_contract_document(uid(1), **args)) == {'scan_persisted':False}
    assert calls == [(client, uid(1), args)]
