"""Synthetic upload/reconciliation only: no real files, storage service or provider credentials."""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest

from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed, plausible_media, upload_registered_evidence
from tools.acquisition_evidence import EvidenceUnavailable

WORKSPACE=UUID('10000000-0000-4000-8000-000000000001')
CAMPAIGN=UUID('20000000-0000-4000-8000-000000000001')
ARTIFACT=UUID('30000000-0000-4000-8000-000000000001')
POLICY=UUID('40000000-0000-4000-8000-000000000001')
NOW=datetime(2026,10,29,tzinfo=timezone.utc)
BODY=b'Synthetic evidence for bounded upload\n'
AUTH={'Authorization':'Bearer synthetic-user','apikey':'synthetic-public-key'}


class Source:
    def __init__(self, chunks=None, after=None, delay=0, error=None):
        self.chunks=[BODY[:8],BODY[8:]] if chunks is None else chunks
        self.index=0;self.closed=False;self.after=after;self.delay=delay;self.error=error

    def __aiter__(self):return self

    async def __anext__(self):
        if self.delay:await asyncio.sleep(self.delay)
        if self.index==len(self.chunks):
            if self.after:self.after()
            if self.error:raise self.error
            raise StopAsyncIteration
        value=self.chunks[self.index];self.index+=1
        return value

    async def aclose(self):self.closed=True


class Reply(httpx.AsyncByteStream):
    def __init__(self, body):self.body=body;self.closed=False;self.reads=0

    async def __aiter__(self):
        self.reads+=1
        yield self.body

    async def aclose(self):self.closed=True


class Storage:
    def __init__(self, body=BODY, media='text/plain', outcome='normal'):
        self.body=body;self.media=media;self.outcome=outcome
        self.requests=[];self.replies=[];self.stored=None;self.writes=0;self.revoked=False;self.policy=POLICY
        self.digest=hashlib.sha256(body).hexdigest()
        self.key=f'{WORKSPACE}/{ARTIFACT}/{self.digest}'

    def state(self):
        return {'artifact_id':str(ARTIFACT),'workspace_id':str(WORKSPACE),'campaign_id':str(CAMPAIGN),
            'purpose':'mail_content','expected_sha256':self.digest,'expected_byte_size':len(self.body),'media_type':self.media,
            'created_at':(NOW-timedelta(days=1)).isoformat(),'retain_until':(NOW+timedelta(days=1)).isoformat(),
            'retention_policy_id':str(self.policy),'revoked_at':NOW.isoformat() if self.revoked else None,
            'status':'revoked' if self.revoked else 'pending_verification','checked_at':NOW.isoformat(),
            'bytes_verified':False,'content_approved':False,'execution_authorized':False}

    def reply(self, status, body, media='application/json', **headers):
        stream=Reply(body);self.replies.append(stream)
        return httpx.Response(status,stream=stream,headers={'content-type':media,**headers})

    async def handle(self, request):
        self.requests.append(request)
        assert request.headers['authorization']==AUTH['Authorization'] and request.headers['apikey']==AUTH['apikey']
        assert request.headers['cache-control']=='no-store'
        if request.url.path=='/rest/v1/rpc/acquisition_evidence_state':
            assert request.method=='POST'
            assert json.loads(request.content)=={'p_workspace':str(WORKSPACE),'p_campaign':str(CAMPAIGN),'p_artifact':str(ARTIFACT)}
            return self.reply(200,json.dumps(self.state()).encode())
        if request.method=='POST':
            assert request.url.path==f'/storage/v1/object/acquisition-evidence/{self.key}'
            assert request.headers['x-upsert']=='false' and request.headers['content-type']==self.media
            content=await request.aread()
            assert content==self.body and request.headers['content-length']==str(len(content))
            assert 'transfer-encoding' not in request.headers
            if self.outcome=='lost_before':raise httpx.ConnectError('Synthetic private network details')
            if self.outcome in ('redirect','forbidden','unauthorized'):
                return self.reply({'redirect':307,'forbidden':403,'unauthorized':401}[self.outcome],b'PRIVATE PROVIDER BODY',location='https://attacker.example/file')
            if self.stored is not None:return self.reply(400,b'PRIVATE DUPLICATE BODY')
            self.stored=content;self.writes+=1
            if self.outcome=='delayed_after':await asyncio.sleep(1)
            if self.outcome=='lost_after':raise httpx.ReadTimeout('Synthetic lost response after commit')
            if self.outcome=='revoked_after':self.revoked=True
            if self.outcome=='tampered':self.stored=b'x'*len(content)
            return self.reply(500 if self.outcome=='error_after' else 200,b'IGNORED PRIVATE UPLOAD RESPONSE')
        assert request.method=='GET'
        assert request.url.path==f'/storage/v1/object/authenticated/acquisition-evidence/{self.key}'
        return self.reply(404,b'missing') if self.stored is None else self.reply(200,self.stored,self.media)

    async def upload(self, source=None, **kwargs):
        source=Source() if source is None else source
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',headers=AUTH,
                    transport=httpx.MockTransport(self.handle),follow_redirects=True) as client:
            return await upload_registered_evidence(client,ARTIFACT,source,workspace_id=WORKSPACE,
                campaign_id=CAMPAIGN,purpose='mail_content',clock=lambda:NOW,**kwargs)

    @property
    def posts(self):return [r for r in self.requests if r.method=='POST' and '/storage/' in r.url.path]


def test_upload_checks_bytes_then_reconciles_without_using_provider_receipt():
    storage=Storage();source=Source()
    receipt=asyncio.run(storage.upload(source))
    assert storage.writes==1 and len(storage.posts)==1 and source.closed
    assert all(r.closed for r in storage.replies)
    assert storage.replies[2].reads==0  # Provider upload response is never treated as proof.
    assert receipt['status']=='stored_unverified' and receipt['write_outcome']=='stored_or_existing'
    assert receipt['byte_match_observed'] is True and receipt['verification_persisted'] is False
    assert receipt['scan_status']=='not_scanned' and receipt['execution_authorized'] is False and receipt['content_approved'] is False
    assert not {'url','signed_url','body','token','object_name'} & receipt.keys()


@pytest.mark.parametrize('outcome',['lost_after','error_after'])
def test_committed_upload_with_lost_reply_recovers_by_reading_not_reposting(outcome):
    storage=Storage(outcome=outcome)
    assert asyncio.run(storage.upload())['status']=='stored_unverified'
    assert storage.writes==1 and len(storage.posts)==1


def test_identical_retry_and_concurrent_uploads_never_replace_object():
    storage=Storage()
    async def run():return await asyncio.gather(storage.upload(),storage.upload())
    receipts=asyncio.run(run())
    assert all(r['write_outcome']=='stored_or_existing' for r in receipts)
    assert len(storage.posts)==2 and storage.writes==1 and storage.stored==BODY
    assert asyncio.run(storage.upload())['status']=='stored_unverified'
    assert storage.writes==1


@pytest.mark.parametrize('outcome',['lost_before','tampered','revoked_after','redirect','forbidden','unauthorized'])
def test_unconfirmed_or_revoked_upload_never_returns_success(outcome):
    storage=Storage(outcome=outcome);source=Source()
    with pytest.raises(EvidenceUploadUnconfirmed) as error:asyncio.run(storage.upload(source))
    assert source.closed and len(storage.posts)==1
    assert 'PRIVATE' not in str(error.value) and 'synthetic-user' not in str(error.value)
    if outcome in ('redirect','forbidden','unauthorized','revoked_after'):
        assert not any(r.method=='GET' for r in storage.requests)
    assert all(r.closed for r in storage.replies)


@pytest.mark.parametrize('chunks',[[],[BODY[:-1]],[b'x'*len(BODY)],[BODY,b'extra',b'never read'],[123],[BODY.decode()]])
def test_wrong_or_oversized_input_stops_before_storage_write(chunks):
    storage=Storage();source=Source(chunks)
    with pytest.raises(EvidenceUnavailable) as error:asyncio.run(storage.upload(source))
    assert not isinstance(error.value,EvidenceUploadUnconfirmed)
    assert not storage.posts and source.closed and storage.stored is None
    if len(chunks)==3:assert source.index==2


@pytest.mark.parametrize('change',['revoked','policy'])
def test_registry_change_during_input_read_prevents_upload(change):
    storage=Storage()
    source=Source(after=lambda:setattr(storage,'revoked' if change=='revoked' else 'policy',True if change=='revoked' else ARTIFACT))
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


@pytest.mark.parametrize('media,body,expected',[
    ('text/plain',b'Plain UTF-8\n',True),('text/plain',b'\x00binary',False),('text/plain',b'\xff',False),
    ('application/pdf',b'%PDF-1.7\nsynthetic\n%%EOF',True),('application/pdf',b'plain text',False),
    ('image/png',b'\x89PNG\r\n\x1a\nsynthetic\x00\x00\x00\x00IEND\xaeB`\x82',True),
    ('image/png',b'\x89PNG\r\n\x1a\ntruncated',False),
    ('image/jpeg',b'\xff\xd8\xffsynthetic\xff\xd9',True),('image/jpeg',b'\xff\xd8\xfftruncated',False),
    ('text/html',b'<script>bad()</script>',False),
])
def test_type_precheck_is_not_a_full_parser_or_scanner(media,body,expected):
    assert plausible_media(bytearray(body),media) is expected


def test_registry_hash_match_does_not_allow_wrong_file_type():
    storage=Storage(body=b'not a PDF',media='application/pdf');source=Source([storage.body])
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


def test_input_timeout_closes_source_without_upload(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence_upload.asyncio.timeout',lambda seconds:original(0.01 if seconds==10 else seconds))
    storage=Storage();source=Source(delay=1)
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


@pytest.mark.parametrize('failure',[OSError,ValueError,RuntimeError])
def test_source_read_error_is_generic_and_does_not_upload(failure):
    storage=Storage();source=Source(error=failure('PRIVATE SOURCE ERROR'))
    with pytest.raises(EvidenceUnavailable) as error:asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts and 'PRIVATE' not in str(error.value)


def test_empty_chunk_flood_cannot_bypass_input_deadline(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence_upload.asyncio.timeout',lambda seconds:original(0.01 if seconds==10 else seconds))
    class Empty(Source):
        async def __anext__(self):return b''
    storage=Storage();source=Empty()
    with pytest.raises(EvidenceUnavailable):asyncio.run(storage.upload(source))
    assert source.closed and not storage.posts


def test_upload_timeout_after_commit_reconciles_without_another_write(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence_upload.asyncio.timeout',lambda seconds:original(0.01 if seconds==15 else seconds))
    storage=Storage(outcome='delayed_after');source=Source()
    receipt=asyncio.run(storage.upload(source))
    assert receipt['status']=='stored_unverified' and storage.writes==1 and len(storage.posts)==1 and source.closed


def test_total_deadline_after_possible_write_preserves_uncertain_outcome(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence_upload.asyncio.timeout',lambda seconds:original(0.02 if seconds==60 else seconds))
    storage=Storage(outcome='delayed_after');source=Source()
    with pytest.raises(EvidenceUploadUnconfirmed):asyncio.run(storage.upload(source))
    assert storage.writes==1 and len(storage.posts)==1 and source.closed
