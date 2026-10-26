"""Acquisition workspace administration; unavailable until explicitly enabled."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
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
