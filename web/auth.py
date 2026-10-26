"""Access checks for the shared, approval-based WholesaleOS workspace."""

import logging

from fastapi import HTTPException, Request

from tools.crm import get_supabase_client
from tools.database_identity import identity

logger = logging.getLogger(__name__)


def require_operator(request: Request) -> None:
    path = request.url.path.rstrip("/")
    route = request.scope.get("route")
    route_path = getattr(route, "path", "")
    if (request.method == "GET" and path in {"/api/health", "/api/readiness", "/api/config"}) or (
        (request.method, route_path) in {
            ("GET", "/api/forms/{form_id}"),
            ("POST", "/api/forms/{form_id}/submit"),
        }
    ):
        return
    # Provider webhooks and the worker enforce their own signatures/secrets.
    if path.startswith("/webhooks/") and path != "/webhooks/launch_control/csv-queue":
        return
    if not (path.startswith("/api/") or path.startswith("/internal/") or path == "/v1" or path.startswith("/v1/")
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
        # '*' permits a code-first rollout before the additive acquisition_only
        # column exists. Only the fields below affect authorization.
        rows = client.table("profiles").select("*").eq("id", str(user.id)).limit(1).execute().data
    except Exception:
        logger.exception("Could not verify operator approval")
        raise HTTPException(503, "Unable to verify account access")
    if not rows or rows[0].get("status") != "approved":
        raise HTTPException(403, "Your account requires administrator approval")
    if identity.get() is not None and (path == '/v1' or path.startswith('/v1/') or path == '/api/leads/rescore'):
        raise HTTPException(409, "This local-CRM workflow requires a workspace-aware replacement")
    if rows[0].get("acquisition_only") is True and not (
        path.startswith('/api/acquisition/') or path == '/internal/outreach/eligibility/evaluate'
    ):
        raise HTTPException(403, "Use your assigned acquisition workspace")
    if (path == "/api/ai/test-key" or path.startswith(("/api/email/", "/api/calls/", "/api/operations/", "/api/nurture/"))) and rows[0].get("role") != "admin":
        raise HTTPException(403, "Administrator access required")
    request.state.user_id = str(user.id)
