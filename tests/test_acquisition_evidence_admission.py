"""Admission contracts only; no file source or provider access."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException

from tools.acquisition_evidence_admission import admit_evidence_upload

W=UUID('10000000-0000-4000-8000-000000000001')
C=UUID('20000000-0000-4000-8000-000000000001')
A=UUID('30000000-0000-4000-8000-000000000001')
NOW=datetime(2026,10,29,tzinfo=timezone.utc)


class Store:
    def __init__(self,change=None,error=None):self.calls=[];self.change=change or {};self.error=error
    async def request(self,method,path,*,body):
        self.calls.append((method,path,body))
        if self.error:raise self.error
        return {'attempt_id':body['p_attempt'],'workspace_id':str(W),'campaign_id':str(C),'artifact_id':str(A),
                'purpose':'mail_content','admitted':True,'checked_at':NOW.isoformat(),
                'expires_at':(NOW+timedelta(seconds=120)).isoformat(),'retry_after_seconds':0,
                'execution_authorized':False,**self.change}


def run(store,**kwargs):
    return asyncio.run(admit_evidence_upload(store,A,workspace_id=W,campaign_id=C,purpose='mail_content',clock=lambda:NOW,**kwargs))


def test_fresh_private_attempt_identity_per_invocation():
    store=Store();one=run(store);two=run(store)
    assert one.attempt_id!=two.attempt_id and len(store.calls)==2
    method,path,body=store.calls[0]
    assert (method,path)==('POST','rpc/admit_acquisition_evidence_upload')
    assert body=={'p_attempt':str(one.attempt_id),'p_workspace':str(W),'p_campaign':str(C),'p_artifact':str(A),'p_purpose':'mail_content'}


@pytest.mark.parametrize('change',[
    {'workspace_id':str(C)},{'campaign_id':str(W)},{'artifact_id':str(W)},{'attempt_id':str(W)},
    {'purpose':'mail_destination'},{'admitted':'true'},{'expires_at':None},{'retry_after_seconds':True},
    {'retry_after_seconds':1},{'execution_authorized':True},{'execution_authorized':0},
    {'checked_at':(NOW-timedelta(seconds=16)).isoformat()},{'checked_at':(NOW+timedelta(seconds=6)).isoformat()},
    {'expires_at':(NOW+timedelta(seconds=121)).isoformat()},{'checked_at':0},
    {'download_url':'private'},{'admitted':False},{'admitted':False,'expires_at':None,'retry_after_seconds':121}])
def test_untrusted_receipt_never_admits(change):
    store=Store(change)
    with pytest.raises(HTTPException) as error:run(store)
    assert error.value.status_code==503 and error.value.headers['Cache-Control']=='no-store'
    assert len(store.calls)==1 and 'private' not in error.value.detail


def test_denied_capacity_has_bounded_retry_and_no_replay():
    store=Store({'admitted':False,'expires_at':None,'retry_after_seconds':120})
    with pytest.raises(HTTPException) as error:run(store)
    assert error.value.status_code==429 and error.value.headers['Retry-After']=='120' and len(store.calls)==1


@pytest.mark.parametrize('status',[401,403,409,503])
def test_unknown_or_denied_database_response_never_retries(status):
    store=Store(error=HTTPException(status,'Database unavailable'))
    with pytest.raises(HTTPException) as error:run(store)
    assert error.value.status_code==status and error.value.headers['Cache-Control']=='no-store' and len(store.calls)==1


class Source:
    def __init__(self):self.read=False;self.closed=False
    async def aclose(self):self.closed=True


def test_capacity_denial_closes_source_before_read(monkeypatch):
    import tools.acquisition_evidence_admission as module
    from threading import BoundedSemaphore
    slots=BoundedSemaphore(1);slots.acquire();monkeypatch.setattr(module,'_PROCESS_UPLOADS',slots)
    store=Store();source=Source()
    with pytest.raises(HTTPException) as error:
        asyncio.run(module.upload_with_admission(store,A,source,workspace_id=W,campaign_id=C,purpose='mail_content'))
    assert error.value.status_code==429 and not store.calls and source.closed and not source.read
    assert not slots.acquire(blocking=False)
    slots.release()


def test_database_denial_or_failure_never_starts_upload(monkeypatch):
    import tools.acquisition_evidence_admission as module
    from threading import BoundedSemaphore
    slots=BoundedSemaphore(1);monkeypatch.setattr(module,'_PROCESS_UPLOADS',slots)
    for failure in (HTTPException(429,'Occupied'),HTTPException(503,'Unknown outcome')):
        store=Store(error=failure);source=Source()
        with pytest.raises(HTTPException):
            asyncio.run(module.upload_with_admission(store,A,source,workspace_id=W,campaign_id=C,purpose='mail_content'))
        assert source.closed and not source.read and len(store.calls)==1
        assert slots.acquire(blocking=False);slots.release()


def test_reserved_upload_releases_process_capacity_on_success_and_error(monkeypatch):
    import tools.acquisition_evidence_admission as module
    from threading import BoundedSemaphore
    from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed
    slots=BoundedSemaphore(1);monkeypatch.setattr(module,'_PROCESS_UPLOADS',slots)
    async def admitted(*args,**kwargs):return None
    monkeypatch.setattr(module,'admit_evidence_upload',admitted)
    class UploadStore:
        error=False
        async def upload_evidence(self,artifact,source,**kwargs):
            source.read=True;await source.aclose()
            if self.error:raise EvidenceUploadUnconfirmed('Unconfirmed')
            return {'status':'stored_unverified'}
    store=UploadStore()
    for failure in (False,True):
        store.error=failure;source=Source()
        async def run_upload():return await module.upload_with_admission(store,A,source,workspace_id=W,campaign_id=C,purpose='mail_content')
        if failure:
            with pytest.raises(EvidenceUploadUnconfirmed):asyncio.run(run_upload())
        else:assert asyncio.run(run_upload())=={'status':'stored_unverified'}
        assert source.read and source.closed and slots.acquire(blocking=False)
        slots.release()


def test_cancellation_during_admission_closes_input_and_releases_capacity(monkeypatch):
    import tools.acquisition_evidence_admission as module
    from threading import BoundedSemaphore
    slots=BoundedSemaphore(1);monkeypatch.setattr(module,'_PROCESS_UPLOADS',slots)
    async def scenario():
        entered=asyncio.Event()
        class WaitingStore:
            async def request(self,*args,**kwargs):
                entered.set();await asyncio.Event().wait()
        source=Source()
        task=asyncio.create_task(module.upload_with_admission(WaitingStore(),A,source,workspace_id=W,campaign_id=C,purpose='mail_content'))
        await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert source.closed and not source.read and slots.acquire(blocking=False)
        slots.release()
    asyncio.run(scenario())
