"""Signed observation transport tests using synthetic requests and raw streams."""
import asyncio
import copy
import json
from uuid import UUID

import httpx
import pytest

from tests.test_acquisition_evidence import ARTIFACT, AUTH, CAMPAIGN, WORKSPACE, Stream
from tests.test_acquisition_evidence_attestation import ACTOR, REQUEST, sign
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_persistence import EvidencePersistenceUnconfirmed, persist_evidence_attestation
from tools.acquisition_store import AcquisitionStore


def receipt(**changes):
    return dict(verification_id=str(REQUEST),workspace_id=str(WORKSPACE),artifact_id=str(ARTIFACT),scan_status='no_detection',
        duplicate=False,observation_persisted=True,preview_authorized=False,content_approved=False,execution_authorized=False)|changes


def setup(*, body=None, response=None, status=200, headers=None, error=None, request=None, scope=None,
          origin='https://storage.example.test/rest/v1/', auth=None, stream=None, via_store=False):
    signed=sign() if request is None else request
    stream=stream or Stream([json.dumps(receipt() if response is None else response).encode() if body is None else body])
    calls=[]
    def handle(req):
        calls.append(req)
        if error: raise error
        return httpx.Response(status,stream=stream,headers={'content-type':'application/json',**(headers or {})})
    async def execute():
        async with httpx.AsyncClient(base_url=origin,headers=AUTH if auth is None else auth,
                                    transport=httpx.MockTransport(handle),follow_redirects=True) as client:
            kwargs=dict(workspace_id=WORKSPACE,campaign_id=CAMPAIGN,artifact_id=ARTIFACT,actor_id=ACTOR,session_id=ACTOR)|(scope or {})
            if via_store:return await AcquisitionStore(client).persist_evidence_attestation(signed,**kwargs)
            return await persist_evidence_attestation(client,signed,**kwargs)
    return execute,calls,stream,signed


def test_one_user_scoped_post_preserves_signed_text_and_returns_no_clearance():
    execute,calls,stream,original=setup(via_store=True)
    saved=copy.deepcopy(original)
    result=asyncio.run(execute())
    assert len(calls)==1 and stream.closed and original==saved
    call=calls[0]
    assert call.method=='POST' and call.url.path=='/rest/v1/rpc/record_acquisition_evidence_verification'
    assert json.loads(call.content)==original
    assert call.headers['authorization']==AUTH['Authorization'] and call.headers['apikey']==AUTH['apikey']
    assert call.headers['accept-encoding']=='identity' and call.headers['cache-control']=='no-store'
    assert result==receipt()


def test_old_exact_request_can_reconcile_historical_duplicate_without_resigning():
    # The fixed synthetic observation timestamp can be old; database decides whether
    # this is an exact historical replay. Transport must not renew or reject it.
    execute,calls,_,original=setup(response=receipt(duplicate=True))
    assert asyncio.run(execute())['duplicate'] is True
    assert json.loads(calls[0].content)['p_observation']==original['p_observation']


@pytest.mark.parametrize('field', ['workspace_id','campaign_id','artifact_id','actor_id','session_id'])
def test_context_mismatch_stops_before_io(field):
    execute,calls,_,_=setup(scope={field:UUID('99900000-0000-4000-8000-000000000001')})
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert calls==[]


@pytest.mark.parametrize('field,value', [('p_signature','bad'),('p_signature','A'*64),('p_key',None),('p_actor',True),
    ('p_id',str(REQUEST).upper()),('p_workspace',' '+str(WORKSPACE)),('p_observation','{}'),('p_observation','['*4097),
    ('p_observation','{"scan_status":"no_detection","scan_status":"detected"}'),('new_field',True)])
def test_malformed_signed_requests_are_rejected_before_io(field,value):
    request=sign();request[field]=value
    if field=='p_id': request[field]='99300000-0000-4000-8000-00000000000A'
    execute,calls,_,_=setup(request=request)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert calls==[]


@pytest.mark.parametrize('origin', ['http://storage.example.test/rest/v1/','https://user:secret@storage.example.test/rest/v1/',
    'https://storage.example.test/rest/v1/?redirect=outside','https://storage.example.test/rest/v1/#secret','https://storage.example.test/other/'])
def test_origin_rejected_without_credential_transmission(origin):
    execute,calls,_,_=setup(origin=origin)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert not calls


@pytest.mark.parametrize('auth',[{}, {'Authorization':'Bearer a b','apikey':'public'}, {'Authorization':'Basic token','apikey':'public'}])
def test_missing_or_malformed_user_authority_does_not_fall_back(auth):
    execute,calls,_,_=setup(auth=auth)
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert not calls


@pytest.mark.parametrize('status',[201,204,206,301,302,307,308,400,401,403,404,409,422,429,500,503])
def test_all_non_success_outcomes_keep_original_request_unconfirmed_without_body_read(status):
    execute,calls,stream,original=setup(status=status,headers={'location':'https://outside.example/secret'})
    saved=copy.deepcopy(original)
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    assert len(calls)==1 and stream.closed and stream.reads==0 and original==saved


@pytest.mark.parametrize('headers',[{'content-type':'text/html'},{'content-encoding':'gzip'},
    {'content-length':'2049'},{'content-length':'-1'},{'content-length':'0'}, {'content-length':'99999999999'},
    {'content-length':'1, 2'}])
def test_invalid_headers_are_unknown_and_unread(headers):
    execute,calls,stream,_=setup(headers=headers)
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    assert len(calls)==1 and stream.closed and stream.reads==0


@pytest.mark.parametrize('body',[b'x'*2049,b'{',b'[]',b'null',b'{}',b'\xff',
    json.dumps(receipt()).encode()[:-1]+b',"duplicate":true}'])
def test_oversized_invalid_or_duplicate_field_receipts_are_not_accepted(body):
    execute,_,stream,_=setup(body=body)
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    assert stream.closed


@pytest.mark.parametrize('changes',[{'verification_id':str(ARTIFACT)},{'workspace_id':str(CAMPAIGN)},
    {'artifact_id':str(CAMPAIGN)},{'scan_status':'detected'},{'duplicate':0},{'observation_persisted':False},
    {'observation_persisted':1},{'preview_authorized':True},{'content_approved':True},{'execution_authorized':True},
    {'preview_authorized':0},{'object_url':'https://outside.example/file'}])
def test_corrupted_or_approving_receipts_do_not_clear_pending_state(changes):
    execute,_,stream,_=setup(response=receipt(**changes))
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    assert stream.closed


def test_length_mismatch_and_socket_failure_remain_unknown():
    execute,_,stream,_=setup(headers={'content-length':'1'})
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    assert stream.closed
    execute,calls,_,_=setup(error=httpx.ReadTimeout('private upstream body'))
    with pytest.raises(EvidencePersistenceUnconfirmed,match='^Evidence observation persistence is unconfirmed$'):asyncio.run(execute())
    assert len(calls)==1


def test_exact_request_can_be_retried_after_lost_reply_without_mutation():
    request=sign();saved=copy.deepcopy(request)
    execute,calls,_,_=setup(request=request,error=httpx.ReadTimeout('committed then lost'))
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    execute,retries,_,_=setup(request=request,response=receipt(duplicate=True))
    assert asyncio.run(execute())['duplicate'] is True
    assert calls[0].content==retries[0].content and request==saved


def test_deadline_closes_small_chunk_response(monkeypatch):
    monkeypatch.setattr('tools.acquisition_evidence_persistence.PERSIST_SECONDS',0.001)
    class SmallChunks(Stream):
        async def __aiter__(self):
            for value in b' '*1500+json.dumps(receipt()).encode():
                self.reads+=1
                yield bytes([value])
    stream=SmallChunks()
    execute,_,_,_=setup(stream=stream)
    with pytest.raises(EvidencePersistenceUnconfirmed):asyncio.run(execute())
    assert stream.closed and stream.reads<1500


def test_cancellation_closes_stream_and_keeps_request():
    async def scenario():
        entered=asyncio.Event()
        class Waiting(Stream):
            async def __aiter__(self):
                entered.set()
                await asyncio.Event().wait()
                yield b'never'
        stream=Waiting()
        execute,calls,_,request=setup(stream=stream)
        saved=copy.deepcopy(request)
        task=asyncio.create_task(execute());await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert stream.closed and request==saved and len(calls)==1
    asyncio.run(scenario())
