"""Server-owned inbox acceptance only; no legacy queue or provider processing."""
import os
from uuid import UUID
from urllib.parse import urlsplit

import httpx


class InboxUnavailable(RuntimeError):
    pass


def ingestion_enabled():
    return (os.getenv('ACQUISITION_ENABLED', '').lower() == 'true'
            and os.getenv('FACEBOOK_ACQUISITION_INGESTION_ENABLED', '').lower() == 'true')


async def accept_facebook_events(events, raw_body):
    """Return only after every event has a confirmed durable receipt.

    One database transaction accepts the batch. On an unknown response the
    provider retries; database event identities reconcile existing receipts.
    Never acknowledge unknown durability or fall back to legacy processing.
    """
    if not ingestion_enabled():
        raise InboxUnavailable('Acquisition ingestion disabled')
    key = os.getenv('ACQUISITION_INGESTION_SERVICE_KEY', '').strip()
    url = os.getenv('SUPABASE_URL', '').rstrip('/')
    try:
        parsed = urlsplit(url)
        parsed.port  # Reject malformed port configuration before creating a client.
    except ValueError:
        raise InboxUnavailable('Acquisition ingestion unavailable') from None
    if not key or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise InboxUnavailable('Acquisition ingestion unavailable')
    if not events or len(events) > 100 or not raw_body or len(raw_body) > 1048576:
        raise InboxUnavailable('Invalid ingestion batch')
    accepted = 0
    try:
        async with httpx.AsyncClient(base_url=url + '/rest/v1/', timeout=10.0, follow_redirects=False,
                                    headers={'apikey': key, 'Authorization': 'Bearer ' + key}) as client:
            response = await client.post('rpc/accept_facebook_acquisition_batch', json={
                'p_events': events, 'p_raw_body': '\\x' + raw_body.hex(),
            })
            if response.status_code != 200:
                raise InboxUnavailable('Receipt persistence unconfirmed')
            results = response.json()
            if not isinstance(results, list) or len(results) != len(events):
                raise InboxUnavailable('Receipt persistence unconfirmed')
            for result in results:
                if not isinstance(result, dict) or type(result.get('duplicate')) is not bool or result.get('status') not in ('acquisition_received', 'acquisition_expired'):
                    raise InboxUnavailable('Receipt persistence unconfirmed')
                UUID(result['receipt_id']); UUID(result['workspace_id'])
                accepted += 1
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        raise InboxUnavailable('Receipt persistence unconfirmed') from None
    return accepted
