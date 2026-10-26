"""Acquisition workspace administration; unavailable until explicitly enabled."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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
