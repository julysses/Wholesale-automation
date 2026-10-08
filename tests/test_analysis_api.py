from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from web.api import analysis_api as api
ID='1d52e7d1-885c-44c5-8c52-a7ca5e1412d7'
LEAD='f44034c3-2a35-5b88-a028-ba038a408e1e'
INPUTS={'address':'Internal QA','sqft':1200,'beds':3,'baths':2,'condition':'moderate','comps':[], 'line_items':[], 'arv':250000,'repairs':37500,'assignment_fee':15000,'summary':''}
def body(**changes): return api.SaveAnalysis(request_id=ID,lead_id=LEAD,inputs={**INPUTS,**changes})
@pytest.mark.asyncio
async def test_atomic_call_uses_authenticated_operator_and_original_manifest(monkeypatch):
 db=MagicMock();db.rpc.return_value.execute.return_value.data={'analysis':{'id':ID,'lead_id':LEAD},'reused':True}
 monkeypatch.setattr(api,'get_supabase_client',lambda:db)
 result=await api.save_analysis(body(),SimpleNamespace(state=SimpleNamespace(user_id=ID)))
 assert result['reused']; name,p=db.rpc.call_args.args
 assert name=='save_manual_analysis' and p['p_id']==ID and p['p_operator']==ID and p['p_inputs']['repairs']==37500
@pytest.mark.asyncio
@pytest.mark.parametrize('result,status',[(None,503),({'analysis':{'id':LEAD,'lead_id':LEAD}},503),({'conflict':True},409),({'missing':True},404)])
async def test_receipt_failure_never_claims_saved(monkeypatch,result,status):
 db=MagicMock();db.rpc.return_value.execute.return_value.data=result;monkeypatch.setattr(api,'get_supabase_client',lambda:db)
 with pytest.raises(HTTPException) as e: await api.save_analysis(body(),SimpleNamespace(state=SimpleNamespace(user_id=ID)))
 assert e.value.status_code==status
@pytest.mark.parametrize('change',[{'arv':0},{'repairs':-1},{'assignment_fee':float('nan')},{'condition':'other'},{'comps':[{}]*7},{'repairs':50000}])
def test_invalid_estimates_refused(change):
 with pytest.raises(ValidationError):body(**change)
@pytest.mark.asyncio
async def test_missing_operator_has_no_write(monkeypatch):
 db=MagicMock();monkeypatch.setattr(api,'get_supabase_client',lambda:db)
 with pytest.raises(HTTPException): await api.save_analysis(body(),SimpleNamespace(state=SimpleNamespace()))
 db.rpc.assert_not_called()
