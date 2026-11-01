"""Real disposable SQL + synthetic Storage/daemon transport; no hosted acceptance."""
import asyncio
import hashlib
import json
import struct
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from acquisition_retained_refresh_tests import RetainedRefreshTests
from acquisition_contract_document_tests import DOC_POLICY, DRAFT
from acquisition_contract_observation_tests import KEY
from test_acquisition_workspace import ADMIN, WORKSPACE, main
from tools.acquisition_contract_attestation import ContractVerificationSigningKey, build_contract_scan_attestation
from tools.acquisition_contract_documents import scan_registered_contract_document
from tools.acquisition_evidence_journal import EvidenceJournal
from tools.acquisition_evidence_persistence import EvidencePersistenceUnconfirmed
from tools.acquisition_evidence_scan import ClamAVPolicy
from tools.acquisition_store import AcquisitionStore
from tests.test_acquisition_evidence_scan import daemon, VERSION

# Capture before the inherited fixture installs its general application transport.
ASYNC_CLIENT = httpx.AsyncClient

ARTIFACT = 'af136000-0000-4000-8000-000000000001'
OBSERVATION = 'af136000-0000-4000-8000-000000000002'
BODY = b'%PDF-1.7\nSynthetic retained agreement for scan recovery rehearsal.\n%%EOF\n'


class Stream(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        yield self.body


class RetainedScanJourneyCases:
    def test_signature_retained_scan_journey_committed_loss_recovers_without_rescan(self):
        digest = hashlib.sha256(BODY).hexdigest()
        self.sql(f"SELECT public.register_contract_document('{ARTIFACT}','{WORKSPACE}','{DRAFT}',2,"
                 f"'purchase_contract','{digest}',{len(BODY)},'application/pdf','{DOC_POLICY}',"
                 "'Synthetic retained original bytes for post-handoff recovery.')", user=ADMIN)
        self.post_handoff()
        history = self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r')
        state_query = (f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{ARTIFACT}')")
        requests, sent, receipts = [], [], []

        def transport(request):
            self.assertEqual(request.headers['authorization'], 'Bearer synthetic-admin')
            requests.append((request.method, request.url.path))
            if request.method == 'GET':
                self.assertTrue(request.url.path.startswith('/storage/v1/object/authenticated/acquisition-evidence/'))
                self.assertIn(ARTIFACT, request.url.path)
                return httpx.Response(200, headers={'content-type': 'application/pdf'}, stream=Stream(BODY))
            body = json.loads(request.content)
            if request.url.path == '/rest/v1/rpc/contract_document_state':
                self.assertEqual(body, dict(p_workspace=WORKSPACE, p_contract=DRAFT, p_version=2, p_artifact=ARTIFACT))
                result = json.loads(self.sql(state_query, user=ADMIN))
            elif request.url.path == '/rest/v1/rpc/record_contract_document_verification':
                sent.append(request.content)
                result = self.record_contract_scan(body)
                receipts.append(result)
                if len(sent) == 1:
                    raise httpx.ReadTimeout('Synthetic lost response after real SQL commit')
            else:
                raise AssertionError('Unexpected retained-document destination')
            return httpx.Response(200, headers={'content-type': 'application/json'}, stream=Stream(json.dumps(result).encode()))

        async def journey(directory):
            now = datetime.now(timezone.utc)
            policy = ClamAVPolicy('/run/clamav/clamd.sock', VERSION.decode(), 'synthetic-v1',
                                  now-timedelta(hours=1), now+timedelta(hours=1))
            key = ContractVerificationSigningKey(UUID(KEY), UUID(WORKSPACE), bytes.fromhex('ab'*32),
                frozenset({'purchase_contract'}), VERSION.decode(), 'synthetic-v1',
                now-timedelta(hours=1), now+timedelta(hours=1))
            scope = dict(workspace_id=UUID(WORKSPACE), contract_id=UUID(DRAFT), contract_version=2,
                         purpose='purchase_contract', artifact_id=UUID(ARTIFACT), actor_id=UUID(ADMIN), session_id=UUID(ADMIN))
            async with ASYNC_CLIENT(base_url='https://retained.test/rest/v1/', trust_env=False,
                    transport=httpx.MockTransport(transport), headers={'Authorization': 'Bearer synthetic-admin', 'apikey': 'synthetic'}) as client:
                observed = await scan_registered_contract_document(client, UUID(ARTIFACT), workspace_id=UUID(WORKSPACE),
                    contract_id=UUID(DRAFT), contract_version=2, purpose='purchase_contract', policy=policy)
                self.assertEqual(observed['sha256'], digest)
                signed = build_contract_scan_attestation(observed, request_id=UUID(OBSERVATION),
                    actor_id=UUID(ADMIN), session_id=UUID(ADMIN), key=key)
                journal = EvidenceJournal(directory)
                journal.prepare(signed)
                store = AcquisitionStore(client)
                with self.assertRaises(EvidencePersistenceUnconfirmed):
                    await store.persist_journaled_contract_observation(journal, UUID(OBSERVATION), **scope)
                reopened = EvidenceJournal(directory)
                self.assertEqual(reopened.load(UUID(OBSERVATION)), (signed, 'unconfirmed'))
                # Recovery remains a historical receipt even after scanner authority is revoked.
                self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
                before_retry = len(requests)
                receipt = await store.persist_journaled_contract_observation(reopened, UUID(OBSERVATION), **scope)
                self.assertEqual(len(requests), before_retry+1)
                self.assertTrue(receipt['duplicate'])
                self.assertFalse(receipt['legal_review_approved'])
                self.assertFalse(receipt['execution_authorized'])
                self.assertEqual(reopened.load(UUID(OBSERVATION))[1], 'confirmed')

        with tempfile.TemporaryDirectory(prefix='retained-scan-recovery-') as directory, pytest.MonkeyPatch.context() as patch:
            writers = daemon(patch)
            asyncio.run(journey(Path(directory)))
            self.assertEqual(len(writers), 3)
            self.assertEqual(bytes(writers[1].data), b'zINSTREAM\0'+struct.pack('!I', len(BODY))+BODY+b'\0'*4)
        self.assertEqual(sent[0], sent[1])
        self.assertEqual([r['duplicate'] for r in receipts], [False, True])
        self.assertEqual(history, self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r'))
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"), 'disposition_review')
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_evidence_verifications WHERE id='{OBSERVATION}'"), '1')


class RetainedScanJourneyTests(RetainedScanJourneyCases, RetainedRefreshTests):
    pass


if __name__ == '__main__':
    raise SystemExit(main(RetainedScanJourneyTests, [n for n in RetainedScanJourneyCases.__dict__ if n.startswith('test_signature_retained_scan_journey_')]))
