"""Form preparation does not accept scope drift, malformed history or activation."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.acquisition_store import acquisition_store
from web.api.acquisition_offer_forms_api import router, OfferFormVersion

W='10000000-0000-4000-8000-000000000001'
C='20000000-0000-4000-8000-000000000001'
I='30000000-0000-4000-8000-000000000001'
I2='30000000-0000-4000-8000-000000000002'
DEFINITION={'form_key':'synthetic-form','version':'v1','privacy_acknowledged':'Synthetic privacy',
            'human_callback_requested':'Synthetic human callback','email_reply_requested':'Synthetic email reply'}
BODY={'id':I,'expected_revision':0,'definition':DEFINITION}
RECEIPT={'id':I,'workspace_id':W,'campaign_id':C,'form_key':'synthetic-form','version':'v1',
         'revision':1,'definition_hash':'a'*64,'status':'draft','duplicate':False,'public_enabled':False,'execution_authorized':False}
ROW={'id':I,'workspace_id':W,'campaign_id':C,'acquisition_form_key':'synthetic-form','acquisition_form_revision':1,
     'acquisition_form_version':'v1','acquisition_form_definition':DEFINITION,'acquisition_definition_hash':'a'*64,
     'created_at':'2026-10-30T23:00:00Z','active':False,'send_confirmation_sms':False,'send_confirmation_email':False}
PATH=f'/workspaces/{W}/campaigns/{C}/offer-forms'


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router)
    app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_exact_save_preserves_definition_and_only_path_scope(endpoint):
    client,store=endpoint;store.request.return_value=deepcopy(RECEIPT)
    response=client.post(PATH,json=BODY)
    assert response.status_code==200 and response.json()==RECEIPT
    assert response.headers['cache-control']=='no-store'
    store.request.assert_awaited_once_with('POST','rpc/save_acquisition_offer_form',body={
        'p_id':I,'p_workspace':W,'p_campaign':C,'p_expected_revision':0,'p_definition':DEFINITION})


@pytest.mark.parametrize('change',[
    {'workspace_id':C},{'campaign_id':W},{'id':I2},{'revision':2},{'revision':True},
    {'form_key':'other'},{'version':'v2'},{'definition_hash':'bad'},{'status':'published'},
    {'duplicate':'false'},{'public_enabled':True},{'execution_authorized':True},{'execution_authorized':0},
    {'private_internal':'secret-marker'},
])
def test_unconfirmed_save_requires_original_retry(endpoint,change):
    client,store=endpoint;store.request.return_value=deepcopy(RECEIPT)|change
    response=client.post(PATH,json=BODY)
    assert response.status_code==503
    assert 'same saved request' in response.text
    assert 'secret-marker' not in response.text
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('change',[
    {'workspace_id':W},{'approved_by':W},{'active':True},{'expected_revision':True},
    {'expected_revision':-1},{'expected_revision':1000000000},
    {'definition':DEFINITION|{'privacy_acknowledged':' '}},
    {'definition':DEFINITION|{'send_confirmation_sms':True}},
])
def test_invalid_draft_never_reaches_database(endpoint,change):
    client,store=endpoint
    assert client.post(PATH,json=BODY|change).status_code==422
    store.request.assert_not_awaited()


def test_history_is_paginated_scoped_and_explicitly_inactive(endpoint):
    client,store=endpoint;store.request.return_value=[deepcopy(ROW),deepcopy(ROW)|{'id':I2}]
    response=client.get(PATH+'?limit=1&form_key=synthetic-form')
    assert response.status_code==200 and response.json()['next_after']==I
    assert len(response.json()['items'])==1
    assert response.headers['cache-control']=='no-store'
    params=store.request.call_args.kwargs['params']
    assert params=={'select':','.join(OfferFormVersion.model_fields),'workspace_id':'eq.'+W,
                    'campaign_id':'eq.'+C,'acquisition_form_key':'eq.synthetic-form','order':'id','limit':'2'}
    store.request.return_value=[deepcopy(ROW)|{'id':I2}]
    page=client.get(PATH+'?after='+I)
    assert page.json()['items'][0]['id']==I2 and page.json()['next_after'] is None
    assert store.request.call_args.kwargs['params']['id']=='gt.'+I


@pytest.mark.parametrize('change',[
    {'workspace_id':C},{'campaign_id':W},{'active':True},{'send_confirmation_sms':True},
    {'send_confirmation_email':'false'},{'acquisition_form_revision':True},
    {'acquisition_form_key':'other'},{'acquisition_form_version':'v2'},
    {'acquisition_form_definition':DEFINITION|{'privacy_acknowledged':' '}},
    {'acquisition_form_definition':DEFINITION|{'extra':'secret-marker'}},
    {'created_at':'2026-10-30T23:00:00'},{'acquisition_definition_hash':'invalid'},
    {'unknown':'secret-marker'},
])
def test_invalid_history_cannot_enter_editor(endpoint,change):
    client,store=endpoint;store.request.return_value=[deepcopy(ROW)|change]
    response=client.get(PATH+'?form_key=synthetic-form')
    assert response.status_code==503 and response.headers['cache-control']=='no-store'
    assert 'secret-marker' not in response.text


@pytest.mark.parametrize('rows',[[ROW,ROW],[ROW|{'id':I2},ROW],{'items':[ROW]},[ROW,ROW,ROW]])
def test_unordered_duplicate_or_overfull_page_rejected(endpoint,rows):
    client,store=endpoint;store.request.return_value=deepcopy(rows)
    assert client.get(PATH+'?limit=1').status_code==503


def test_cursor_regression_and_filter_drift_rejected(endpoint):
    client,store=endpoint;store.request.return_value=[deepcopy(ROW)]
    assert client.get(PATH+'?after='+I).status_code==503
    assert client.get(PATH+'?form_key=other').status_code==503


@pytest.mark.parametrize('method',['get','post'])
def test_database_errors_keep_status_and_no_store(endpoint,method):
    client,store=endpoint;store.request.side_effect=HTTPException(403,'Workspace access is not authorized')
    response=getattr(client,method)(PATH,**({'json':BODY} if method=='post' else {}))
    assert response.status_code==403 and response.headers['cache-control']=='no-store'
