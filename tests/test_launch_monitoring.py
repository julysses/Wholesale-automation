import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from tools import launch_monitor
from web.api import monitoring_api as api
from scripts import check_launch_availability as external

VALID = {"database":True,"intake":True,"owner":True,"aged":{"intake":2},"open_incidents":2}

@pytest.mark.asyncio
async def test_public_readiness_never_exposes_operational_records(monkeypatch):
    monkeypatch.setattr(launch_monitor,"snapshot",lambda:VALID)
    response = await api.readiness()
    assert response.status_code == 200 and json.loads(response.body) == {"status":"ok"}
    assert response.headers["cache-control"] == "no-store"

@pytest.mark.asyncio
@pytest.mark.parametrize("failure",[True,False])
async def test_dependency_outage_or_invalid_configuration_fails_readiness(monkeypatch,failure):
    def state():
        if failure: raise RuntimeError('database private details')
        return {**VALID,"intake":False}
    monkeypatch.setattr(launch_monitor,"snapshot",state)
    response=await api.readiness()
    assert response.status_code == 503 and json.loads(response.body)=={"status":"unavailable"}

@pytest.mark.asyncio
async def test_unauthenticated_worker_never_scans(monkeypatch):
    scan=MagicMock(); monkeypatch.setattr(launch_monitor,'scan',scan)
    monkeypatch.delenv('CRON_SECRET',raising=False)
    with pytest.raises(HTTPException) as error: await api.worker('')
    assert error.value.status_code==503
    monkeypatch.setenv('CRON_SECRET','controlled-test-secret')
    with pytest.raises(HTTPException) as error: await api.worker('Bearer incorrect')
    assert error.value.status_code==401
    scan.assert_not_called()
    scan.return_value={"created":1}
    assert await api.worker('Bearer controlled-test-secret')=={"created":1}

@pytest.mark.parametrize('value',[None,{}, {**VALID,'aged':{'email':-1}}, {**VALID,'database':'true'}])
def test_invalid_snapshot_is_never_ready(monkeypatch,value):
    monkeypatch.setattr(launch_monitor,'_request',lambda *args,**kwargs:value)
    with pytest.raises(RuntimeError): launch_monitor.snapshot()


def test_monitor_transport_is_bounded_and_server_only(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://controlled.supabase.co')
    monkeypatch.delenv('VITE_SUPABASE_URL',raising=False)
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','controlled-test-service-key')
    client=MagicMock(); client.return_value.__enter__.return_value.request.return_value.json.return_value=VALID
    monkeypatch.setattr(launch_monitor.httpx,'Client',client)
    assert launch_monitor.snapshot()==VALID
    client.assert_called_once_with(timeout=5)
    request=client.return_value.__enter__.return_value.request.call_args
    assert request.args==('POST','https://controlled.supabase.co/rest/v1/rpc/launch_monitor_snapshot')
    assert request.kwargs['headers']['Authorization']=='Bearer controlled-test-service-key'
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY')
    with pytest.raises(RuntimeError): launch_monitor.snapshot()
    assert client.call_count==1

@pytest.mark.parametrize('status,body,expected',[(200,b'{"status":"ok"}',True),(200,b'{"status":"unavailable"}',False),(503,b'private details',False),(200,b'not json',False)])
def test_independent_monitor_validates_readiness_acknowledgement(monkeypatch,status,body,expected):
    response=MagicMock(); response.__enter__.return_value=SimpleNamespace(status=status,read=lambda n:body)
    transport=MagicMock(return_value=response); monkeypatch.setattr(external,'urlopen',transport)
    assert external.probe(('crm_readiness',external.TARGETS['crm_readiness']))==('crm_readiness',expected)
    assert transport.call_args.kwargs['timeout']==10


def test_external_failure_output_has_no_response_body(monkeypatch,capsys):
    monkeypatch.setattr(external,'probe',lambda item:(item[0],False))
    assert external.main()==1
    value=json.loads(capsys.readouterr().out)
    assert value=={name:False for name in external.TARGETS}
