"""Public availability probe and protected operational escalation controls."""
import hmac
import os
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from tools import launch_monitor

router = APIRouter(tags=["Launch monitoring"])


@router.get("/api/readiness")
async def readiness():
    # Public probe reveals only dependency availability, never backlog or lead data.
    try:
        state = await run_in_threadpool(launch_monitor.snapshot)
        ready = all(state.get(key) is True for key in ("database", "intake", "owner"))
    except Exception:
        ready = False
    return JSONResponse({"status": "ok" if ready else "unavailable"}, status_code=200 if ready else 503,
        headers={"Cache-Control":"no-store"})


@router.get("/api/operations/monitor")
async def monitor():
    try:
        state = await run_in_threadpool(launch_monitor.snapshot)
        items = await run_in_threadpool(launch_monitor.incidents)
        return {"snapshot":state,"incidents":items}
    except Exception:
        raise HTTPException(503, "Monitoring database is unavailable. Check the independent availability monitor.")


@router.post("/api/operations/monitor/scan")
async def scan():
    try:
        return await run_in_threadpool(launch_monitor.scan)
    except Exception:
        raise HTTPException(503, "Escalation outcome is unconfirmed. Refresh incidents; no seller outreach was attempted.")


@router.get("/webhooks/_worker/launch-monitor")
async def worker(authorization: str = Header(default="")):
    secret = os.getenv("CRON_SECRET", "")
    if not secret:
        raise HTTPException(503, "Monitoring worker secret is not configured")
    if not hmac.compare_digest(authorization, f"Bearer {secret}"):
        raise HTTPException(401, "Unauthorized")
    return await scan()
