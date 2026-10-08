from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from web.api import deals_api as api
ID='11234567-0000-4000-8000-000000000001'; LEAD='f44034c3-2a35-5b88-a028-ba038a408e1e'; OP='89f3b3f6-5a88-4b79-b3f4-461e0cd626a2'
def setup(monkeypatch,value):
 db=MagicMock();db.rpc.return_value.execute.return_value.data=value;monkeypatch.setattr(api,'get_supabase_client',lambda:db)
 return db,SimpleNamespace(state=SimpleNamespace(user_id=OP))
@pytest.mark.asyncio
async def test_create_keeps_original_reference_and_authenticated_owner(monkeypatch):
 db,req=setup(monkeypatch,{'deal':{'id':ID,'updated_at':'2026-10-08T12:00:00Z'}})
 row=await api.create(api.CreateDeal(request_id=ID,deal=api.NewDeal(lead_id=LEAD,deal_name='Internal QA')),req)
 assert row['id']==ID;name,p=db.rpc.call_args.args
 assert name=='create_pipeline_deal' and p['p_operator']==OP and p['p_id']==ID and p['p_payload']['lead_id']==LEAD
@pytest.mark.asyncio
async def test_update_carries_version_and_explicit_date_clear(monkeypatch):
 db,req=setup(monkeypatch,{'deal':{'id':ID,'updated_at':'2026-10-08T12:01:00Z'}})
 await api.update(UUID(ID),api.UpdateDeal(expected_updated_at='2026-10-08T12:00:00Z',updates=api.DealFields(inspection_deadline=None)),req)
 p=db.rpc.call_args.args[1]; assert p['p_patch']=={'inspection_deadline':None};assert p['p_expected']=='2026-10-08T12:00:00+00:00'
@pytest.mark.parametrize('value,status',[(None,503),({'conflict':True},409),({'existing_id':ID},409),({'invalid':True},422),({'missing':True},404),({'deal':{'id':ID}},503)])
def test_unconfirmed_and_invalid_receipts_are_not_success(value,status):
 with pytest.raises(HTTPException) as e:api.result(value,ID)
 assert e.value.status_code==status
@pytest.mark.parametrize('fields',[{'psa_doc_url':'javascript:alert(1)'},{'psa_doc_url':'http://example.com/doc'},{'psa_doc_url':'https://secret@example.com/doc'},{'assignment_fee':float('nan')},{'contract_price':-1},{'buyer_id':'bad'},{'stage':'fake'},{'updated_at':'2026-10-08T12:00:00Z'}])
def test_invalid_fields_and_unsafe_urls_refused(fields):
 with pytest.raises(ValidationError):api.DealFields(**fields)

def test_only_definite_create_rejection_releases_browser_reference():
 for value in ({'existing_id':ID},{'missing':True}):
  with pytest.raises(HTTPException) as e:api.result(value,ID,creating=True)
  assert e.value.headers=={'X-Deal-Create-Rejected':'true'}
 for value in ({'conflict':True},None):
  with pytest.raises(HTTPException) as e:api.result(value,ID,creating=True)
  assert not e.value.headers
@pytest.mark.asyncio
async def test_transport_failure_preserves_reference_without_private_details(monkeypatch):
 db,req=setup(monkeypatch,{});db.rpc.return_value.execute.side_effect=RuntimeError('private payload')
 with pytest.raises(HTTPException) as e:await api.create(api.CreateDeal(request_id=ID,deal=api.NewDeal(lead_id=LEAD,deal_name='Internal QA')),req)
 assert e.value.status_code==503 and 'private payload' not in e.value.detail;assert db.rpc.call_args.args[1]['p_id']==ID
