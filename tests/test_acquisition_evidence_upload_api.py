"""Raw ASGI boundary tests: verify admission can reject without reading a request body."""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException

from web.api.acquisition_api import router
from web.api.acquisition_evidence_api import evidence_upload_store
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed

W='10000000-0000-4000-8000-000000000001'
C='20000000-0000-4000-8000-000000000001'
A='30000000-0000-4000-8000-000000000001'
P='40000000-0000-4000-8000-000000000001'
PATH=f'/api/acquisition/workspaces/{W}/campaigns/{C}/evidence/{A}/bytes'
BODY=b'Synthetic file bytes'


def receipt():
    now=datetime.now(timezone.utc)
    return {'workspace_id':W,'campaign_id':C,'evidence_ref':A,'purpose':'mail_content',
        'sha256':hashlib.sha256(BODY).hexdigest(),'byte_size':len(BODY),'media_type':'text/plain',
        'checked_at':now.isoformat(),'registry_checked_at':now.isoformat(),'retain_until':(now+timedelta(days=1)).isoformat(),
        'retention_policy_id':P,'status':'stored_unverified','verifier_version':'acquisition-evidence-bytes-v1',
        'registry_verifier_version':'acquisition-evidence-registry-v1','upload_version':'acquisition-evidence-upload-v1',
        'write_outcome':'stored_or_existing','scan_status':'not_scanned','verification_persisted':False,
        'byte_match_observed':True,'content_approved':False,'execution_authorized':False}


@pytest.fixture
def boundary():
    app=FastAPI();app.include_router(router)
    class Store:
        calls=[]
        error=None
        result=None
        async def upload_evidence_with_admission(self,artifact,source,**scope):
            self.calls.append((artifact,scope))
            try:
                if self.error:raise self.error
                body=bytearray()
                try:
                    async for chunk in source:body.extend(chunk)
                except (ValueError,RuntimeError):raise EvidenceUnavailable('private source details') from None
                assert bytes(body)==BODY
                return self.result or receipt()
            finally:await source.aclose()
    store=Store();app.dependency_overrides[evidence_upload_store]=lambda:store
    return app,store


def request(app,headers=None,chunks=None,query=b'purpose=mail_content'):
    calls=[];messages=[]
    source=list(chunks if chunks is not None else [BODY[:4],BODY[4:]])
    async def receive():
        calls.append(True)
        chunk=source.pop(0)
        if chunk is None:return {'type':'http.disconnect'}
        return {'type':'http.request','body':chunk,'more_body':bool(source)}
    async def send(message):messages.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','scheme':'https',
        'path':PATH,'raw_path':PATH.encode(),'query_string':query,'root_path':'',
        'headers':headers if headers is not None else [(b'content-type',b'application/octet-stream'),(b'content-length',str(len(BODY)).encode())],
        'server':('fixture',443),'client':('127.0.0.1',12345)}
    asyncio.run(app(scope,receive,send))
    start=next(x for x in messages if x['type']=='http.response.start')
    body=json.loads(b''.join(x.get('body',b'') for x in messages if x['type']=='http.response.body'))
    return start['status'],dict(start['headers']),body,calls


def test_scoped_binary_stream_and_no_approval(boundary):
    app,store=boundary
    status,headers,body,reads=request(app)
    assert status==200 and headers[b'cache-control']==b'no-store' and len(reads)==2
    assert body['status']=='stored_unverified' and body['scan_status']=='not_scanned' and not body['content_approved']
    assert store.calls==[(UUID(A),{'workspace_id':UUID(W),'campaign_id':UUID(C),'purpose':'mail_content'})]
    assert request(app,headers=[(b'content-type',b'application/octet-stream')])[0]==200


@pytest.mark.parametrize('headers,status',[
    ([],415), ([(b'content-type',b'multipart/form-data')],415),
    ([(b'content-type',b'application/octet-stream'),(b'content-encoding',b'gzip')],415),
    ([(b'content-type',b'application/octet-stream'),(b'content-disposition',b'attachment; filename=x')],415),
    ([(b'content-type',b'application/octet-stream')]*2,415),
    ([(b'content-type',b'application/octet-stream'),(b'content-length',b'10485761')],413),
    ([(b'content-type',b'application/octet-stream'),(b'content-length',b'-1')],422),
    ([(b'content-type',b'application/octet-stream'),(b'content-length',b'0')],422),
    ([(b'content-type',b'application/octet-stream'),(b'content-length',b'1'),(b'content-length',b'2')],422)])
def test_header_rejection_precedes_admission_and_body_read(boundary,headers,status):
    app,store=boundary
    code,response_headers,_,reads=request(app,headers=headers)
    assert code==status and response_headers[b'cache-control']==b'no-store' and not reads and not store.calls


@pytest.mark.parametrize('query',[b'',b'purpose=sms',b'purpose=mail_content&purpose=mail_content',b'purpose=mail_content&url=private'])
def test_query_cannot_change_identity_or_source(boundary,query):
    app,store=boundary
    status,_,_,reads=request(app,query=query)
    assert status==422 and not reads and not store.calls


@pytest.mark.parametrize('length',[1,100])
def test_declared_length_is_checked_against_stream(boundary,length):
    app,store=boundary
    status,_,body,_=request(app,headers=[(b'content-type',b'application/octet-stream'),(b'content-length',str(length).encode())])
    assert status==409 and body['detail']['code']=='EVIDENCE_UPLOAD_NOT_ACCEPTED'
    assert 'private' not in json.dumps(body)


def test_actual_size_limit_and_disconnection(boundary):
    app,_=boundary
    for chunks in ([b'x'*(10485760+1)],[None]):
        status,_,body,_=request(app,headers=[(b'content-type',b'application/octet-stream')],chunks=chunks)
        assert status==409 and body['detail']['code']=='EVIDENCE_UPLOAD_NOT_ACCEPTED'


@pytest.mark.parametrize('error,status',[(HTTPException(429,'Busy',headers={'Retry-After':'120'}),429),
    (HTTPException(403,'Denied'),403),(HTTPException(503,'Unknown reservation'),503),
    (EvidenceUnavailable('private'),409),(EvidenceUploadUnconfirmed('private'),503)])
def test_errors_preserve_recovery_and_do_not_read_unadmitted_body(boundary,error,status):
    app,store=boundary;store.error=error
    code,headers,body,reads=request(app)
    assert code==status and headers[b'cache-control']==b'no-store' and not reads
    assert 'private' not in json.dumps(body)
    if status==429:assert headers[b'retry-after']==b'120'
    if isinstance(error,EvidenceUploadUnconfirmed):assert body['detail']['code']=='EVIDENCE_UPLOAD_UNCONFIRMED'


@pytest.mark.parametrize('change',[
    {'workspace_id':C},{'campaign_id':W},{'evidence_ref':W},{'purpose':'mail_destination'},
    {'status':'approved'},{'scan_status':'clean'},{'verification_persisted':True},{'content_approved':True},
    {'execution_authorized':True},{'byte_match_observed':False},{'byte_match_observed':1},{'byte_size':True},
    {'retain_until':'2000-01-01T00:00:00Z'},{'checked_at':0},{'registry_checked_at':'2099-01-01T00:00:00Z'},
    {'checked_at':(datetime.now(timezone.utc)-timedelta(seconds=31)).isoformat()},
    {'sha256':'bad'},{'write_outcome':'created'},{'url':'private'}])
def test_malformed_receipt_preserves_unknown_outcome(boundary,change):
    app,store=boundary;store.result=receipt()|change
    status,headers,body,_=request(app)
    assert status==503 and headers[b'cache-control']==b'no-store' and body['detail']['code']=='EVIDENCE_UPLOAD_UNCONFIRMED'
    assert 'private' not in json.dumps(body)


def test_default_closed_and_authentication_before_body(boundary,monkeypatch):
    app,_=boundary;app.dependency_overrides.clear()
    monkeypatch.delenv('ACQUISITION_EVIDENCE_UPLOAD_ENABLED',raising=False)
    status,_,_,reads=request(app);assert status==404 and not reads
    monkeypatch.setenv('ACQUISITION_EVIDENCE_UPLOAD_ENABLED','true')
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    status,_,_,reads=request(app);assert status==404 and not reads
    monkeypatch.setenv('ACQUISITION_ENABLED','true')
    status,_,_,reads=request(app);assert status==401 and not reads
