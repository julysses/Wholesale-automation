"""Admin-only operator-notification acceptance drill."""
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client
from tools.operational_alerts import record_provider_alert

router = APIRouter(prefix='/api/operations', tags=['Operations'])


class AlertDrill(BaseModel):
    request_id: UUID


def test_alert(request_id):
    sb = get_supabase_client()
    if sb is None:
        raise HTTPException(503, 'Notification storage unavailable')
    try:
        notification_id = record_provider_alert(sb, 'test', str(request_id), 'controlled_drill')
        return {'notification_id': notification_id, 'saved': True}
    except Exception:
        raise HTTPException(503, 'Operator alert could not be confirmed')


@router.post('/test-alert')
async def drill(body: AlertDrill):
    return await run_in_threadpool(test_alert, body.request_id)
