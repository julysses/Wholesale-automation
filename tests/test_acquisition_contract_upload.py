"""Contract transport against synthetic Storage; does not establish live write authority."""
import asyncio
import json
import httpx
import pytest
from tests.test_acquisition_evidence_upload import Storage, Source, WORKSPACE, CAMPAIGN, ARTIFACT, AUTH, NOW, BODY
from tools.acquisition_contract_documents import upload_registered_contract_document
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed


class ContractStorage(Storage):
    version=1
    async def handle(self, request):
        if request.url.path=='/rest/v1/rpc/contract_document_state':
            self.requests.append(request)
            assert request.headers['authorization']==AUTH['Authorization']
            assert set(json.loads(request.content))=={'p_workspace','p_contract','p_version','p_artifact'}
            state=self.state();state.pop('campaign_id');state.pop('content_approved')
            state.update(contract_id=str(CAMPAIGN),contract_version=self.version,purpose='purchase_contract',legal_review_approved=False)
            return self.reply(200,json.dumps(state).encode())
        return await super().handle(request)

    async def upload(self, source=None, **changes):
        source=Source() if source is None else source
        scope=dict(workspace_id=WORKSPACE,contract_id=CAMPAIGN,contract_version=1,purpose='purchase_contract',clock=lambda:NOW)|changes
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',headers=AUTH,
                    transport=httpx.MockTransport(self.handle),follow_redirects=True) as client:
            return await upload_registered_contract_document(client,ARTIFACT,source,**scope)


@pytest.mark.parametrize('outcome',['normal','lost_after','error_after'])
def test_contract_upload_reconciles_exact_bytes_without_approval(outcome):
    storage=ContractStorage(outcome=outcome);source=Source()
    receipt=asyncio.run(storage.upload(source))
    assert receipt['contract_id']==str(CAMPAIGN) and receipt['contract_version']==1
    assert receipt['upload_version']=='acquisition-contract-document-upload-v1'
    assert receipt['status']=='stored_unverified' and receipt['verification_persisted'] is False
    assert receipt['scan_status']=='not_scanned' and receipt['legal_review_approved'] is False
    assert receipt['execution_authorized'] is False
    assert len(storage.posts)==1 and storage.writes==1 and source.closed
    assert json.loads(storage.requests[0].content)=={'p_workspace':str(WORKSPACE),'p_contract':str(CAMPAIGN),
                                                    'p_version':1,'p_artifact':str(ARTIFACT)}
    assert not {'body','url','signed_url','object_name','campaign_id'} & receipt.keys()


def test_contract_upload_retry_never_overwrites():
    storage=ContractStorage()
    async def run():return await asyncio.gather(storage.upload(),storage.upload())
    results=asyncio.run(run())
    assert all(r['status']=='stored_unverified' for r in results)
    assert storage.writes==1 and storage.stored==BODY


@pytest.mark.parametrize('outcome',['lost_before','tampered','revoked_after','redirect','forbidden','unauthorized'])
def test_contract_uncertain_write_preserves_recovery_identity(outcome):
    storage=ContractStorage(outcome=outcome);source=Source()
    with pytest.raises(EvidenceUploadUnconfirmed) as error:asyncio.run(storage.upload(source))
    assert source.closed and len(storage.posts)==1 and 'PRIVATE' not in str(error.value)
    if outcome in ('redirect','forbidden','unauthorized','revoked_after'):
        assert not any(r.method=='GET' for r in storage.requests)


@pytest.mark.parametrize('change',[{'contract_version':2},{'contract_version':True},{'contract_version':2147483648},
                                  {'contract_id':WORKSPACE},{'workspace_id':CAMPAIGN},{'purpose':'mail_content'}])
def test_contract_target_mismatch_never_reads_input(change):
    storage=ContractStorage();source=Source()
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source,**change))
    assert source.closed and source.index==0 and not storage.posts


@pytest.mark.parametrize('field,value',[('version',2),('revoked',True),('policy',ARTIFACT)])
def test_contract_state_change_during_input_prevents_write(field,value):
    storage=ContractStorage();source=Source(after=lambda:setattr(storage,field,value))
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


@pytest.mark.parametrize('chunks',[[],[BODY[:-1]],[b'x'*len(BODY)],[BODY,b'extra'],['not bytes']])
def test_contract_mismatched_input_never_writes(chunks):
    storage=ContractStorage();source=Source(chunks)
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


def test_contract_empty_chunk_flood_obeys_shared_deadline(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence_upload.asyncio.timeout',lambda seconds:original(.01 if seconds==10 else seconds))
    class Empty(Source):
        async def __anext__(self):return b''
    storage=ContractStorage();source=Empty()
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


def test_contract_total_deadline_after_write_is_uncertain(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence_upload.asyncio.timeout',lambda seconds:original(.01 if seconds==60 else seconds))
    storage=ContractStorage(outcome='delayed_after');source=Source()
    with pytest.raises(EvidenceUploadUnconfirmed):asyncio.run(storage.upload(source))
    assert storage.writes==1 and len(storage.posts)==1 and source.closed


def test_store_forwards_exact_contract_scope(monkeypatch):
    from tools.acquisition_store import AcquisitionStore
    import tools.acquisition_contract_documents as documents
    seen=[]
    async def upload(client,artifact,source,**scope):seen.append((client,artifact,source,scope));return {'held':True}
    monkeypatch.setattr(documents,'upload_registered_contract_document',upload)
    source=Source();client=object();store=AcquisitionStore(client)
    scope=dict(workspace_id=WORKSPACE,contract_id=CAMPAIGN,contract_version=1,purpose='purchase_contract')
    assert asyncio.run(store.upload_contract_document(ARTIFACT,source,**scope))=={'held':True}
    assert seen==[(client,ARTIFACT,source,scope)]
