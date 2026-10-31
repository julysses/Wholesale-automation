import asyncio
from datetime import datetime,timedelta,timezone
from uuid import UUID

from fastapi import HTTPException
import httpx
import pytest

from schemas.acquisition_online_offer import OnlineOfferRequest
from tools.acquisition_portal_bot import BotConfig
from tools.acquisition_portal_submission import submit_portal_inquiry, PortalSubmissionUnconfirmed

ID=UUID('fd000000-0000-4000-8000-000000000001')
CONFIG=BotConfig('synthetic-secret','seller.example.test')
BODY={'submission_id':str(ID),'form_version':'v1','seller':{'name':'Synthetic seller','phone':'2145550100'},
      'property':{'address':'123 Synthetic St','city':'Dallas','state':'TX','postal_code':'75201','authority':'owner',
                  'condition':'unsure','occupancy':'vacant','timeline':'flexible','motivation':'Synthetic request','asking_price':None},
      'selections':{'privacy_acknowledged':True,'human_callback_requested':False}}
DEFINITION={'form_key':'synthetic','version':'v1','privacy_acknowledged':'Synthetic privacy',
            'human_callback_requested':'Synthetic callback','email_reply_requested':'Synthetic email'}

class Store:
    def __init__(self, *, denied=False, form=None, receipt=None, completion_error=None):
        self.calls=[];self.denied=denied;self.form=form or DEFINITION;self.receipt=receipt
        self.completion_error=completion_error
    async def request(self, method,path,*,body):
        self.calls.append((path,body))
        if path=='rpc/read_acquisition_public_form':return self.form
        if path=='rpc/admit_acquisition_portal_request':
            now=datetime.now(timezone.utc)
            return {'attempt_id':body['p_attempt'],'form_key':body['p_form_key'],'purpose':'submit','admitted':not self.denied,
                'checked_at':now.isoformat(),'expires_at':None if self.denied else (now+timedelta(seconds=30)).isoformat(),
                'retry_after_seconds':5 if self.denied else 0,'policy_revision':2}
        assert path=='rpc/complete_acquisition_portal_request'
        if self.completion_error:raise self.completion_error
        return self.receipt if self.receipt is not None else {'submission_id':str(ID),'status':'received','duplicate':False}


def run(store,handler):
    return asyncio.run(submit_portal_inquiry(store,CONFIG,form_key='synthetic',inquiry=OnlineOfferRequest.model_validate(BODY),
        network_hash='a'*64,bot_token='synthetic-token',bot_transport=httpx.MockTransport(handler)))


def success(_):
    return httpx.Response(200,json={'success':True,'hostname':CONFIG.hostname,'action':'acquisition_offer','cdata':str(ID),
                                   'challenge_ts':datetime.now(timezone.utc).isoformat()})


def test_orchestration_orders_admission_verification_and_exact_non_sending_save():
    store=Store()
    def provider(request):
        assert [p for p,_ in store.calls]==['rpc/read_acquisition_public_form','rpc/admit_acquisition_portal_request']
        return success(request)
    receipt=run(store,provider)
    assert receipt.submission_id==ID
    payload=store.calls[-1][1]
    assert payload['p_prepared']['request_evidence']['form']==DEFINITION
    assert payload['p_prepared']['asking_price'] is None
    assert payload['p_prepared']['contact_permission_granted'] is False
    assert payload['p_prepared']['request_hash']==payload['p_bot']['request_hash']
    assert 'synthetic-token' not in str(payload) and 'synthetic-secret' not in str(payload)


def test_capacity_denial_stops_before_provider_or_completion():
    store=Store(denied=True)
    def forbidden(_):raise AssertionError('Provider reached without admission')
    with pytest.raises(HTTPException) as caught:run(store,forbidden)
    assert caught.value.status_code==429 and len(store.calls)==2


@pytest.mark.parametrize('form',[DEFINITION|{'version':'changed'},DEFINITION|{'form_key':'other'},DEFINITION|{'internal_id':str(ID)}])
def test_changed_or_malformed_form_never_reaches_provider(form):
    store=Store(form=form)
    def forbidden(_):raise AssertionError('Provider reached for invalid form')
    with pytest.raises(HTTPException) as caught:run(store,forbidden)
    assert caught.value.status_code in (409,503) and len(store.calls)==1


def test_bot_rejection_never_saves_and_preserves_no_store():
    store=Store()
    with pytest.raises(HTTPException) as caught:run(store,lambda _:httpx.Response(200,json={'success':False}))
    assert caught.value.status_code==400 and caught.value.headers['Cache-Control']=='no-store'
    assert len(store.calls)==2


@pytest.mark.parametrize('receipt',[{}, {'submission_id':str(ID),'status':'received','duplicate':True,'lead_id':str(ID)},
                                  {'submission_id':str(UUID(int=1)),'status':'received','duplicate':False}])
def test_bad_receipt_is_an_uncertain_save_not_an_automatic_retry(receipt):
    store=Store(receipt=receipt)
    with pytest.raises(PortalSubmissionUnconfirmed):run(store,success)
    assert len(store.calls)==3


def test_lost_completion_response_preserves_request_and_uses_fresh_admission_on_retry():
    store=Store(completion_error=HTTPException(503,'Lost response'))
    with pytest.raises(PortalSubmissionUnconfirmed):run(store,success)
    original=store.calls[-1][1]
    store.completion_error=None;store.receipt={'submission_id':str(ID),'status':'received','duplicate':True}
    assert run(store,success).duplicate is True
    retried=store.calls[-1][1]
    assert retried['p_prepared']==original['p_prepared']
    assert retried['p_attempt']!=original['p_attempt']
    assert retried['p_bot']['verification_id']==original['p_bot']['verification_id']
