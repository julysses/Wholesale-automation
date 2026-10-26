"""Narrow server-owned calculation worker; never a fallback for user requests.

Only two worker RPCs are allowed. Inputs come from a reserved database snapshot,
not the HTTP client's result payload. A pending request can be retried safely:
completion is immutable/idempotent and never calls a provider or creates offers.
"""
import os
from uuid import UUID

import httpx
from pydantic import ValidationError

from schemas.acquisition_underwriting import UnderwritingPreview
from tools.acquisition_underwriting import CALCULATION_VERSION, calculate_preview


class CalculationUnavailable(RuntimeError):
    pass


def calculate_snapshot(snapshot):
    if not isinstance(snapshot,dict) or snapshot.get('calculation_version') != CALCULATION_VERSION:
        raise CalculationUnavailable('Calculation version is unavailable')
    try:
        request=UnderwritingPreview.model_validate(snapshot.get('inputs'))
    except ValidationError:
        return {'calculation_version':CALCULATION_VERSION,'status':'invalid','error_code':'INVALID_INPUTS',
                'binding_offer':False,'human_approval_required':True,'persisted':False}
    return calculate_preview(request)


async def _rpc(client, name, body):
    if name not in {'read_acquisition_calculation','complete_acquisition_calculation'}:
        raise CalculationUnavailable('Unsupported calculation operation')
    try:
        response=await client.post('rpc/'+name,json=body)
        if response.status_code != 200:
            raise CalculationUnavailable('Calculation database operation unavailable')
        value=response.json()
        if not isinstance(value,dict):
            raise CalculationUnavailable('Invalid calculation database result')
        return value
    except (httpx.HTTPError,ValueError):
        raise CalculationUnavailable('Calculation database operation unavailable') from None


async def process_reserved_analysis(workspace_id, analysis_id):
    workspace_id=str(UUID(str(workspace_id)));analysis_id=str(UUID(str(analysis_id)))
    if os.getenv('ACQUISITION_ENABLED','').lower() != 'true' or os.getenv('ACQUISITION_CALCULATOR_ENABLED','').lower() != 'true':
        return {'status':'pending','reason':'CALCULATOR_NOT_ENABLED'}
    # Explicit worker credential only. Never use the caller JWT or silently fall
    # back to the generic application's service credential.
    key=os.getenv('ACQUISITION_CALCULATOR_SERVICE_KEY','')
    url=(os.getenv('VITE_SUPABASE_URL') or os.getenv('SUPABASE_URL') or '').rstrip('/')
    if not key or not url.startswith('https://'):
        return {'status':'pending','reason':'CALCULATOR_NOT_CONFIGURED'}
    async with httpx.AsyncClient(base_url=url+'/rest/v1/',timeout=15.0,follow_redirects=False,
                                headers={'apikey':key,'Authorization':'Bearer '+key}) as client:
        snapshot=await _rpc(client,'read_acquisition_calculation',{'p_id':analysis_id,'p_workspace':workspace_id})
        if snapshot.get('id') != analysis_id or snapshot.get('workspace_id') != workspace_id:
            raise CalculationUnavailable('Calculation identity mismatch')
        if snapshot.get('status') in {'calculated','incomplete','invalid'}:
            return {'status':snapshot['status']}
        if snapshot.get('status') != 'pending' or not isinstance(snapshot.get('input_hash'),str) or len(snapshot['input_hash']) != 64:
            raise CalculationUnavailable('Invalid calculation snapshot')
        output=calculate_snapshot(snapshot)
        completed=await _rpc(client,'complete_acquisition_calculation',{
            'p_id':analysis_id,'p_workspace':workspace_id,'p_input_hash':snapshot['input_hash'],'p_outputs':output,
        })
        if completed.get('id') != analysis_id or completed.get('status') != output['status']:
            raise CalculationUnavailable('Calculation completion is unconfirmed')
        return {'status':completed['status']}
