"""Workspace-authorized contact decisions; pending policy never permits outreach."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from tools.acquisition_store import acquisition_store

router = APIRouter(prefix='/internal/outreach/eligibility', tags=['Acquisition'])
Channel = Literal['human_voice', 'ai_voice', 'prerecorded', 'sms', 'email', 'direct_mail']


class EligibilityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace_id: UUID
    lead_id: UUID
    contact_point_id: UUID
    channel: Channel
    purpose: Literal['principal_property_acquisition']
    actor_type: Literal['human', 'ai', 'prerecorded', 'system']
    campaign_id: UUID | None = None


@router.post('/evaluate')
async def evaluate(body: EligibilityRequest, store=Depends(acquisition_store)):
    return await store.request('POST', 'rpc/evaluate_acquisition_eligibility', body={
        'p_workspace': str(body.workspace_id), 'p_lead': str(body.lead_id),
        'p_contact': str(body.contact_point_id), 'p_channel': body.channel,
        'p_purpose': body.purpose, 'p_actor_type': body.actor_type,
        'p_campaign': str(body.campaign_id) if body.campaign_id else None,
    })
