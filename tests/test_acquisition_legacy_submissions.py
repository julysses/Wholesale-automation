"""Legacy receipt views and recovery cannot consume acquisition form versions."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient

from web.api import lead_forms_api as forms

IDENTITY=UUID('11111111-1111-4111-8111-111111111111')


@pytest.fixture
def database(monkeypatch):
    db=MagicMock(); queries={}
    def table(name):
        if name not in queries:
            query=MagicMock()
            for method in ('select','eq','order','limit'):
                getattr(query,method).return_value=query
            query.execute.return_value=SimpleNamespace(data=[])
            queries[name]=query
        return queries[name]
    db.table.side_effect=table
    monkeypatch.setattr(forms,'_get_supabase',lambda:db)
    return db,table


@pytest.mark.parametrize('enabled',['true','false'])
def test_receipt_list_filters_scope_and_projects_only_legacy_parent_fields(database,monkeypatch,enabled):
    monkeypatch.setenv('ACQUISITION_ENABLED',enabled)
    db,table=database
    rows=[{'id':'old','form_id':'old-form','lead_form_configs':{'name':'Old','slug':'old','questions':['private-detail']}},
          {'id':'unlinked','form_id':None,'lead_form_configs':None},
          {'id':'scoped-receipt','workspace_id':'w','lead_form_configs':{'name':'private'}},
          {'id':'scoped-parent','form_id':'f','lead_form_configs':{'workspace_id':'w','name':'private'}},
          {'id':'unresolved','form_id':'f','lead_form_configs':None},
          {'id':'bad-parent','form_id':'f','lead_form_configs':[{'name':'private'}]}]
    before=deepcopy(rows)
    table('lead_form_submissions').execute.return_value=SimpleNamespace(data=rows)
    response=Response()
    result=asyncio.run(forms.list_submissions(10,'old-form',response))
    assert result==[{'id':'old','form_id':'old-form','lead_form_configs':{'name':'Old','slug':'old'}},rows[1]]
    assert rows==before and response.headers['cache-control']=='no-store'
    table('lead_form_submissions').limit.assert_called_once_with(10)
    table('lead_form_submissions').eq.assert_called_once_with('form_id','old-form')
    assert 'lead_form_configs(*)' in table('lead_form_submissions').select.call_args.args[0]
    db.rpc.assert_not_called()


@pytest.mark.parametrize('limit',[0,101,-1,True])
def test_list_limit_rejected_before_database(database,limit):
    db,_=database
    with pytest.raises(HTTPException) as error:asyncio.run(forms.list_submissions(limit))
    assert error.value.status_code==422
    db.table.assert_not_called()


def recovery_setup(table,receipt=None,config=None):
    table('profiles').execute.return_value=SimpleNamespace(data=[{'role':'admin','status':'approved'}])
    table('lead_form_submissions').execute.return_value=SimpleNamespace(data=[] if receipt is None else [receipt])
    table('lead_form_configs').execute.return_value=SimpleNamespace(data=[] if config is None else [config])
    request=Request({'type':'http','state':{'user_id':'operator'}})
    return request


@pytest.mark.parametrize('receipt,config',[
    ({'workspace_id':'w','form_id':'f','raw_answers':{'secret':'value'}},{'id':'f'}),
    ({'form_id':'f','raw_answers':{'secret':'value'}},{'id':'f','workspace_id':'w'}),
])
def test_recovery_rejects_scoped_receipt_or_parent_before_processing(database,monkeypatch,receipt,config):
    db,table=database;request=recovery_setup(table,receipt,config)
    processor=AsyncMock();monkeypatch.setattr(forms,'_process_form_submission',processor)
    with pytest.raises(HTTPException) as error:asyncio.run(forms.recover_form_submission(IDENTITY,request))
    assert error.value.status_code==404 and error.value.detail=='Submission not found'
    assert error.value.headers['Cache-Control']=='no-store'
    processor.assert_not_awaited();db.rpc.assert_not_called()
    if receipt.get('workspace_id'):table('lead_form_configs').execute.assert_not_called()


def test_disabled_legacy_form_can_recover_without_notifications(database,monkeypatch):
    _,table=database
    config={'id':'f','active':False};receipt={'form_id':'f','raw_answers':{},'utm_campaign':'legacy'}
    request=recovery_setup(table,receipt,config);processor=AsyncMock(return_value='saved-lead')
    monkeypatch.setattr(forms,'_process_form_submission',processor)
    response=Response();result=asyncio.run(forms.recover_form_submission(IDENTITY,request,response))
    assert result=={'success':True,'lead_id':'saved-lead','provider_messages_replayed':False}
    assert processor.call_args.args[:2]==(config,{})
    assert processor.call_args.kwargs=={'deliver_notifications':False}
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('missing_receipt,status',[(True,404),(False,409)])
def test_missing_receipt_or_definition_does_not_infer_a_form(database,monkeypatch,missing_receipt,status):
    _,table=database
    request=recovery_setup(table,None if missing_receipt else {'form_id':'f'})
    processor=AsyncMock();monkeypatch.setattr(forms,'_process_form_submission',processor)
    with pytest.raises(HTTPException) as error:asyncio.run(forms.recover_form_submission(IDENTITY,request))
    assert error.value.status_code==status;processor.assert_not_awaited()
    assert error.value.headers['Cache-Control']=='no-store'


def test_internal_processor_rejects_scoped_config_before_any_side_effect(monkeypatch):
    client=MagicMock();monkeypatch.setattr(forms,'_get_supabase',client)
    with pytest.raises(HTTPException) as error:
        asyncio.run(forms._process_form_submission({'workspace_id':'w'},{},{},str(IDENTITY),None))
    assert error.value.status_code==404;client.assert_not_called()


def test_real_route_keeps_no_store_header_on_receipt_list(database):
    app=FastAPI();app.include_router(forms.router)
    with TestClient(app) as client:
        response=client.get('/api/lead-gen/submissions')
        assert response.status_code==200 and response.json()==[]
        assert response.headers['cache-control']=='no-store'
