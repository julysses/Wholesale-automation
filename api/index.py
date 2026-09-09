"""
Vercel Python serverless entry point.

Vercel's @vercel/python runtime statically scans this module for a top-level
``app`` / ``application`` / ``handler`` name and serves it as an ASGI app. All
``/api/*`` and ``/webhooks/*`` requests are routed here via ``vercel.json``; the
FastAPI app sees the original request path, so the existing routers (mounted at
``/api/...`` and ``/webhooks/...``) work unchanged.

The React SPA is served by Vercel as static files from ``frontend/dist`` — NOT
by this function — so the StaticFiles catch-all in ``web/app.py`` stays inert
here (its ``frontend/dist`` guard is False in the serverless bundle).

Async/long-running work (webhook follow-ups) runs inline within the request on
this plan; see ``web/api/webhooks.py`` (``_process_inline``). A durable
``webhook_jobs`` queue + ``/_worker/drain`` endpoint remain in the codebase for a
future Pro-plan/pg_cron drain, but are off the request hot path.

If importing the real app raises during cold start, ``_load_app`` logs the full
exception server-side and returns a minimal service-unavailable app. Responses
never expose startup diagnostics, which may contain configuration credentials.

IMPORTANT: ``app`` must be assigned at module top level (``app = _load_app()``).
The @vercel/python builder finds the entrypoint by statically scanning for a
top-level ``app`` name; binding it only inside a ``try``/``except`` makes the
builder fail with "Could not find a top-level app".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the repo root is importable when Vercel invokes this file from api/.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_app():
    """Return the real FastAPI app, or a generic fallback on startup failure."""
    try:
        from web.app import app as real_app
        return real_app
    except Exception:  # noqa: BLE001 — keep diagnostics in server logs
        logging.getLogger(__name__).exception("Backend import failed during cold start")

        from fastapi import FastAPI
        from fastapi.responses import PlainTextResponse

        fallback = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @fallback.api_route(
            "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        )
        def _boot_error(path: str) -> PlainTextResponse:
            return PlainTextResponse(
                "Service temporarily unavailable. Please try again later.",
                status_code=503,
            )

        return fallback


app = _load_app()  # top-level binding — statically visible to @vercel/python

__all__ = ["app"]
