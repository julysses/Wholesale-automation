"""Fresh scoped scan state, with no byte/scanner dispatch or review authority."""
import asyncio
import json
from datetime import timedelta

import httpx
import pytest

from tests.test_acquisition_contract_documents import NOW, uid
from tests.test_acquisition_evidence import AUTH, Stream
from tools.acquisition_contract_documents import load_contract_document_scan_state
from tools.acquisition_evidence import EvidenceUnavailable

SCOPE=dict(artifact_id=uid(1),workspace_id=uid(2),contract_id=uid(3),contract_version=2,purpose='purchase_contract')


def state(**change):
    return dict(artifact_id=str(uid(1)),workspace_id=str(uid(2)),contract_id=str(uid(3)),contract_version=2,
        purpose='purchase_contract',status='no_detection_observed',quarantined=False,observation_id=str(uid(4)),
        preview_authorized=False,legal_review_approved=False,execution_authorized=False,checked_at=NOW.isoformat()) | change


def setup(*, change=None, scope=None, status=200, raw=None):
    calls=[];stream=Stream([raw if raw is not None else json.dumps(state(**(change or {}))).encode()])
    def handler(req):
        calls.append(req)
        return httpx.Response(status,stream=stream,headers={'content-type':'application/json'})
    async def execute():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',headers=AUTH,
                transport=httpx.MockTransport(handler)) as client:
            return await load_contract_document_scan_state(client,**(SCOPE | (scope or {})),clock=lambda:NOW)
    return execute,calls,stream


def test_only_fixed_current_read_and_exact_scope():
    execute,calls,stream=setup()
    assert asyncio.run(execute()).model_dump(mode='json')['status']=='no_detection_observed'
    assert stream.closed and len(calls)==1
    assert calls[0].url.path=='/rest/v1/rpc/contract_document_scan_state'
    assert json.loads(calls[0].content)==dict(p_workspace=str(uid(2)),p_contract=str(uid(3)),p_version=2,
        p_purpose='purchase_contract',p_artifact=str(uid(1)))


@pytest.mark.parametrize('change',[{'workspace_id':str(uid(99))},{'contract_id':str(uid(99))},{'artifact_id':str(uid(99))},
    {'contract_version':3},{'contract_version':True},{'purpose':'title_report'},{'purpose':'mail_content'},
    {'campaign_id':str(uid(3))},{'checked_at':0},{'checked_at':NOW.replace(tzinfo=None).isoformat()},
    {'checked_at':(NOW-timedelta(seconds=31)).isoformat()},{'checked_at':(NOW+timedelta(seconds=6)).isoformat()},
    {'preview_authorized':True},{'legal_review_approved':True},{'execution_authorized':True},{'quarantined':0},
    {'quarantined':True},{'observation_id':None},{'status':'quarantined'},{'status':'not_scanned'},
    {'object_url':'https://private.test/file'}])
def test_foreign_stale_or_approving_state_unavailable(change):
    execute,calls,stream=setup(change=change)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert len(calls)==1 and stream.closed


@pytest.mark.parametrize('status',['not_scanned','requires_review','quarantined','revoked','expired','policy_review_required'])
def test_non_current_state_retained_without_observation_or_clearance(status):
    execute,_,_=setup(change={'status':status,'observation_id':None,'quarantined':status=='quarantined'})
    result=asyncio.run(execute())
    assert result.status==status and not result.legal_review_approved and not result.execution_authorized


@pytest.mark.parametrize('scope',[{'contract_version':True},{'contract_version':0},{'contract_version':2147483648},
    {'artifact_id':'not-a-uuid'},{'purpose':'mail_content'}])
def test_invalid_scope_no_io(scope):
    execute,calls,_=setup(scope=scope)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert not calls


@pytest.mark.parametrize('status',[301,401,403,404,429,500])
def test_failed_read_never_becomes_current(status):
    execute,calls,stream=setup(status=status)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert len(calls)==1 and stream.closed and stream.reads==0


@pytest.mark.parametrize('raw',[b'x'*8193,b'{',b'[]',b'null',json.dumps(state()).encode()[:-1]+b',"quarantined":true}'])
def test_invalid_or_ambiguous_read_unavailable(raw):
    execute,_,stream=setup(raw=raw)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert stream.closed
