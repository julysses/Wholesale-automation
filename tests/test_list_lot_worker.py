from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from tools import list_lot_worker as worker
from tools.list_digest import render_digest
from tests.test_daily_list_launch_guards import client


def outcome():
    return dict(lead_id=str(uuid4()), evaluation_id=str(uuid4()), handoff_id=str(uuid4()), blocked=None)


def database(rows):
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = [SimpleNamespace(data={'outcomes':rows,'outreach_authorized':False}),
        SimpleNamespace(data={'owner_configured':True,'open_incidents':[],'overdue_receipts':[]})]
    return db


def test_disabled_has_no_storage_writes(monkeypatch):
    monkeypatch.delenv('LIST_LOT_ROUTING_ENABLED', raising=False)
    db=MagicMock();assert worker.process_lot_batch(db=db)['status']=='disabled';db.rpc.assert_not_called()


@pytest.mark.parametrize('value',['bad','0','11'])
def test_bad_limit_has_no_writes(monkeypatch,value):
    monkeypatch.setenv('LIST_LOT_ROUTING_ENABLED','true');monkeypatch.setenv('LIST_LOT_ROUTING_BATCH_SIZE',value)
    db=MagicMock()
    with pytest.raises(RuntimeError):worker.process_lot_batch(db=db)
    db.rpc.assert_not_called()


def test_routes_and_monitors_without_provider(monkeypatch):
    monkeypatch.setenv('LIST_LOT_ROUTING_ENABLED','true')
    held=outcome();held.update(blocked='lot_review_required',handoff_id=None)
    db=database([outcome(),held]);result=worker.process_lot_batch(db=db)
    assert result['routed']==1 and result['monitor']['owner_configured']
    assert db.rpc.call_args_list[0].args==('route_list_lots',{'p_limit':5})
    assert db.rpc.call_args_list[1].args==('monitor_list_lots',{})


@pytest.mark.parametrize('malformed',['missing_receipt','duplicate','outreach','monitor'])
def test_unconfirmed_outcomes_not_reported_as_success(monkeypatch,malformed):
    monkeypatch.setenv('LIST_LOT_ROUTING_ENABLED','true');row=outcome();rows=[row]
    if malformed=='missing_receipt':row['handoff_id']=None
    if malformed=='duplicate':rows.append(row)
    db=database(rows)
    if malformed=='outreach':db.rpc.return_value.execute.side_effect=[SimpleNamespace(data={'outcomes':rows,'outreach_authorized':True})]
    if malformed=='monitor':db.rpc.return_value.execute.side_effect=[SimpleNamespace(data={'outcomes':rows,'outreach_authorized':False}),SimpleNamespace(data={})]
    with pytest.raises((RuntimeError,TypeError,ValueError)):worker.process_lot_batch(db=db)
    assert db.rpc.call_count <= 2


def test_secret_gate(client,monkeypatch):
    process=MagicMock(return_value={'status':'disabled'});monkeypatch.setattr(worker,'process_lot_batch',process)
    path='/webhooks/_worker/list-lots';monkeypatch.delenv('CRON_SECRET',raising=False)
    assert client.get(path).status_code==503
    monkeypatch.setenv('CRON_SECRET','synthetic-lot-secret')
    assert client.get(path,headers={'Authorization':'Bearer wrong'}).status_code==401;process.assert_not_called()
    assert client.get(path,headers={'Authorization':'Bearer synthetic-lot-secret'}).status_code==200
    process.side_effect=RuntimeError('private database detail')
    response=client.get(path,headers={'Authorization':'Bearer synthetic-lot-secret'})
    assert response.status_code==503 and 'private database detail' not in response.text


def test_digest_discloses_lot_holds_overdue_receipts_and_monitor_absence():
    assert 'Lot routing monitor is unavailable' in render_digest({})
    result=render_digest({'lot_routing_monitor':{'owner_configured':False,'open_incidents':[{'lead_id':'fixture','blocked':'lot_review_required'}],'overdue_receipts':[{'handoff_id':'receipt','task_id':'task'}]}})
    assert 'Blocked routing: 1' in result and 'Overdue receipt: 1' in result and 'lead owner is not configured for automatic lot routing' in result


def test_digest_reports_stale_handoff_reasons_without_claiming_underwriting_completion():
    result=render_digest({'lot_routing_monitor':{'owner_configured':True,'open_incidents':[],
        'overdue_receipts':[],'stale_handoffs':[{'handoff_id':'receipt','task_id':'original-task','reasons':['destination_identity_conflict']}]}})
    assert 'Stale or held handoff: 1' in result and 'destination_identity_conflict' in result and 'original-task' in result
