"""
Vercel Python serverless entry point.

Vercel's @vercel/python runtime auto-detects the module-level ASGI ``app`` and
serves it. All ``/api/*`` and ``/webhooks/*`` requests are routed here via the
rewrites in ``vercel.json``; the FastAPI app sees the original request path, so
the existing routers (mounted at ``/api/...`` and ``/webhooks/...``) work
unchanged.

The React SPA is served by Vercel as static files from ``frontend/dist`` — NOT
by this function — so the StaticFiles catch-all in ``web/app.py`` stays inert
here (its ``frontend/dist`` guard is False in the serverless bundle).

Async/long-running work (webhook follow-ups) is NOT run inside the request via
FastAPI BackgroundTasks on Vercel — the function is frozen once the response is
returned. Instead webhooks enqueue a row into the ``webhook_jobs`` table and a
Vercel Cron hits ``/webhooks/_worker/drain`` once a minute to process the queue.
See ``web/api/webhook_queue.py``.

Self-diagnosing: if importing the real app raises during cold start (the usual
cause of an opaque ``FUNCTION_INVOCATION_FAILED``), we expose a minimal fallback
app that returns the traceback as a readable 500 instead of crashing the
function — so the error is visible in the browser without log access.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Ensure the repo root is importable when Vercel invokes this file from api/.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from web.app import app  # noqa: E402  (ASGI app picked up by Vercel)
except Exception:  # noqa: BLE001 — surface the import error instead of crashing
    _BOOT_TRACEBACK = traceback.format_exc()

    from fastapi import FastAPI  # noqa: E402
    from fastapi.responses import PlainTextResponse  # noqa: E402

    app = FastAPI()

    @app.get("/api/health")
    def _boot_health() -> PlainTextResponse:
        return PlainTextResponse(
            "backend import failed:\n\n" + _BOOT_TRACEBACK, status_code=500
        )

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def _boot_error(path: str) -> PlainTextResponse:
        return PlainTextResponse(
            "backend import failed during cold start:\n\n" + _BOOT_TRACEBACK,
            status_code=500,
        )

__all__ = ["app"]
