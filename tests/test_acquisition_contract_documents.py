"""Synthetic private storage transport, no registry or production requests."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID
import httpx
import pytest
from pydantic import ValidationError
from schemas.acquisition_contract_documents import ContractDocumentArtifact
from tools.acquisition_contract_documents import verify_contract_document_bytes
from tools.acquisition_evidence import EvidenceUnavailable

NOW=datetime(2026,10,31,tzinfo=timezone.utc)
BODY=b'Synthetic contract document bytes'
uid=lambda n:UUID(int=n)

def artifact(**changes):
    return ContractDocumentArtifact.model_validate(dict(id=uid(1),workspace_id=uid(2),contract_id=uid(3),contract_version=2,
        purpose='purchase_contract',sha256=hashlib.sha256(BODY).hexdigest(),byte_size=len(BODY),media_type='application/pdf',
        created_at=NOW-timedelta(days=1),retain_until=NOW+timedelta(days=1),revoked_at=None)|changes)

class Stream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield BODY[:5]
        yield BODY[5:]

def run(document=None, *, scope=None, status=200, headers=None, clock=lambda:NOW):
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(status,headers={'content-type':'application/pdf',**(headers or {})},stream=Stream())
    async def execute():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',
            headers={'Authorization':'Bearer synthetic-user','apikey':'synthetic-public'},transport=httpx.MockTransport(handler)) as client:
            return await verify_contract_document_bytes(client,document or artifact(),**(dict(workspace_id=uid(2),contract_id=uid(3),contract_version=2,purpose='purchase_contract')|(scope or {})),clock=clock)
    return execute,requests

def test_scoped_document_observation_returns_no_document_or_approval():
    execute,requests=run()
    result=asyncio.run(execute())
    assert len(requests)==1 and requests[0].url.path==f'/storage/v1/object/authenticated/acquisition-evidence/{uid(2)}/{uid(1)}/{hashlib.sha256(BODY).hexdigest()}'
    assert requests[0].headers['authorization']=='Bearer synthetic-user'
    assert result['contract_version']==2 and result['contract_id']==str(uid(3))
    assert result['execution_authorized'] is False and result['legal_review_approved'] is False
    assert result['verification_persisted'] is False and result['scan_status']=='not_scanned'
    assert not {'campaign_id','body','url','object_name','token'} & result.keys()

@pytest.mark.parametrize('scope',[{'workspace_id':uid(9)},{'contract_id':uid(9)},{'contract_version':3},{'contract_version':True},{'purpose':'title_report'}])
def test_wrong_target_never_fetches_document(scope):
    execute,requests=run(scope=scope)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert requests==[]

@pytest.mark.parametrize('changes',[{'contract_version':True},{'contract_version':0},{'object_name':'../secret'},
    {'purpose':'executed_and_approved'},{'campaign_id':uid(9)},{'byte_size':0},{'sha256':'A'*64}])
def test_document_descriptor_rejects_ambiguous_or_misclassified_input(changes):
    with pytest.raises(ValidationError):artifact(**changes)

@pytest.mark.parametrize('changes',[{'sha256':'0'*64},{'byte_size':len(BODY)-1},{'byte_size':len(BODY)+1}])
def test_different_bytes_cannot_be_confirmed(changes):
    execute,_=run(artifact(**changes))
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())

@pytest.mark.parametrize('changes',[{'revoked_at':NOW},{'retain_until':NOW}])
def test_unavailable_document_never_fetches(changes):
    execute,requests=run(artifact(**changes))
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert requests==[]

def test_retention_expiry_during_stream_is_not_confirmed():
    times=iter([NOW,NOW+timedelta(days=1)])
    execute,_=run(clock=lambda:next(times))
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())

@pytest.mark.parametrize('status,headers',[(302,{'location':'https://external.test'}),(200,{'content-encoding':'gzip'}),(200,{'content-type':'text/html'}),(200,{'content-length':'1'}),(403,{})])
def test_untrusted_transport_metadata_and_redirects_rejected(status,headers):
    execute,requests=run(status=status,headers=headers)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert len(requests)==1

def test_unvalidated_copy_is_revalidated_before_fetch():
    execute,requests=run(artifact().model_copy(update={'contract_version':True}))
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert requests==[]
