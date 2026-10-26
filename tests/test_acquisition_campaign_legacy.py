"""Shared campaign routes cannot expose scoped records even when flags are off."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from web.api import lead_forms_api as api


def database(monkeypatch, data):
    query=MagicMock()
    for method in ('select','eq','order','single'):
        getattr(query,method).return_value=query
    query.execute.return_value=SimpleNamespace(data=data)
    db=MagicMock();db.table.return_value=query
    monkeypatch.setattr(api,'_get_supabase',lambda:db)
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    return query


def test_shared_campaign_list_filters_scoped_rows_with_flag_off(monkeypatch):
    database(monkeypatch,[{'id':'old'},{'id':'legacy','workspace_id':None},{'id':'private','workspace_id':'other-workspace'}])
    assert asyncio.run(api.list_campaigns())==[{'id':'old'},{'id':'legacy','workspace_id':None}]


@pytest.mark.parametrize('action',['patch','sync'])
def test_shared_campaign_patch_and_sync_reject_scoped_records_before_effects(monkeypatch,action):
    query=database(monkeypatch,{'id':'private','workspace_id':'other-workspace','external_campaign_id':'123'})
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.update_campaign('private',{'status':'active'}) if action=='patch' else api.sync_campaign_from_facebook('private'))
    assert error.value.status_code==404
    query.update.assert_not_called()


def test_legacy_patch_cannot_claim_workspace_metadata(monkeypatch):
    query=database(monkeypatch,{'id':'legacy'})
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.update_campaign('legacy',{'workspace_id':'other-workspace'}))
    assert error.value.status_code==422
    query.update.assert_not_called()


def test_legacy_campaign_patch_remains_available(monkeypatch):
    query=database(monkeypatch,{'id':'legacy'})
    query.update.return_value=query
    query.execute.side_effect=[SimpleNamespace(data={'id':'legacy'}),SimpleNamespace(data=[{'id':'legacy','status':'paused'}])]
    assert asyncio.run(api.update_campaign('legacy',{'status':'paused'}))=={'id':'legacy','status':'paused'}
    query.update.assert_called_once_with({'status':'paused'})


def test_shared_optimizer_never_receives_scoped_campaigns(monkeypatch):
    import sys
    query=database(monkeypatch,[{'id':'legacy'},{'id':'scoped','workspace_id':'w'}])
    agent=MagicMock();agent.analyze_campaign_performance.return_value.model_dump.return_value={'ok':True}
    monkeypatch.setitem(sys.modules,'agents.lead_generation_agent',SimpleNamespace(LeadGenerationAgent=lambda:agent))
    assert asyncio.run(api.run_optimization())=={'ok':True}
    assert agent.analyze_campaign_performance.call_args.kwargs['campaigns']==[{'id':'legacy'}]


def test_shared_campaign_kpis_exclude_scoped_spend_with_flag_off(monkeypatch):
    query=database(monkeypatch,[])
    query.not_=query
    query.is_.return_value=query;query.gte.return_value=query
    query.execute.return_value=SimpleNamespace(count=0,data=[{'total_spend':100,'leads_count':2},{'workspace_id':'w','total_spend':9000,'leads_count':1}])
    result=asyncio.run(api.get_lead_gen_kpis())
    assert result['total_spend']==100 and result['avg_cpl']==50
