"""Database-only lot routing; live activation requires separate acceptance."""
import os
from uuid import UUID
from tools.crm import get_supabase_client


def process_lot_batch(*, db=None):
    if os.getenv('LIST_LOT_ROUTING_ENABLED', 'false').lower() != 'true':
        return {'status': 'disabled', 'routed': 0}
    try:
        limit = int(os.getenv('LIST_LOT_ROUTING_BATCH_SIZE', '5'))
    except ValueError as exc:
        raise RuntimeError('Invalid lot routing batch size') from exc
    if not 1 <= limit <= 10:
        raise RuntimeError('Lot routing batch size must be between 1 and 10')
    db = db if db is not None else get_supabase_client()
    if db is None:
        raise RuntimeError('Lot routing storage unavailable')
    result = db.rpc('route_list_lots', {'p_limit': limit}).execute().data
    if isinstance(result, dict) and result.get('busy') is True:
        return {'status': 'busy', 'routed': 0}
    if (not isinstance(result, dict) or result.get('outreach_authorized') is not False
            or not isinstance(result.get('outcomes'), list) or len(result['outcomes']) > limit):
        raise RuntimeError('Lot routing outcome unconfirmed; inspect durable handoffs')
    seen = set()
    for row in result['outcomes']:
        if not isinstance(row, dict):
            raise RuntimeError('Invalid lot routing outcome')
        UUID(row['lead_id']); UUID(row['evaluation_id'])
        if row['lead_id'] in seen:
            raise RuntimeError('Duplicate lot routing outcome')
        seen.add(row['lead_id'])
        if row.get('blocked') is None:
            UUID(row['handoff_id'])
        elif not isinstance(row['blocked'], str) or not row['blocked']:
            raise RuntimeError('Invalid lot routing hold')
    monitor = db.rpc('monitor_list_lots', {}).execute().data
    if not isinstance(monitor, dict) or (monitor.get('busy') is not True and
            (type(monitor.get('owner_configured')) is not bool
             or not isinstance(monitor.get('open_incidents'), list)
             or not isinstance(monitor.get('overdue_receipts'), list))):
        raise RuntimeError('Lot routing monitor unconfirmed')
    return {'status': 'processed', 'routed': sum(row.get('blocked') is None for row in result['outcomes']),
            **result, 'monitor': monitor}
