"""Access checks for the shared, approval-based WholesaleOS workspace."""

import logging

from fastapi import HTTPException, Request

from tools.crm import get_supabase_client

logger = logging.getLogger(__name__)


def require_operator(request: Request) -> None:
    path = request.url.path.rstrip("/")
    route = request.scope.get("route")
    route_path = getattr(route, "path", "")
    if (request.method == "GET" and path in {"/api/health", "/api/config"}) or (
        (request.method, route_path) in {
            ("GET", "/api/forms/{form_id}"),
            ("POST", "/api/forms/{form_id}/submit"),
        }
    ):
        return
    # Provider webhooks and the worker enforce their own signatures/secrets.
    if path.startswith("/webhooks/") and path != "/webhooks/launch_control/csv-queue":
        return
    if not (path.startswith("/api/") or path == "/v1" or path.startswith("/v1/")
            or path == "/webhooks/launch_control/csv-queue"):
        return

    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    client = get_supabase_client()
    if client is None:
        raise HTTPException(503, "Authentication service is not configured")
    try:
        user = client.auth.get_user(token.strip()).user
    except Exception:
        raise HTTPException(401, "Session is invalid or expired", headers={"WWW-Authenticate": "Bearer"})
    if not user or not user.id:
        raise HTTPException(401, "Session is invalid or expired")
    try:
        rows = client.table("profiles").select("role,status").eq("id", str(user.id)).limit(1).execute().data
    except Exception:
        logger.exception("Could not verify operator approval")
        raise HTTPException(503, "Unable to verify account access")
    if not rows or rows[0].get("status") != "approved":
        raise HTTPException(403, "Your account requires administrator approval")
    if path == "/api/ai/test-key" and rows[0].get("role") != "admin":
        raise HTTPException(403, "Administrator access required")
    request.state.user_id = str(user.id)

