"""Acquisition workspace administration; unavailable until explicitly enabled."""
from datetime import date, datetime, timezone
from typing import Literal
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from tools.acquisition_store import acquisition_store
from schemas.acquisition_mail_preparation import ContentPreparationRequest, ContentPreparation, ContentReviewRequest, ContentReviewState
from tools.acquisition_mail_render import safe_text
from schemas.acquisition_mail_proof import MailProofRequest
from tools.acquisition_mail_proof import build_reviewed_mail_proof, ProofUnavailable
from web.api.acquisition_evidence_api import router as evidence_router
from web.api.acquisition_postal_api import router as postal_router

router = APIRouter(prefix='/api/acquisition', tags=['Acquisition'])
router.include_router(evidence_router)
router.include_router(postal_router)


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
    reserved=await store.request('POST','rpc/reserve_acquisition_analysis',body={
        'p_id':str(body.id),'p_workspace':str(workspace_id),'p_lead':str(lead_id),
        'p_inputs':body.inputs.model_dump(mode='json'),
    })
    if (not isinstance(reserved,dict) or reserved.get('id')!=str(body.id)
            or reserved.get('workspace_id')!=str(workspace_id) or reserved.get('lead_id')!=str(lead_id)):
        raise HTTPException(503,'Analysis reservation is unconfirmed; retry the same reference')
    return await _finish_reserved_analysis(store, workspace_id, lead_id, body.id)


async def _finish_reserved_analysis(store, workspace_id: UUID, lead_id: UUID, analysis_id: UUID):
    from tools.acquisition_calculator import process_reserved_analysis, CalculationUnavailable
    try:
        calculation=await process_reserved_analysis(workspace_id,analysis_id)
    except CalculationUnavailable:
        calculation={'status':'pending','reason':'CALCULATION_UNCONFIRMED_RETRY_SAME_REFERENCE'}
    # Re-read through current user RLS, never return a privileged worker payload.
    rows=await store.request('GET','deal_analyses',params={
        'select':'id,workspace_id,lead_id,property_id,acquisition_revision,acquisition_strategy,calculation_version,acquisition_status,acquisition_inputs,acquisition_outputs,analyzed_at',
        'id':'eq.'+str(analysis_id),'workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),'limit':'1',
    })
    if (not isinstance(rows,list) or len(rows)!=1 or rows[0].get('id')!=str(analysis_id)
            or rows[0].get('workspace_id')!=str(workspace_id) or rows[0].get('lead_id')!=str(lead_id)):
        raise HTTPException(403,'Workspace analysis access is not authorized')
    if calculation.get('status') == 'pending' and rows[0].get('acquisition_status') in {'calculated','incomplete','invalid'}:
        # A lost worker reply does not undo a committed result. This fresh,
        # user-authorized read confirms the outcome without another mutation.
        calculation={'status':rows[0]['acquisition_status'],'reason':'RECONCILED_FROM_SAVED_SCENARIO'}
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


@router.get('/workspaces/{workspace_id}/offers/{offer_id}/state')
async def current_offer_review(workspace_id: UUID, offer_id: UUID, store=Depends(acquisition_store)):
    return await store.request('POST','rpc/acquisition_offer_review_state',body={
        'p_workspace':str(workspace_id),'p_offer':str(offer_id),
    })


@router.get('/workspaces/{workspace_id}/offers')
async def offer_review_queue(workspace_id: UUID, after: UUID | None = None,
                             limit: int = Query(20,ge=1,le=50), store=Depends(acquisition_store)):
    return await store.request('POST','rpc/acquisition_offer_review_queue',body={
        'p_workspace':str(workspace_id),'p_after':str(after) if after is not None else None,'p_limit':limit,
    })


@router.get('/workspaces/{workspace_id}/leads/{lead_id}/summary')
async def acquisition_lead_summary(workspace_id: UUID, lead_id: UUID, store=Depends(acquisition_store)):
    bindings=await store.request('GET','workspace_leads',params={
        'select':'workspace_id,lead_id,property_id','workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),'limit':'1',
    })
    if (not isinstance(bindings,list) or len(bindings)!=1 or bindings[0].get('workspace_id')!=str(workspace_id)
            or bindings[0].get('lead_id')!=str(lead_id)):
        raise HTTPException(403,'Workspace lead access is not authorized')
    leads=await store.request('GET','leads',params={
        'select':'id,property_address,city','id':'eq.'+str(lead_id),'limit':'1',
    })
    if not isinstance(leads,list) or len(leads)!=1 or leads[0].get('id')!=str(lead_id):
        raise HTTPException(403,'Workspace lead access is not authorized')
    return {**leads[0],'property_id':bindings[0].get('property_id')}


@router.get('/workspaces/{workspace_id}/inquiries/health')
async def acquisition_inquiry_health(workspace_id: UUID, after: UUID | None = None,
                                     limit: int = Query(20, ge=1, le=50), store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_inquiry_health', body={
        'p_workspace': str(workspace_id), 'p_after': str(after) if after is not None else None, 'p_limit': limit,
    })


class InquiryRecovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_updated_at: AwareDatetime
    expected_reason: Literal['CREDENTIALS_INVALID','PERMISSION_DENIED','RETRY_EXHAUSTED','INVALID_PROVIDER_DATA','IDENTITY_CONFLICT','UNSUPPORTED_EVENT']
    review_note: str = Field(min_length=20, max_length=2000)
    evidence_ref: str = Field(min_length=1, max_length=500)


@router.post('/workspaces/{workspace_id}/inquiries/{receipt_id}/recoveries')
async def recover_inquiry(workspace_id: UUID, receipt_id: UUID, body: InquiryRecovery, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/recover_acquisition_inquiry', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_receipt': str(receipt_id),
        'p_expected_updated_at': body.expected_updated_at.isoformat(), 'p_expected_reason': body.expected_reason,
        'p_note': body.review_note, 'p_evidence_ref': body.evidence_ref,
    })


@router.get('/workspaces/{workspace_id}/inquiries/{receipt_id}/recoveries')
async def inquiry_recovery_history(workspace_id: UUID, receipt_id: UUID, store=Depends(acquisition_store)):
    return await store.request('GET', 'acquisition_inquiry_recoveries', params={
        'select': 'id,receipt_id,cycle,actor_id,reason_code,review_note,evidence_ref,previous_attempts,created_at',
        'workspace_id': 'eq.'+str(workspace_id), 'receipt_id': 'eq.'+str(receipt_id), 'order': 'cycle', 'limit': '3',
    })


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/candidates')
async def intake_identity_candidates(workspace_id: UUID, intake_id: UUID,
                                     limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_intake_candidates', body={
        'p_workspace': str(workspace_id), 'p_intake': str(intake_id), 'p_limit': limit,
    })


class IntakeIdentityReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_sequence: int = Field(ge=0)
    preparation_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: Literal['link_property', 'repeat_inquiry', 'revoke']
    target_lead_id: UUID | None = None
    target_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    property_basis: Literal['parcel_document', 'verified_address'] | None = None
    property_evidence_ref: str | None = Field(default=None, min_length=10, max_length=500)
    seller_evidence_ref: str | None = Field(default=None, min_length=10, max_length=500)
    review_note: str = Field(min_length=20, max_length=2000)


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/identity-state')
async def intake_identity_state(workspace_id: UUID, intake_id: UUID, target: UUID | None = None,
                                store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_intake_identity_state', body={
        'p_workspace': str(workspace_id), 'p_intake': str(intake_id), 'p_target': str(target) if target else None,
    })


@router.post('/workspaces/{workspace_id}/intakes/{intake_id}/identity-reviews')
async def review_intake_identity(workspace_id: UUID, intake_id: UUID, body: IntakeIdentityReview,
                                 store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/review_acquisition_intake_identity', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_intake': str(intake_id),
        'p_expected_sequence': body.expected_sequence, 'p_preparation_hash': body.preparation_hash,
        'p_action': body.action, 'p_target': str(body.target_lead_id) if body.target_lead_id else None,
        'p_target_hash': body.target_hash, 'p_property_basis': body.property_basis,
        'p_property_evidence_ref': body.property_evidence_ref, 'p_seller_evidence_ref': body.seller_evidence_ref,
        'p_note': body.review_note,
    })


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/identity-reviews')
async def intake_identity_history(workspace_id: UUID, intake_id: UUID,
                                  before: int | None = Query(default=None, ge=1),
                                  limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': '*', 'workspace_id': 'eq.'+str(workspace_id), 'intake_id': 'eq.'+str(intake_id),
              'order': 'sequence.desc', 'limit': str(limit)}
    if before is not None:
        params['sequence'] = 'lt.'+str(before)
    return await store.request('GET', 'acquisition_intake_identity_reviews', params=params)


@router.get('/workspaces/{workspace_id}/intakes')
async def acquisition_intakes(workspace_id: UUID, after: UUID | None = None,
                              limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,lead_id,classification,created_at,source_type,inbound_integration_id,inbound_call_id,inbound_revision', 'workspace_id': 'eq.'+str(workspace_id),
              'order': 'id', 'limit': str(limit+1)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'seller_intakes', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit-1]['id'] if len(rows)>limit else None}


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}')
async def acquisition_intake_detail(workspace_id: UUID, intake_id: UUID, store=Depends(acquisition_store)):
    rows = await store.request('GET', 'seller_intakes', params={
        'select': 'id,lead_id,classification,created_at,source_type,inbound_integration_id,inbound_call_id,inbound_revision,prepared_answers,preparation_hash,normalization_notes',
        'workspace_id': 'eq.'+str(workspace_id), 'id': 'eq.'+str(intake_id), 'limit': '1',
    })
    if not rows:
        raise HTTPException(status_code=404, detail='Intake unavailable')
    return rows[0]


class IntakeAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_sequence: int = Field(ge=0)
    evidence_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/qualification-state')
async def intake_qualification_state(workspace_id: UUID, intake_id: UUID, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_intake_qualification_state', body={
        'p_workspace': str(workspace_id), 'p_intake': str(intake_id),
    })


@router.post('/workspaces/{workspace_id}/intakes/{intake_id}/assessments')
async def record_intake_assessment(workspace_id: UUID, intake_id: UUID, body: IntakeAssessment, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/record_acquisition_intake_assessment', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_intake': str(intake_id),
        'p_expected_sequence': body.expected_sequence, 'p_evidence_hash': body.evidence_hash,
    })


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/assessments')
async def intake_assessment_history(workspace_id: UUID, intake_id: UUID,
                                     before: int | None = Query(default=None, ge=1),
                                     limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,sequence,policy_version,classification,evidence_hash,assessment,actor_id,created_at',
              'workspace_id': 'eq.'+str(workspace_id), 'intake_id': 'eq.'+str(intake_id),
              'order': 'sequence.desc', 'limit': str(limit)}
    if before is not None:
        params['sequence'] = 'lt.'+str(before)
    return await store.request('GET', 'acquisition_intake_assessments', params=params)


class IntakeAnalysisReservation(AnalysisReservation):
    evidence_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.post('/workspaces/{workspace_id}/intakes/{intake_id}/underwriting/scenarios')
async def save_intake_scenario(workspace_id: UUID, intake_id: UUID, body: IntakeAnalysisReservation,
                               store=Depends(acquisition_store)):
    reserved = await store.request('POST', 'rpc/reserve_acquisition_intake_analysis', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_intake': str(intake_id),
        'p_evidence_hash': body.evidence_hash, 'p_inputs': body.inputs.model_dump(mode='json'),
    })
    if (not isinstance(reserved, dict) or reserved.get('id') != str(body.id)
            or reserved.get('workspace_id') != str(workspace_id) or reserved.get('intake_id') != str(intake_id)):
        raise HTTPException(503, 'Intake analysis reservation is unconfirmed; retry the same reference')
    try:
        canonical_lead = UUID(str(reserved['lead_id']))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Canonical analysis identity is unconfirmed') from None
    result = await _finish_reserved_analysis(store, workspace_id, canonical_lead, body.id)
    context = await store.request('POST', 'rpc/acquisition_intake_analysis_state', body={
        'p_workspace': str(workspace_id), 'p_analysis': str(body.id),
    })
    if (not isinstance(context, dict) or context.get('analysis_id') != str(body.id)
            or context.get('intake_id') != str(intake_id) or context.get('has_intake') is not True
            or not isinstance(context.get('qualification_current'), bool)):
        raise HTTPException(503, 'Intake analysis state is unconfirmed')
    return {**result, 'intake_context': context}


@router.get('/workspaces/{workspace_id}/underwriting/scenarios/{analysis_id}/intake-context')
async def saved_analysis_intake_context(workspace_id: UUID, analysis_id: UUID, store=Depends(acquisition_store)):
    """Read current source validity and immutable retry evidence through the user's RLS."""
    context = await store.request('POST', 'rpc/acquisition_intake_analysis_state', body={
        'p_workspace': str(workspace_id), 'p_analysis': str(analysis_id),
    })
    if (not isinstance(context, dict) or context.get('analysis_id') != str(analysis_id)
            or not isinstance(context.get('has_intake'), bool)
            or not isinstance(context.get('qualification_current'), bool)):
        raise HTTPException(503, 'Analysis provenance unavailable')
    if not context['has_intake']:
        return {**context, 'evidence_hash': None}
    rows = await store.request('GET', 'acquisition_analysis_intakes', params={
        'select': 'analysis_id,intake_id,assessment_id,evidence_hash',
        'workspace_id': 'eq.'+str(workspace_id), 'analysis_id': 'eq.'+str(analysis_id), 'limit': '1',
    })
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
            or any(rows[0].get(key) != context.get(key) for key in ('analysis_id', 'intake_id', 'assessment_id'))
            or not isinstance(rows[0].get('evidence_hash'), str)
            or len(rows[0]['evidence_hash']) != 64
            or any(c not in '0123456789abcdef' for c in rows[0]['evidence_hash'])):
        raise HTTPException(503, 'Analysis provenance unavailable')
    return {**context, 'evidence_hash': rows[0]['evidence_hash']}


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/attribution')
async def intake_source_attribution(workspace_id: UUID, intake_id: UUID, store=Depends(acquisition_store)):
    from tools.acquisition_attribution import facebook_attribution
    rows = await store.request('GET', 'seller_intakes', params={
        'select': 'id,lead_id,prepared_answers', 'workspace_id': 'eq.'+str(workspace_id),
        'id': 'eq.'+str(intake_id), 'limit': '1',
    })
    if not rows:
        raise HTTPException(404, 'Intake unavailable')
    return {'intake_id': rows[0]['id'], 'lead_id': rows[0]['lead_id'],
            'attribution': facebook_attribution(rows[0]['prepared_answers'])}


class AcquisitionCampaignDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    channel: Literal['facebook', 'inbound_voice', 'direct_mail', 'online_offer', 'human_voice', 'agency_voice']
    budget_cents: int = Field(strict=True, ge=0, le=100000000000)
    currency: Literal['USD']


@router.post('/workspaces/{workspace_id}/campaigns')
async def create_campaign_draft(workspace_id: UUID, body: AcquisitionCampaignDraft, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/create_acquisition_campaign', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_name': body.name,
        'p_channel': body.channel, 'p_budget_cents': body.budget_cents, 'p_currency': body.currency,
    })


@router.get('/workspaces/{workspace_id}/campaigns')
async def workspace_campaigns(workspace_id: UUID, after: UUID | None = None,
                              limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,name,workspace_id,status,acquisition_channel,acquisition_budget_cents,acquisition_currency,created_at',
              'workspace_id': 'eq.'+str(workspace_id), 'order': 'id', 'limit': str(limit+1)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'ad_campaigns', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit-1]['id'] if len(rows)>limit else None}


@router.get('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-content')
async def mail_content_history(workspace_id: UUID, campaign_id: UUID, after: UUID | None = None,
                                limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,workspace_id,campaign_id,content_id,version,action,creative_id,destination_review_id,company_name,created_at',
              'workspace_id': 'eq.' + str(workspace_id), 'campaign_id': 'eq.' + str(campaign_id),
              'order': 'id', 'limit': str(limit + 1)}
    if after is not None:
        params['id'] = 'gt.' + str(after)
    rows = await store.request('GET', 'acquisition_mail_content_reviews', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit - 1]['id'] if len(rows) > limit else None}


@router.post('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-content/prepare')
async def prepare_mail_content(workspace_id: UUID, campaign_id: UUID, body: ContentPreparationRequest,
                               store=Depends(acquisition_store)):
    try:
        safe_text(body.company_name)
        if any(c in body.company_name for c in '{}'):
            raise ValueError('Company identity cannot contain placeholders')
    except ValueError:
        raise HTTPException(422, 'A plain-text proposed company identity is required')
    result = await store.request('POST', 'rpc/prepare_acquisition_mail_content', body={
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_creative': str(body.creative_id), 'p_destination_review': str(body.destination_review_id),
        'p_company_name': body.company_name})
    try:
        prepared = ContentPreparation.model_validate(result)
        snapshot = prepared.snapshot
        if (snapshot.workspace_id != workspace_id or snapshot.campaign_id != campaign_id
                or snapshot.template.creative_id != body.creative_id
                or snapshot.destination.review_id != body.destination_review_id
                or snapshot.company_name != body.company_name):
            raise ValueError('Preparation scope changed')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Mail content preparation could not be confirmed')
    return result


@router.post('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-content/{content_id}/proof')
async def mail_content_proof(workspace_id: UUID, campaign_id: UUID, content_id: UUID,
                              body: MailProofRequest, response: Response, store=Depends(acquisition_store)):
    context = await store.request('POST', 'rpc/acquisition_mail_proof_context', body={
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_content': str(content_id), 'p_lead': str(body.lead_id)})
    response.headers['Cache-Control'] = 'no-store'
    try:
        return build_reviewed_mail_proof(context, workspace_id=workspace_id, campaign_id=campaign_id,
            content_id=content_id, lead_id=body.lead_id, now=datetime.now(timezone.utc))
    except ProofUnavailable:
        raise HTTPException(409, 'Refresh the content approval and property records before previewing')
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(503, 'Reviewed mail proof could not be confirmed')


@router.post('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-content/{content_id}/reviews')
async def review_mail_content(workspace_id: UUID, campaign_id: UUID, content_id: UUID,
                              body: ContentReviewRequest, store=Depends(acquisition_store)):
    receipt = await store.request('POST', 'rpc/review_acquisition_mail_content', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_content': str(content_id), 'p_expected_version': body.expected_version, 'p_action': body.action,
        'p_creative': str(body.creative_id) if body.creative_id else None,
        'p_destination_review': str(body.destination_review_id) if body.destination_review_id else None,
        'p_company_name': body.company_name, 'p_preparation_hash': body.preparation_hash,
        'p_evidence_ref': str(body.evidence_ref) if body.evidence_ref else None, 'p_evidence_hash': body.evidence_hash,
        'p_expires_at': body.expires_at.isoformat() if body.expires_at else None, 'p_note': body.note})
    expected = {'review_id': str(body.id), 'workspace_id': str(workspace_id), 'content_id': str(content_id),
                'version': body.expected_version + 1, 'execution_authorized': False}
    if (not isinstance(receipt, dict) or set(receipt) != set(expected) | {'duplicate'}
            or any(receipt.get(key) != value for key, value in expected.items())
            or type(receipt.get('version')) is not int or type(receipt.get('duplicate')) is not bool
            or receipt.get('execution_authorized') is not False):
        raise HTTPException(503, 'Content review could not be confirmed; retain the same request for reconciliation')
    return receipt


@router.get('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-content/{content_id}')
async def mail_content_state(workspace_id: UUID, campaign_id: UUID, content_id: UUID,
                              store=Depends(acquisition_store)):
    result = await store.request('POST', 'rpc/acquisition_mail_content_state', body={
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_content': str(content_id)})
    try:
        state = ContentReviewState.model_validate(result)
        if (state.workspace_id, state.campaign_id, state.content_id) != (workspace_id, campaign_id, content_id):
            raise ValueError('Content scope mismatch')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Content review state could not be confirmed')
    return result


class MailDestinationReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_version: int = Field(strict=True, ge=0, lt=1000000000)
    action: Literal['approved','withdrawn']
    mode: Literal['phone','landing_page'] | None = None
    value: str | None = Field(default=None, min_length=1, max_length=2048)
    verification_ref: UUID | None = None
    verification_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    verified_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    note: str = Field(min_length=20, max_length=2000)

    @model_validator(mode='after')
    def validate_review(self):
        evidence = (self.mode, self.value, self.verification_ref, self.verification_hash, self.verified_at, self.expires_at)
        if len(self.note.strip()) < 20 or (self.action == 'approved' and any(v is None for v in evidence)):
            raise ValueError('Documented destination evidence required')
        if self.action == 'withdrawn' and any(v is not None for v in evidence):
            raise ValueError('Withdrawal retains prior destination evidence')
        if self.verified_at is not None and self.expires_at is not None and self.expires_at <= self.verified_at:
            raise ValueError('Verification expiry must follow observation')
        return self


@router.get('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-destinations')
async def mail_destination_history(workspace_id: UUID, campaign_id: UUID, after: UUID | None = None,
                                   limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,workspace_id,campaign_id,destination_id,version,action,mode,value,created_at',
              'workspace_id': 'eq.'+str(workspace_id), 'campaign_id': 'eq.'+str(campaign_id),
              'order': 'id', 'limit': str(limit+1)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'acquisition_mail_destination_reviews', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit-1]['id'] if len(rows)>limit else None}


@router.post('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-destinations/{destination_id}/reviews')
async def review_mail_destination(workspace_id: UUID, campaign_id: UUID, destination_id: UUID,
                                  body: MailDestinationReview, store=Depends(acquisition_store)):
    receipt = await store.request('POST', 'rpc/review_acquisition_mail_destination', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_destination': str(destination_id), 'p_expected_version': body.expected_version, 'p_action': body.action,
        'p_mode': body.mode, 'p_value': body.value,
        'p_verification_ref': str(body.verification_ref) if body.verification_ref else None,
        'p_verification_hash': body.verification_hash,
        'p_verified_at': body.verified_at.isoformat() if body.verified_at else None,
        'p_expires_at': body.expires_at.isoformat() if body.expires_at else None, 'p_note': body.note,
    })
    expected = {'review_id': str(body.id), 'workspace_id': str(workspace_id), 'destination_id': str(destination_id),
                'version': body.expected_version+1, 'execution_authorized': False}
    if (not isinstance(receipt, dict) or set(receipt) != set(expected) | {'duplicate'}
            or any(receipt.get(key) != value for key, value in expected.items())
            or type(receipt.get('version')) is not int or type(receipt.get('duplicate')) is not bool
            or receipt.get('execution_authorized') is not False):
        raise HTTPException(503, 'Destination review could not be confirmed; retain the same request for reconciliation')
    return receipt


@router.get('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-destinations/{destination_id}')
async def mail_destination_state(workspace_id: UUID, campaign_id: UUID, destination_id: UUID,
                                 store=Depends(acquisition_store)):
    state = await store.request('POST', 'rpc/acquisition_mail_destination_state', body={
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_destination': str(destination_id)})
    expected = {'workspace_id': str(workspace_id), 'campaign_id': str(campaign_id), 'destination_id': str(destination_id)}
    if (not isinstance(state, dict) or set(state) != set(expected) | {'version','latest_review','review_current','status','execution_authorized','checked_at'}
            or any(state.get(k) != v for k,v in expected.items())
            or type(state.get('version')) is not int or state['version'] < 0
            or type(state.get('review_current')) is not bool or state.get('execution_authorized') is not False
            or state.get('status') not in {'pending_review','approved','withdrawn','requires_review'}
            or state['review_current'] != (state['status'] == 'approved')):
        raise HTTPException(503, 'Destination review state could not be confirmed')
    latest = state.get('latest_review')
    if state['version'] == 0:
        valid = latest is None and state['status'] == 'pending_review'
    else:
        valid = (isinstance(latest,dict) and all(latest.get(k) == v for k,v in expected.items())
                 and type(latest.get('version')) is int and latest['version'] == state['version']
                 and latest.get('action') in {'approved','withdrawn'}
                 and (latest['action'] == 'withdrawn') == (state['status'] == 'withdrawn')
                 and state['status'] != 'pending_review')
    if not valid:
        raise HTTPException(503, 'Destination review evidence could not be confirmed')
    return state


class MailTemplateDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    template_id: UUID
    expected_version: int = Field(strict=True, ge=0, lt=1000000000)
    name: str = Field(min_length=1, max_length=200)
    format: Literal['letter','postcard']
    tracking_mode: Literal['phone','landing_page']
    body: str = Field(min_length=1, max_length=20000)

    @model_validator(mode='after')
    def validate_content(self):
        if not self.name.strip() or not self.body.strip():
            raise ValueError('Name and content required')
        required = '{{tracking_phone}}' if self.tracking_mode == 'phone' else '{{tracking_url}}'
        rest = re.sub(r'\{\{(tracking_phone|tracking_url|property_address|company_name)\}\}', '', self.body)
        if required not in self.body or '{' in rest or '}' in rest:
            raise ValueError('Tracked destination and supported placeholders required')
        return self


@router.post('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-templates')
async def save_mail_template(workspace_id: UUID, campaign_id: UUID, body: MailTemplateDraft,
                             store=Depends(acquisition_store)):
    receipt = await store.request('POST', 'rpc/save_acquisition_mail_template', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_template': str(body.template_id), 'p_expected_version': body.expected_version,
        'p_name': body.name, 'p_format': body.format, 'p_tracking_mode': body.tracking_mode, 'p_body': body.body,
    })
    expected = {'id': str(body.id), 'workspace_id': str(workspace_id), 'template_id': str(body.template_id),
                'version': body.expected_version+1, 'status': 'draft', 'execution_authorized': False}
    if (not isinstance(receipt, dict) or set(receipt) != set(expected) | {'duplicate'}
            or any(receipt.get(key) != value for key, value in expected.items())
            or type(receipt.get('version')) is not int or type(receipt.get('duplicate')) is not bool
            or receipt.get('execution_authorized') is not False):
        raise HTTPException(503, 'Mail draft save could not be confirmed; retain the same request for reconciliation')
    return receipt


@router.get('/workspaces/{workspace_id}/campaigns/{campaign_id}/mail-templates')
async def mail_template_versions(workspace_id: UUID, campaign_id: UUID, template_id: UUID | None = None,
                                 after: UUID | None = None, limit: int = Query(default=20, ge=1, le=50),
                                 store=Depends(acquisition_store)):
    params = {'select': 'id,workspace_id,campaign_id,acquisition_template_id,acquisition_template_version,name,primary_text,acquisition_mail_format,acquisition_tracking_mode,status,created_at',
              'workspace_id': 'eq.'+str(workspace_id), 'campaign_id': 'eq.'+str(campaign_id),
              'acquisition_template_id': 'not.is.null', 'order': 'id', 'limit': str(limit+1)}
    if template_id is not None:
        params['acquisition_template_id'] = 'eq.'+str(template_id)
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'ad_creatives', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit-1]['id'] if len(rows)>limit else None}


class AcquisitionCampaignLinkReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_sequence: int = Field(strict=True, ge=0)
    preparation_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: Literal['link', 'revoke']
    campaign_id: UUID | None = None
    ad_account_id: str | None = Field(default=None, pattern=r'^[0-9]{1,200}$')
    evidence_ref: str = Field(min_length=10, max_length=500)
    review_note: str = Field(min_length=20, max_length=2000)


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/campaign-link-state')
async def campaign_link_state(workspace_id: UUID, intake_id: UUID, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_campaign_link_state', body={
        'p_workspace': str(workspace_id), 'p_intake': str(intake_id)})


@router.post('/workspaces/{workspace_id}/intakes/{intake_id}/campaign-link-reviews')
async def review_campaign_link(workspace_id: UUID, intake_id: UUID, body: AcquisitionCampaignLinkReview, store=Depends(acquisition_store)):
    if (body.action == 'link' and (body.campaign_id is None or body.ad_account_id is None)) or (
            body.action == 'revoke' and (body.campaign_id is not None or body.ad_account_id is not None)):
        raise HTTPException(422, 'Link requires a campaign and ad account; revocation cannot assert either.')
    return await store.request('POST', 'rpc/review_acquisition_campaign_link', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_intake': str(intake_id),
        'p_expected_sequence': body.expected_sequence, 'p_preparation_hash': body.preparation_hash,
        'p_action': body.action, 'p_campaign': str(body.campaign_id) if body.campaign_id else None,
        'p_ad_account': body.ad_account_id, 'p_evidence_ref': body.evidence_ref, 'p_note': body.review_note})


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/campaign-link-reviews')
async def campaign_link_reviews(workspace_id: UUID, intake_id: UUID, before: int | None = Query(default=None, ge=1),
                                limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    state = await store.request('POST', 'rpc/acquisition_campaign_link_state', body={
        'p_workspace': str(workspace_id), 'p_intake': str(intake_id)})
    params = {'select': 'id,workspace_id,integration_id,external_campaign_id,sequence,action,campaign_id,ad_account_id,intake_id,evidence_ref,review_note,created_at',
              'workspace_id': 'eq.'+str(workspace_id), 'integration_id': 'eq.'+state['integration_id'],
              'external_campaign_id': 'eq.'+state['external_campaign_id'], 'order': 'sequence.desc', 'limit': str(limit)}
    if before is not None:
        params['sequence'] = 'lt.'+str(before)
    return await store.request('GET', 'acquisition_campaign_links', params=params)


class AcquisitionSourceCampaignCapture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    link_review_id: UUID


@router.post('/workspaces/{workspace_id}/intakes/{intake_id}/source-campaign-reviews')
async def capture_source_campaign(workspace_id: UUID, intake_id: UUID, body: AcquisitionSourceCampaignCapture, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/capture_acquisition_source_campaign', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_source': str(intake_id), 'p_link_review': str(body.link_review_id)})


@router.get('/workspaces/{workspace_id}/leads/{lead_id}/sources')
async def acquisition_lead_sources(workspace_id: UUID, lead_id: UUID, after: UUID | None = None,
                                   limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,workspace_id,lead_id,receipt_id,integration_id,source_type,preparation_hash,external_lead_id,form_id,external_campaign_id,adset_id,ad_id,submitted_at_raw,utm_data,projection_version,recorded_at,inbound_event_id,inbound_revision',
              'workspace_id': 'eq.'+str(workspace_id), 'lead_id': 'eq.'+str(lead_id), 'order': 'id', 'limit': str(limit+1)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'acquisition_lead_sources', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit-1]['id'] if len(rows)>limit else None}


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}/source-campaign-reviews')
async def source_campaign_reviews(workspace_id: UUID, intake_id: UUID, after: UUID | None = None,
                                  limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': 'id,workspace_id,source_id,link_review_id,campaign_id,preparation_hash,created_at',
              'workspace_id': 'eq.'+str(workspace_id), 'source_id': 'eq.'+str(intake_id), 'order': 'id', 'limit': str(limit+1)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'acquisition_source_campaign_reviews', params=params)
    # Read current authority after history, so a later capture cannot be labelled
    # current using an earlier campaign review. This is a reporting snapshot only.
    state = await store.request('POST', 'rpc/acquisition_campaign_link_state', body={
        'p_workspace': str(workspace_id), 'p_intake': str(intake_id)})
    current_review = (state.get('latest_review') or {}).get('id') if state.get('link_current') is True else None
    current_capture = None
    if current_review is not None:
        matches = await store.request('GET', 'acquisition_source_campaign_reviews', params={
            'select': params['select'], 'workspace_id': params['workspace_id'], 'source_id': params['source_id'],
            'link_review_id': 'eq.'+current_review, 'order': 'id', 'limit': '1'})
        current_capture = {**matches[0], 'attribution_current': True} if matches else None
    return {'workspace_id': str(workspace_id), 'source_id': str(intake_id), 'preparation_hash': state['preparation_hash'],
            'current_link_review_id': current_review, 'current_campaign_id': state.get('internal_campaign_id') if current_review else None,
            'current_capture': current_capture,
            'items': [{**row, 'attribution_current': current_review is not None and row['link_review_id'] == current_review} for row in rows[:limit]],
            'next_after': rows[limit-1]['id'] if len(rows)>limit else None, 'execution_authorized': False}


@router.get('/workspaces/{workspace_id}/leads/{lead_id}/source-touches')
async def acquisition_property_source_touches(workspace_id: UUID, lead_id: UUID, after: UUID | None = None,
                                              limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_property_source_touches', body={
        'p_workspace': str(workspace_id), 'p_lead': str(lead_id), 'p_after': str(after) if after else None, 'p_limit': limit})


@router.get('/workspaces/{workspace_id}/campaigns/{campaign_id}/cost-coverage')
async def acquisition_cost_coverage(workspace_id: UUID, campaign_id: UUID, start_date: date, end_date: date,
                                    as_of: AwareDatetime | None = None, store=Depends(acquisition_store)):
    from tools.acquisition_costs import campaign_cost_coverage
    cutoff = as_of or datetime.now(timezone.utc)
    if end_date < start_date or (end_date-start_date).days > 365 or cutoff > datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail='Invalid cost reporting window')
    value = await store.request('POST', 'rpc/acquisition_cost_evidence', body={
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_start': start_date.isoformat(),
        'p_end': end_date.isoformat(), 'p_as_of': cutoff.isoformat()})
    try:
        if (not isinstance(value, dict) or value.get('workspace_id') != str(workspace_id)
            or value.get('campaign_id') != str(campaign_id) or value.get('start_date') != start_date.isoformat()
            or value.get('end_date') != end_date.isoformat() or value.get('truncated') is not False
            or value.get('execution_authorized') is not False or value.get('currency') != 'USD'
            or datetime.fromisoformat(value['as_of'].replace('Z', '+00:00')) != cutoff
            or not isinstance(value.get('items'), list) or len(value['items']) > 366):
            raise ValueError('Invalid evidence envelope')
        rows = value['items']
        if any(type(row.get('attribution_current')) is not bool or row.get('basis') != 'reviewed_import' for row in rows):
            raise ValueError('Invalid evidence authority')
        zone = value.get('reporting_timezone')
        if zone is None:
            if rows:
                raise ValueError('Missing cost units')
            return {**{k: value[k] for k in ('workspace_id','campaign_id','start_date','end_date','as_of','currency')},
                    'reporting_timezone': None, 'status': 'unavailable', 'reason_codes': ['COST_REPORTING_TIMEZONE_UNKNOWN'],
                    'total_cost_minor': None, 'observed_cost_minor': None, 'cost_per_lead_minor': None,
                    'qualified_cost_per_lead_minor': None, 'denominator_status': 'NOT_RECONCILED',
                    'days': [], 'execution_authorized': False}
        result = campaign_cost_coverage(workspace_id=str(workspace_id), campaign_id=str(campaign_id),
            start_date=start_date.isoformat(), end_date=end_date.isoformat(), reporting_timezone=zone,
            currency='USD', as_of=cutoff.isoformat(), records=rows)
        authority = {row['id']: row for row in rows}
        for day in result['days']:
            row = authority.get(day['revision_id'])
            day['attribution_current'] = row['attribution_current'] if row else None
            day['link_review_id'] = row['link_review_id'] if row else None
        result['evidence_basis'] = 'reviewed_import'
        result['attribution_checked_at'] = datetime.now(timezone.utc).isoformat()
        if any(not row['attribution_current'] for row in rows):
            result.update(status='requires_review', total_cost_minor=None, observed_cost_minor=None)
            result['reason_codes'] = sorted(set(result['reason_codes'] + ['COST_ATTRIBUTION_NOT_CURRENT']))
        return result
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise HTTPException(status_code=502, detail='Cost evidence could not be verified') from None


class AcquisitionCostData(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$', min_length=10, max_length=10, strict=True)
    amount_minor: int | None = Field(ge=0, le=100_000_000_000_000, strict=True)
    coverage: Literal['complete', 'partial', 'withdrawn']
    currency: Literal['USD']
    reporting_timezone: str = Field(min_length=1, max_length=100, strict=True)
    observed_at: AwareDatetime
    external_campaign_id: str = Field(pattern=r'^[0-9]{1,200}$', strict=True)
    ad_account_id: str = Field(pattern=r'^[0-9]{1,200}$', strict=True)
    evidence_ref: str = Field(min_length=10, max_length=1000, strict=True)
    evidence_hash: str = Field(pattern=r'^[a-f0-9]{64}$', strict=True)
    expected_revision: int = Field(ge=0, le=999_999_999, strict=True)

    @field_validator('observed_at', mode='before')
    @classmethod
    def explicit_observation_timestamp(cls, value):
        if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})', value):
            raise ValueError('Use an explicit timestamp with timezone')
        return value

    @model_validator(mode='after')
    def consistent_daily_evidence(self):
        day = date.fromisoformat(self.date)
        try:
            zone = ZoneInfo(self.reporting_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Use a supported account reporting timezone') from None
        if len(self.evidence_ref.strip()) < 10:
            raise ValueError('Reviewed evidence reference required')
        if self.observed_at > datetime.now(timezone.utc):
            raise ValueError('Observation cannot be in the future')
        if (self.coverage == 'withdrawn') != (self.amount_minor is None):
            raise ValueError('Withdrawn cost requires null; other coverage requires exact minor units')
        if self.coverage == 'complete' and self.observed_at.astimezone(zone).date() <= day:
            raise ValueError('Complete cost requires a closed local reporting day')
        return self


class AcquisitionCostImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    link_review_id: UUID
    reviewed: bool = Field(strict=True)
    data: AcquisitionCostData

    @model_validator(mode='after')
    def evidence_review_required(self):
        if not self.reviewed:
            raise ValueError('Confirm review of the source evidence')
        return self


@router.post('/workspaces/{workspace_id}/cost-evidence')
async def record_acquisition_cost(workspace_id: UUID, body: AcquisitionCostImport, store=Depends(acquisition_store)):
    try:
        result = await store.request('POST', 'rpc/record_acquisition_cost', body={
            'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_link_review': str(body.link_review_id),
            'p_data': body.data.model_dump(mode='json')})
    except HTTPException as exc:
        # This single transactional RPC has no provider side effects. These
        # mapped PostgREST errors confirm this invocation was rejected. They do
        # not prove that an earlier invocation of the same UUID did not commit.
        if exc.status_code in {401, 403, 409}:
            raise HTTPException(exc.status_code, exc.detail,
                                headers={'X-Acquisition-Cost-Rejected': 'true'}) from None
        raise
    try:
        if (not isinstance(result, dict) or result.get('id') != str(body.id)
            or type(result.get('revision')) is not int or result['revision'] != body.data.expected_revision + 1
            or type(result.get('duplicate')) is not bool or result.get('execution_authorized') is not False
            or str(UUID(result['campaign_id'])) != result['campaign_id']):
            raise ValueError('Unconfirmed cost result')
    except (ValueError, TypeError, KeyError, AttributeError):
        # A malformed reply may follow a committed write. Do not retry or invent
        # another request; callers retain the original UUID/body to reconcile.
        raise HTTPException(status_code=502, detail='Cost import result is unconfirmed; reconcile the exact request') from None
    return {key: result[key] for key in ('id','campaign_id','revision','duplicate','execution_authorized')}


@router.get('/workspaces/{workspace_id}/inbound/integrations/{integration_id}/calls/{call_id}/requests')
async def inbound_call_requests(workspace_id: UUID, integration_id: UUID, call_id: str,
                                after: UUID | None = None,
                                limit: int = Query(default=20, ge=1, le=50),
                                store=Depends(acquisition_store)):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', call_id):
        raise HTTPException(status_code=422, detail='Invalid call identifier')
    return await store.request('POST', 'rpc/acquisition_inbound_requests', body={
        'p_workspace': str(workspace_id), 'p_integration': str(integration_id),
        'p_call': call_id, 'p_after': str(after) if after else None, 'p_limit': limit,
    })


@router.get('/workspaces/{workspace_id}/inbound/requests')
async def inbound_request_queue(workspace_id: UUID, after: UUID | None = None,
                                limit: int = Query(default=20, ge=1, le=50),
                                status: Literal['all','open','pending_review','assigned','on_hold','review_complete','requires_review','unassigned','withdrawn'] = 'all',
                                assignment: Literal['all','mine','unassigned'] = 'all',
                                store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_inbound_request_queue_v2', body={
        'p_workspace': str(workspace_id), 'p_after': str(after) if after else None, 'p_limit': limit,
        'p_status': status, 'p_assignment': assignment,
    })


class InboundRequestReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_sequence: int = Field(ge=0, le=999999999)
    request_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['unassigned','assigned','on_hold','review_complete']
    assigned_user_id: UUID | None
    review_note: str = Field(min_length=20, max_length=2000)

    @model_validator(mode='after')
    def assignment_shape(self):
        if (self.status == 'unassigned') != (self.assigned_user_id is None):
            raise ValueError('Assignment must match review status')
        return self


@router.get('/workspaces/{workspace_id}/inbound/requests/{task_id}/state')
async def inbound_request_review_state(workspace_id: UUID, task_id: UUID, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/acquisition_inbound_request_state', body={
        'p_workspace': str(workspace_id), 'p_task': str(task_id),
    })


@router.post('/workspaces/{workspace_id}/inbound/requests/{task_id}/reviews')
async def record_inbound_request_review(workspace_id: UUID, task_id: UUID, body: InboundRequestReview, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/review_acquisition_inbound_request', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_task': str(task_id),
        'p_expected_sequence': body.expected_sequence, 'p_request_hash': body.request_hash,
        'p_status': body.status, 'p_assignee': str(body.assigned_user_id) if body.assigned_user_id else None,
        'p_note': body.review_note,
    })


@router.get('/workspaces/{workspace_id}/inbound/requests/{task_id}/reviews')
async def inbound_request_review_history(workspace_id: UUID, task_id: UUID,
                                        before: int | None = Query(default=None, ge=1),
                                        limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    params = {'select': '*', 'workspace_id': 'eq.'+str(workspace_id), 'task_id': 'eq.'+str(task_id),
              'order': 'sequence.desc', 'limit': str(limit)}
    if before is not None:
        params['sequence'] = 'lt.'+str(before)
    return await store.request('GET', 'acquisition_inbound_request_reviews', params=params)
