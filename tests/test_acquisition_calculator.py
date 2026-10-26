import asyncio
import json

import httpx
import pytest

from tools.acquisition_calculator import calculate_snapshot, process_reserved_analysis, CalculationUnavailable
from tools.acquisition_underwriting import CALCULATION_VERSION

W='10000000-0000-4000-8000-000000000001'
A='b0000000-0000-4000-8000-000000000001'


def snapshot():
    return {'id':A,'workspace_id':W,'calculation_version':CALCULATION_VERSION,'input_hash':'a'*64,'status':'pending',
            'inputs':{'cases':{name:{'strategy':'fix_and_flip'} for name in ('base','downside','upside')}}}


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED','true')
    monkeypatch.setenv('ACQUISITION_CALCULATOR_ENABLED','true')
    monkeypatch.setenv('ACQUISITION_CALCULATOR_SERVICE_KEY','worker-only-fixture')
    monkeypatch.setenv('SUPABASE_URL','https://fixture.example.test')
    monkeypatch.delenv('VITE_SUPABASE_URL',raising=False)
    state={'snapshot':snapshot(),'requests':[]}
    def handle(request):
        state['requests'].append(request)
        if state.get('timeout'):
            raise httpx.ReadTimeout('secret-error-fixture',request=request)
        if request.url.path.endswith('read_acquisition_calculation'):
            return httpx.Response(200,json=state['snapshot'])
        return httpx.Response(200,json={'id':A,'status':'incomplete'})
    original=httpx.AsyncClient
    monkeypatch.setattr('tools.acquisition_calculator.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    return state


def test_worker_reads_stored_inputs_and_saves_computed_result(worker):
    result=asyncio.run(process_reserved_analysis(W,A))
    assert result=={'status':'incomplete'}
    assert len(worker['requests'])==2
    read,write=worker['requests']
    assert read.headers['Authorization']=='Bearer worker-only-fixture'
    body=json.loads(write.content)
    assert body['p_input_hash']=='a'*64
    assert body['p_outputs']['status']=='incomplete'
    assert body['p_outputs']['cases']['base']['mao'] is None
    assert body['p_outputs']['binding_offer'] is False


def test_completed_snapshot_never_recalculates_or_writes(worker):
    worker['snapshot']['status']='calculated'
    assert asyncio.run(process_reserved_analysis(W,A))=={'status':'calculated'}
    assert len(worker['requests'])==1


def test_unconfigured_worker_never_falls_back_to_generic_service_key(worker,monkeypatch):
    monkeypatch.delenv('ACQUISITION_CALCULATOR_SERVICE_KEY')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','must-not-be-used')
    assert asyncio.run(process_reserved_analysis(W,A))['reason']=='CALCULATOR_NOT_CONFIGURED'
    assert worker['requests']==[]
    monkeypatch.setenv('ACQUISITION_CALCULATOR_ENABLED','false')
    assert asyncio.run(process_reserved_analysis(W,A))['reason']=='CALCULATOR_NOT_ENABLED'


def test_worker_identity_mismatch_and_timeout_do_not_finalize(worker):
    worker['snapshot']['workspace_id']=A
    with pytest.raises(CalculationUnavailable):asyncio.run(process_reserved_analysis(W,A))
    assert len(worker['requests'])==1
    worker['requests'].clear();worker['timeout']=True
    with pytest.raises(CalculationUnavailable) as error:asyncio.run(process_reserved_analysis(W,A))
    assert 'secret-error' not in str(error.value)
    assert len(worker['requests'])==1


def test_invalid_stored_json_has_explicit_terminal_result_and_unknown_version_is_not_reinterpreted():
    invalid=snapshot();invalid['inputs']={'arv':300000,'mao':999999}
    result=calculate_snapshot(invalid)
    assert result['status']=='invalid' and result['error_code']=='INVALID_INPUTS'
    assert result['binding_offer'] is False
    invalid['calculation_version']='future-or-old-unregistered-version'
    with pytest.raises(CalculationUnavailable):calculate_snapshot(invalid)
