from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from tools import list_tracing as tracing

@pytest.fixture
def fixture(monkeypatch):
    reference,lead=uuid4(),uuid4()
    snapshot={'owner_name':'Synthetic','property_address':'TEST ONLY','city':'Dallas','state':'TX'}
    row={'id':str(reference),'lead_id':str(lead),'provider':'synthetic','reserved_cents':60,
         'input_hash':'a'*64,'input_snapshot':snapshot,'state':'reserved'}
    db=MagicMock();provider=MagicMock();provider.name='synthetic'
    provider.trace.return_value={'request_id':str(reference),'lead_id':str(lead),'provider':'synthetic',
        'input_hash':'a'*64,'provider_receipt':'fixture-receipt','actual_cents':40,'contacts':[{'phone':'+12145550198'}]}
    failures={}
    def rpc(name,params):
        def execute():
            if name=='prepare_list_trace':value={'request':deepcopy(row),'input':snapshot,'contacts_saved':1 if row['state']=='completed' else 0}
            elif name=='claim_list_trace':
                dispatch=row['state']=='reserved'
                if dispatch:row['state']='submitted'
                value={'request':deepcopy(row),'input':snapshot,'dispatch':dispatch}
            elif name=='complete_list_trace':
                row.update(state='completed',actual_cents=params['p_actual_cents'],provider_job_id=params['p_provider_receipt'])
                value={'request':deepcopy(row),'contacts_saved':len(params['p_contacts'])}
            elif name=='settle_list_trace':
                if row['state']=='submitted':row['state']='unknown'
                value={'request':deepcopy(row)}
            else:raise AssertionError(name)
            if failures.get(name):raise RuntimeError('lost acknowledgement')
            return SimpleNamespace(data=value)
        return SimpleNamespace(execute=execute)
    db.rpc.side_effect=rpc
    monkeypatch.setattr(tracing,'record_provider_alert',MagicMock())
    return db,provider,reference,lead,row,failures

def execute(f):return tracing.trace_lead(*f[:4],60,enabled=True)

def test_disabled_never_reserves_or_calls(fixture):
    db,provider,ref,lead,*_=fixture
    assert tracing.trace_lead(db,provider,ref,lead,60)=={'blocked':'tracing_disabled'}
    db.rpc.assert_not_called();provider.trace.assert_not_called()

def test_success_persists_and_retry_never_contacts_provider_again(fixture):
    assert execute(fixture)['contacts_saved']==1
    assert execute(fixture)['request']['state']=='completed'
    fixture[1].trace.assert_called_once()

def test_lost_claim_acknowledgement_does_not_authorize_provider(fixture):
    fixture[5]['claim_list_trace']=True
    with pytest.raises(tracing.TraceUnconfirmed):execute(fixture)
    fixture[1].trace.assert_not_called();assert fixture[4]['state']=='unknown'

@pytest.mark.parametrize('change',[{'request_id':str(uuid4())},{'lead_id':str(uuid4())},{'provider':'other'},{'input_hash':'b'*64},{'actual_cents':61},{'contacts':[{'phone':'bad'}]},{'actual_cents':True}])
def test_malformed_or_mismatched_provider_result_keeps_hold(fixture,change):
    fixture[1].trace.return_value.update(change)
    with pytest.raises(tracing.TraceUnconfirmed):execute(fixture)
    assert fixture[4]['state']=='unknown'
    assert execute(fixture)['request']['state']=='unknown'
    fixture[1].trace.assert_called_once()

def test_lost_completion_acknowledgement_does_not_resend(fixture):
    fixture[5]['complete_list_trace']=True
    with pytest.raises(tracing.TraceUnconfirmed):execute(fixture)
    assert fixture[4]['state']=='completed'
    assert execute(fixture)['request']['state']=='completed'
    fixture[1].trace.assert_called_once()

def test_provider_exception_has_one_attempt(fixture):
    fixture[1].trace.side_effect=TimeoutError('uncertain')
    with pytest.raises(tracing.TraceUnconfirmed):execute(fixture)
    fixture[1].trace.assert_called_once();assert fixture[4]['state']=='unknown'
