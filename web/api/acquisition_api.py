"""Acquisition workspace administration; unavailable until explicitly enabled."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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
    params = {'select': 'id,lead_id,classification,created_at', 'workspace_id': 'eq.'+str(workspace_id),
              'order': 'id', 'limit': str(limit+1)}
    if after is not None:
        params['id'] = 'gt.'+str(after)
    rows = await store.request('GET', 'seller_intakes', params=params)
    return {'items': rows[:limit], 'next_after': rows[limit-1]['id'] if len(rows)>limit else None}


@router.get('/workspaces/{workspace_id}/intakes/{intake_id}')
async def acquisition_intake_detail(workspace_id: UUID, intake_id: UUID, store=Depends(acquisition_store)):
    rows = await store.request('GET', 'seller_intakes', params={
        'select': 'id,lead_id,classification,created_at,prepared_answers,preparation_hash,normalization_notes',
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
