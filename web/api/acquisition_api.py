"""Acquisition workspace administration; unavailable until explicitly enabled."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tools.acquisition_store import acquisition_store

router = APIRouter(prefix='/api/acquisition', tags=['Acquisition'])


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    name: str = Field(min_length=1, max_length=160)


class MembershipChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['owner','admin','operator','acquisition_caller','agency_manager']
    status: Literal['active','revoked']


class LeadBinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lead_id: UUID
    property_id: UUID | None = None


class LeadAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: UUID | None


@router.get('/workspaces')
async def workspaces(store=Depends(acquisition_store)):
    return await store.request('GET', 'workspaces', params={
        'select': 'id,name,status,created_by,created_at', 'order': 'created_at,id', 'limit': '100',
    })


@router.post('/workspaces')
async def create_workspace(body: WorkspaceCreate, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/create_acquisition_workspace',
                               body={'p_id': str(body.id), 'p_name': body.name})


@router.get('/workspaces/{workspace_id}/memberships')
async def memberships(workspace_id: UUID, store=Depends(acquisition_store)):
    return await store.request('GET', 'workspace_memberships', params={
        'select': 'workspace_id,user_id,role,status,updated_at',
        'workspace_id': 'eq.'+str(workspace_id), 'order': 'user_id', 'limit': '100',
    })


@router.put('/workspaces/{workspace_id}/memberships/{user_id}')
async def set_membership(workspace_id: UUID, user_id: UUID, body: MembershipChange,
                         store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/set_acquisition_membership', body={
        'p_workspace': str(workspace_id), 'p_user': str(user_id),
        'p_role': body.role, 'p_status': body.status,
    })


@router.post('/workspaces/{workspace_id}/leads')
async def bind_lead(workspace_id: UUID, body: LeadBinding, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/bind_acquisition_lead', body={
        'p_workspace': str(workspace_id), 'p_lead': str(body.lead_id),
        'p_property': str(body.property_id) if body.property_id else None,
    })


@router.put('/workspaces/{workspace_id}/leads/{lead_id}/assignment')
async def assign_lead(workspace_id: UUID, lead_id: UUID, body: LeadAssignment,
                      store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/assign_acquisition_lead', body={
        'p_workspace': str(workspace_id), 'p_lead': str(lead_id),
        'p_user': str(body.user_id) if body.user_id else None,
    })


@router.get('/workspaces/{workspace_id}/leads')
async def list_leads(workspace_id: UUID, after: UUID | None = None,
                     limit: int = Query(20, ge=1, le=50), store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/list_acquisition_leads', body={
        'p_workspace': str(workspace_id), 'p_after': str(after) if after else None, 'p_limit': limit,
    })


class ContactImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_contact_id: UUID | None = None
    source_field: Literal['owner_phone_1','owner_phone_2','owner_phone_3','owner_email','phone','email']


@router.post('/workspaces/{workspace_id}/leads/{lead_id}/contacts/import')
async def import_contact(workspace_id: UUID, lead_id: UUID, body: ContactImport,
                         store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/import_acquisition_contact', body={
        'p_workspace': str(workspace_id), 'p_lead': str(lead_id),
        'p_source_contact': str(body.source_contact_id) if body.source_contact_id else None,
        'p_field': body.source_field,
    })


class ContactSuppression(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    channel: Literal['all','human_voice','ai_voice','prerecorded','sms','email','direct_mail']
    reason: Literal['seller_opt_out','wrong_number','legal_restriction','deceased','contact_preference']


@router.post('/workspaces/{workspace_id}/leads/{lead_id}/contacts/{contact_id}/suppressions')
async def suppress_contact(workspace_id: UUID, lead_id: UUID, contact_id: UUID, body: ContactSuppression,
                           store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/record_acquisition_suppression', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_lead': str(lead_id),
        'p_contact': str(contact_id), 'p_channel': body.channel, 'p_reason': body.reason,
    })


class OwnerCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    source_lead_id: UUID


class OwnerPropertyAssociation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    lead_id: UUID
    relationship: Literal['reported_owner','reported_representative']
    review_note: str = Field(min_length=10, max_length=2000)


class OwnerContactAssociation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    contact_point_id: UUID
    review_note: str = Field(min_length=10, max_length=2000)


@router.post('/workspaces/{workspace_id}/owners')
async def create_owner(workspace_id: UUID, body: OwnerCreate, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/create_acquisition_owner', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_lead': str(body.source_lead_id),
    })


@router.get('/workspaces/{workspace_id}/owners')
async def list_owners(workspace_id: UUID, after: UUID | None = None,
                      limit: int = Query(20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select':'id,source_lead_id,display_name,verification_status,created_at',
              'workspace_id':'eq.'+str(workspace_id), 'order':'id', 'limit':str(limit)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    return await store.request('GET', 'acquisition_owners', params=params)


@router.post('/workspaces/{workspace_id}/owners/{owner_id}/properties')
async def associate_owner(workspace_id: UUID, owner_id: UUID, body: OwnerPropertyAssociation,
                          store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/associate_acquisition_owner', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_owner': str(owner_id),
        'p_lead': str(body.lead_id), 'p_relationship': body.relationship, 'p_note': body.review_note,
    })


@router.post('/workspaces/{workspace_id}/owner-relationships/{relationship_id}/contacts')
async def associate_owner_contact(workspace_id: UUID, relationship_id: UUID,
                                  body: OwnerContactAssociation, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/associate_acquisition_owner_contact', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_relationship': str(relationship_id),
        'p_contact': str(body.contact_point_id), 'p_note': body.review_note,
    })


class PermissionImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_kind: Literal['website','facebook']
    source_id: UUID
    channel: Literal['sms','ai_voice']


class PermissionRevocation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    reason: Literal['seller_revoked','invalid_evidence','wrong_identity']


@router.post('/workspaces/{workspace_id}/leads/{lead_id}/contacts/{contact_id}/permissions/import')
async def import_permission(workspace_id: UUID, lead_id: UUID, contact_id: UUID,
                            body: PermissionImport, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/import_acquisition_permission', body={
        'p_workspace': str(workspace_id), 'p_lead': str(lead_id), 'p_contact': str(contact_id),
        'p_source_kind': body.source_kind, 'p_source': str(body.source_id), 'p_channel': body.channel,
    })


@router.post('/workspaces/{workspace_id}/permissions/{permission_id}/revocations')
async def revoke_permission(workspace_id: UUID, permission_id: UUID,
                            body: PermissionRevocation, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/revoke_acquisition_permission', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id),
        'p_permission': str(permission_id), 'p_reason': body.reason,
    })


@router.get('/workspaces/{workspace_id}/leads/{lead_id}/permissions')
async def list_permissions(workspace_id: UUID, lead_id: UUID, after: UUID | None = None,
                           limit: int = Query(20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select':'id,contact_point_id,channel,scope,selection,disclosure_version,asserted_at,expires_at,expiry_basis,effective_status,revoked_at',
              'workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),'order':'id','limit':str(limit)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    return await store.request('GET', 'acquisition_permission_status', params=params)


from schemas.acquisition_underwriting import UnderwritingPreview
from tools.acquisition_underwriting import calculate_preview


@router.post('/workspaces/{workspace_id}/leads/{lead_id}/underwriting/preview')
async def underwriting_preview(workspace_id: UUID, lead_id: UUID, body: UnderwritingPreview,
                                store=Depends(acquisition_store)):
    # Existing binding RLS permits only owner/admin/operator, never caller roles.
    rows = await store.request('GET','workspace_leads',params={
        'select':'workspace_id,lead_id,property_id','workspace_id':'eq.'+str(workspace_id),
        'lead_id':'eq.'+str(lead_id),'limit':'1',
    })
    if (not isinstance(rows,list) or len(rows)!=1 or rows[0].get('workspace_id')!=str(workspace_id)
            or rows[0].get('lead_id')!=str(lead_id)):
        raise HTTPException(403,'Workspace underwriting access is not authorized')
    return {**calculate_preview(body),'workspace_id':str(workspace_id),'lead_id':str(lead_id),
            'property_id':rows[0].get('property_id')}


class AnalysisReservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    inputs: UnderwritingPreview


@router.post('/workspaces/{workspace_id}/leads/{lead_id}/underwriting/scenarios')
async def save_scenario(workspace_id: UUID, lead_id: UUID, body: AnalysisReservation,
                        store=Depends(acquisition_store)):
    from tools.acquisition_calculator import process_reserved_analysis, CalculationUnavailable
    reserved=await store.request('POST','rpc/reserve_acquisition_analysis',body={
        'p_id':str(body.id),'p_workspace':str(workspace_id),'p_lead':str(lead_id),
        'p_inputs':body.inputs.model_dump(mode='json'),
    })
    if (not isinstance(reserved,dict) or reserved.get('id')!=str(body.id)
            or reserved.get('workspace_id')!=str(workspace_id) or reserved.get('lead_id')!=str(lead_id)):
        raise HTTPException(503,'Analysis reservation is unconfirmed; retry the same reference')
    try:
        calculation=await process_reserved_analysis(workspace_id,body.id)
    except CalculationUnavailable:
        calculation={'status':'pending','reason':'CALCULATION_UNCONFIRMED_RETRY_SAME_REFERENCE'}
    # Re-read through current user RLS, never return a privileged worker payload.
    rows=await store.request('GET','deal_analyses',params={
        'select':'id,workspace_id,lead_id,property_id,acquisition_revision,acquisition_strategy,calculation_version,acquisition_status,acquisition_inputs,acquisition_outputs,analyzed_at',
        'id':'eq.'+str(body.id),'workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),'limit':'1',
    })
    if (not isinstance(rows,list) or len(rows)!=1 or rows[0].get('id')!=str(body.id)
            or rows[0].get('workspace_id')!=str(workspace_id) or rows[0].get('lead_id')!=str(lead_id)):
        raise HTTPException(403,'Workspace analysis access is not authorized')
    return {'analysis':rows[0],'calculation':calculation,'binding_offer':False}


@router.get('/workspaces/{workspace_id}/leads/{lead_id}/underwriting/scenarios')
async def scenario_history(workspace_id: UUID, lead_id: UUID, after: int = Query(0,ge=0),
                           limit: int = Query(20,ge=1,le=50), store=Depends(acquisition_store)):
    return await store.request('GET','deal_analyses',params={
        'select':'id,property_id,acquisition_revision,acquisition_strategy,calculation_version,acquisition_status,acquisition_inputs,acquisition_outputs,analyzed_at',
        'workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),
        'acquisition_revision':'gt.'+str(after),'order':'acquisition_revision','limit':str(limit),
    })


from decimal import Decimal


class OfferProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    analysis_id: UUID
    case: Literal['base','downside','upside']
    amount: Decimal = Field(gt=0,lt=Decimal('1000000000000'),decimal_places=2,allow_inf_nan=False)
    note: str = Field(min_length=1,max_length=4000)


class OfferReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_sequence: int = Field(ge=1)
    status: Literal['amount_approved','rejected','withdrawn','approval_revoked']
    note: str = Field(min_length=1,max_length=4000)
    review_notes: dict[str,str] = Field(default_factory=dict,max_length=20)


@router.post('/workspaces/{workspace_id}/offers')
async def propose_offer(workspace_id: UUID, body: OfferProposal, store=Depends(acquisition_store)):
    return await store.request('POST','rpc/propose_acquisition_offer',body={
        'p_id':str(body.id),'p_workspace':str(workspace_id),'p_analysis':str(body.analysis_id),
        'p_case':body.case,'p_amount':str(body.amount),'p_note':body.note,
    })


@router.post('/workspaces/{workspace_id}/offers/{offer_id}/reviews')
async def review_offer(workspace_id: UUID, offer_id: UUID, body: OfferReview, store=Depends(acquisition_store)):
    return await store.request('POST','rpc/review_acquisition_offer',body={
        'p_id':str(body.id),'p_workspace':str(workspace_id),'p_offer':str(offer_id),
        'p_expected_sequence':body.expected_sequence,'p_status':body.status,'p_note':body.note,
        'p_review_notes':body.review_notes,
    })


@router.get('/workspaces/{workspace_id}/leads/{lead_id}/offers')
async def offer_history(workspace_id: UUID, lead_id: UUID, after: UUID | None = None,
                         limit: int = Query(20,ge=1,le=50), store=Depends(acquisition_store)):
    params={'select':'id,lead_id,deal_analysis_id,acquisition_case,target_offer,ceiling_offer,proposed_by,proposal_note,generated_at',
            'workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),'order':'id','limit':str(limit)}
    if after is not None: params['id']='gt.'+str(after)
    return await store.request('GET','offer_recommendations',params=params)


@router.get('/workspaces/{workspace_id}/offers/{offer_id}/reviews')
async def offer_reviews(workspace_id: UUID, offer_id: UUID, after: int = Query(0,ge=0),
                         limit: int = Query(20,ge=1,le=50), store=Depends(acquisition_store)):
    return await store.request('GET','acquisition_offer_events',params={
        'select':'id,sequence,status,actor_id,note,review_notes,created_at','workspace_id':'eq.'+str(workspace_id),
        'offer_id':'eq.'+str(offer_id),'sequence':'gt.'+str(after),'order':'sequence','limit':str(limit),
    })
