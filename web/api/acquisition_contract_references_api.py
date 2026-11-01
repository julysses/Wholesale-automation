"""Authenticated reference discovery for the current or retained contract version."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,Response,Query
from schemas.acquisition_contract_references import ContractReference,ContractReferencePage
from schemas.acquisition_contract_documents import DocumentPurpose
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version,rpc,uncertain

router=APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/references')


def fresh(value,workspace,contract,version):
    now=datetime.now(timezone.utc)
    return ((value.workspace_id,value.contract_id,value.contract_version)==(workspace,contract,version)
            and now-timedelta(seconds=30)<=value.checked_at<=now+timedelta(seconds=5))


@router.get('')
async def references(workspace_id:UUID,contract_id:UUID,contract_version:Version,response:Response,
                     purpose:DocumentPurpose,after:UUID|None=None,limit:int=Query(20,ge=1,le=50),store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'contract_reference_candidates',{'p_workspace':str(workspace_id),'p_contract':str(contract_id),
        'p_version':contract_version,'p_purpose':purpose,'p_after':str(after) if after else None,'p_limit':limit})
    try:
        page=ContractReferencePage.model_validate(raw)
        if (not fresh(page,workspace_id,contract_id,contract_version) or page.purpose!=purpose or len(page.items)>limit
                or page.next_after is not None and len(page.items)!=limit
                or after is not None and any(row.artifact_id.int<=after.int for row in page.items)):
            raise ValueError('Current exact reference page required')
    except (ValueError,TypeError):raise uncertain('Contract document references could not be confirmed. Refresh before continuing.') from None
    return page.model_dump(mode='json')


@router.get('/{artifact_id}')
async def reference(workspace_id:UUID,contract_id:UUID,contract_version:Version,artifact_id:UUID,
                    response:Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'contract_reference_state',{'p_workspace':str(workspace_id),'p_contract':str(contract_id),
                                                'p_version':contract_version,'p_artifact':str(artifact_id)})
    try:
        value=ContractReference.model_validate(raw)
        if not fresh(value,workspace_id,contract_id,contract_version) or value.artifact_id!=artifact_id:
            raise ValueError('Current exact reference required')
    except (ValueError,TypeError):raise uncertain('Contract document reference could not be confirmed. Refresh before continuing.') from None
    return value.model_dump(mode='json')
