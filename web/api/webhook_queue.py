"""
Durable webhook queue for serverless (Vercel) hosting.

On a persistent server, inbound webhooks return 200 and finish their work in a
FastAPI BackgroundTask. On Vercel the function is frozen the moment the response
is sent, so background tasks — and the fire-and-forget ``asyncio.create_task``
used for HOT-lead automation — never complete.

This module decouples acceptance from processing:

  * ``enqueue(source, payload)`` — called from each webhook route after
    signature verification. Inserts the raw provider payload into the
    ``webhook_jobs`` table and returns immediately. The route returns 200.

  * ``drain(limit)`` — called by ``POST /webhooks/_worker/drain`` (a Vercel
    Cron target). Pulls pending rows, replays each through the matching
    processor in ``web.api.webhooks`` (which re-parses the raw payload and
    awaits the real handler), and marks the row done/failed.

HOT-lead automation: handlers schedule that work via
``_schedule_hot_lead_automation``. On a server it stays fire-and-forget; inside
the worker it must be awaited or it dies with the function. ``PENDING_AUTOMATIONS``
is a ContextVar the worker sets to a list before running a job; the scheduler
appends coroutines to it instead of detaching them, and the worker awaits them
before marking the job done.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

WEBHOOK_JOBS_TABLE = "webhook_jobs"

# Max delivery attempts before a job is parked as 'failed'.
MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "5"))

# Set by drain() per job so _schedule_hot_lead_automation appends awaitable
# coroutines here instead of detaching them with asyncio.create_task.
PENDING_AUTOMATIONS: ContextVar[Optional[list]] = ContextVar(
    "webhook_pending_automations", default=None
)


def _get_supabase() -> Optional[Any]:
    """Return a service-role Supabase client, or None if not configured."""
    # Imported lazily from webhooks to reuse the exact same resolution logic.
    from web.api.webhooks import _get_supabase as _sb  # local import avoids cycle
    return _sb()


def enqueue(source: str, payload: dict) -> bool:
    """
    Persist a webhook for later processing. Returns True if stored.

    Never raises: a queue failure must not turn the webhook 200 into a 500 (the
    provider would just retry). Failures are logged; the row is simply not
    stored (matching the pre-queue behaviour where a missing Supabase client
    made the background handler a no-op).
    """
    sb = _get_supabase()
    if sb is None:
        logger.error(
            "[webhook-queue] Supabase not configured — dropping %s job (work will "
            "not be processed)", source,
        )
        return False
    try:
        sb.table(WEBHOOK_JOBS_TABLE).insert({
            "source":  source,
            "payload": payload,
            "status":  "pending",
        }).execute()
        logger.info("[webhook-queue] enqueued source=%s", source)
        return True
    except Exception as exc:  # noqa: BLE001 — must not break the 200 response
        logger.error("[webhook-queue] enqueue failed source=%s: %s", source, exc)
        return False


async def _run_job(processor: Callable[[dict], Awaitable[None]], payload: dict) -> None:
    """Run one processor and await any HOT-lead automations it scheduled."""
    pending: list = []
    token = PENDING_AUTOMATIONS.set(pending)
    try:
        await processor(payload)
        if pending:
            await asyncio.gather(*pending)
    finally:
        PENDING_AUTOMATIONS.reset(token)


async def drain(limit: int = 10) -> dict:
    """
    Process up to ``limit`` pending webhook jobs. Returns a summary dict.

    Each job is claimed (status -> processing), replayed through its processor,
    then marked done or failed. A job that errors is retried on later drains
    until MAX_ATTEMPTS, after which it is parked as 'failed'.
    """
    sb = _get_supabase()
    if sb is None:
        return {"status": "skipped", "reason": "supabase_not_configured", "processed": 0}

    # Late import keeps this module free of a hard dependency on webhooks at
    # import time (webhooks imports enqueue/PENDING_AUTOMATIONS from here).
    from web.api.webhooks import get_webhook_processors
    processors = get_webhook_processors()

    try:
        resp = (
            sb.table(WEBHOOK_JOBS_TABLE)
            .select("*")
            .eq("status", "pending")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        jobs = resp.data or []
    except Exception as exc:  # noqa: BLE001
        logger.error("[webhook-queue] failed to fetch pending jobs: %s", exc)
        return {"status": "error", "reason": str(exc), "processed": 0}

    done = 0
    failed = 0
    for job in jobs:
        job_id = job["id"]
        source = job.get("source", "")
        attempts = (job.get("attempts") or 0) + 1
        processor = processors.get(source)

        # Claim the job so a concurrent drain doesn't double-process it.
        try:
            claimed = sb.table(WEBHOOK_JOBS_TABLE).update(
                {"status": "processing", "attempts": attempts}
            ).eq("id", job_id).eq("status", "pending").execute()
            if not claimed.data:
                continue  # Another worker already owns this job.
        except Exception as exc:  # noqa: BLE001
            logger.error("[webhook-queue] failed to claim job %s: %s", job_id, exc)
            continue

        if processor is None:
            logger.error("[webhook-queue] no processor for source=%s job=%s", source, job_id)
            sb.table(WEBHOOK_JOBS_TABLE).update(
                {"status": "failed", "last_error": f"no processor for source '{source}'"}
            ).eq("id", job_id).execute()
            failed += 1
            continue

        try:
            await _run_job(processor, job.get("payload") or {})
            sb.table(WEBHOOK_JOBS_TABLE).update({
                "status": "done",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).execute()
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("[webhook-queue] job %s (source=%s) failed", job_id, source)
            parked = attempts >= MAX_ATTEMPTS
            sb.table(WEBHOOK_JOBS_TABLE).update({
                "status": "failed" if parked else "pending",
                "last_error": str(exc)[:2000],
            }).eq("id", job_id).execute()
            failed += 1

    return {"status": "ok", "processed": done, "failed": failed, "fetched": len(jobs)}
