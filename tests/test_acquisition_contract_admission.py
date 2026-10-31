"""Admission contracts only; no file source or provider access."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException

from tools.acquisition_evidence_admission import admit_contract_document_upload

W=UUID('10000000-0000-4000-8000-000000000001')
C=UUID('20000000-0000-4000-8000-000000000001')
A=UUID('30000000-0000-4000-8000-000000000001')
NOW=datetime(2026,10,29,tzinfo=timezone.utc)


class Store:
    def __init__(self,change=None,error=None):self.calls=[];self.change=change or {};self.error=error
    async def request(self,method,path,*,body):
        self.calls.append((method,path,body))
        if self.error:raise self.error
        return {'attempt_id':body['p_attempt'],'workspace_id':str(W),'contract_id':str(C),'contract_version':1,'artifact_id':str(A),
                'purpose':'purchase_contract','admitted':True,'checked_at':NOW.isoformat(),
                'expires_at':(NOW+timedelta(seconds=120)).isoformat(),'retry_after_seconds':0,
                'execution_authorized':False,**self.change}


def run(store,**kwargs):
    return asyncio.run(admit_contract_document_upload(store,A,workspace_id=W,contract_id=C,contract_version=1,purpose='purchase_contract',clock=lambda:NOW,**kwargs))


def test_fresh_private_attempt_identity_per_invocation():
    store=Store();one=run(store);two=run(store)
    assert one.attempt_id!=two.attempt_id and len(store.calls)==2
    method,path,body=store.calls[0]
    assert (method,path)==('POST','rpc/admit_contract_document_upload')
    assert body=={'p_attempt':str(one.attempt_id),'p_workspace':str(W),'p_contract':str(C),'p_version':1,'p_artifact':str(A),'p_purpose':'purchase_contract'}


@pytest.mark.parametrize('change',[
    {'workspace_id':str(C)},{'contract_id':str(W)},{'contract_version':2},{'contract_version':True},{'contract_version':'1'}, {'campaign_id':str(C)},{'artifact_id':str(W)},{'attempt_id':str(W)},
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


@pytest.mark.parametrize('change',[{'contract_version':True},{'contract_version':0},{'contract_version':2147483648},
                                  {'contract_version':'1'},{'contract_id':str(C)},{'purpose':'mail_content'}])
def test_invalid_contract_identity_never_reserves(change):
    store=Store()
    scope=dict(workspace_id=W,contract_id=C,contract_version=1,purpose='purchase_contract')|change
    with pytest.raises(HTTPException) as error:
        asyncio.run(admit_contract_document_upload(store,A,**scope))
    assert error.value.status_code==422 and not store.calls


def test_mail_and_contract_share_process_capacity_and_cancel_cleanup(monkeypatch):
    import tools.acquisition_evidence_admission as module
    from threading import BoundedSemaphore
    from tests.test_acquisition_evidence_admission import Source
    slots=BoundedSemaphore(1);monkeypatch.setattr(module,'_PROCESS_UPLOADS',slots)
    async def scenario():
        entered=asyncio.Event()
        class WaitingStore:
            async def request(self,*args,**kwargs):
                entered.set();await asyncio.Event().wait()
        first=Source();second=Source()
        task=asyncio.create_task(module.upload_contract_document_with_admission(WaitingStore(),A,first,
            workspace_id=W,contract_id=C,contract_version=1,purpose='purchase_contract'))
        await entered.wait()
        blocked=Store()
        with pytest.raises(HTTPException) as error:
            await module.upload_with_admission(blocked,A,second,workspace_id=W,campaign_id=C,purpose='mail_content')
        assert error.value.status_code==429 and second.closed and not second.read and not blocked.calls
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert first.closed and not first.read
        assert slots.acquire(blocking=False);slots.release()
    asyncio.run(scenario())
