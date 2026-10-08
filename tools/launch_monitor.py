"""Bounded server-only launch monitoring. Never dispatch seller outreach."""
import os
import httpx


def _request(path: str, *, params=None, rpc=False):
    base = (os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")).rstrip("/")
    secret = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base.startswith("https://") or not secret:
        raise RuntimeError("Monitoring database is not configured")
    # No SDK default 120-second timeout and no transport retry after a write.
    with httpx.Client(timeout=5) as client:
        response = client.request("POST" if rpc else "GET", f"{base}/rest/v1/{path}",
            headers={"apikey": secret, "Authorization": f"Bearer {secret}"},
            params=params, json={} if rpc else None)
        response.raise_for_status()
        return response.json()


def snapshot() -> dict:
    value = _request("rpc/launch_monitor_snapshot", rpc=True)
    if not isinstance(value, dict) or any(type(value.get(key)) is not bool for key in ("database", "intake", "owner")):
        raise RuntimeError("Readiness acknowledgement is invalid")
    if not isinstance(value.get("aged"), dict) or any(type(count) is not int or count < 0 for count in value["aged"].values()):
        raise RuntimeError("Backlog acknowledgement is invalid")
    return value


def scan() -> dict:
    result = _request("rpc/scan_launch_monitor", rpc=True)
    if not isinstance(result, dict) or not (result.get("busy") is True or type(result.get("created")) is int):
        raise RuntimeError("Escalation acknowledgement is unavailable")
    return result


def incidents() -> list:
    result = _request("launch_monitor_incidents", params={"select":"id,category,reference,lead_id,first_seen", "resolved_at":"is.null", "order":"first_seen.asc", "limit":"50"})
    if not isinstance(result, list):
        raise RuntimeError("Incident acknowledgement is unavailable")
    return result
