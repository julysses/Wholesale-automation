"""
TX Wholesale Agency — FastAPI application.

Development (two terminals):
    uvicorn web.app:app --reload --port 8000   # Python backend
    cd frontend && npm run dev                  # React dev server → proxies /api to :8000

Production (single process):
    cd frontend && npm run build               # outputs to frontend/dist/
    uvicorn web.app:app --host 0.0.0.0 --port 8000
    # or: docker compose up

Environment variables (see .env.example):
    ANTHROPIC_API_KEY, DATABASE_URL, CORS_ORIGINS,
    VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY  ← used by /api/config
"""

from __future__ import annotations

import csv
import io
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator import MasterOrchestrator       # noqa: E402
from schemas.compliance import AuditLogEntry      # noqa: E402
from schemas.property import DataSource           # noqa: E402
from tools.crm import CRMStore                    # noqa: E402
from web.api import router as ai_router           # noqa: E402

logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="WholesaleOS — TX Wholesale Agency",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:8000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── AI endpoints (used by React/WholesaleOS) ───────────────────────────────────
app.include_router(ai_router)  # POST /api/ai/*

# ── Jinja2 templates (legacy pipeline UI at /v1/*) ────────────────────────────
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# ── CRM singleton ──────────────────────────────────────────────────────────────
_crm: Optional[CRMStore] = None


def get_crm() -> CRMStore:
    global _crm
    if _crm is None:
        _crm = CRMStore()
    return _crm


# ── Helpers ────────────────────────────────────────────────────────────────────
def _source_enum(source: str) -> DataSource:
    return {
        "tax_delinquent_csv": DataSource.TAX_DELINQUENT,
        "tax_delinquent":     DataSource.TAX_DELINQUENT,
        "probate_csv":        DataSource.PROBATE,
        "probate":            DataSource.PROBATE,
        "propstream":         DataSource.PROPSTREAM,
        "batchleads":         DataSource.BATCHLEADS,
    }.get(source, DataSource.MANUAL)


def _fmt_currency(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v else "—"


def _truncate(s: str, n: int = 35) -> str:
    return (s[:n] + "…") if s and len(s) > n else (s or "")


# ── System API ─────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
def health_check() -> dict:
    """Health-check for load-balancers, Docker HEALTHCHECK, and Railway/Render probes."""
    return {"status": "ok", "service": "wholesaleos"}


@app.get("/api/config", tags=["system"])
def frontend_config() -> dict:
    """
    Serves Supabase connection config to the React app at runtime.
    Eliminates the need to bake VITE_ vars into the frontend build image.
    """
    return {
        "supabase_url":      os.getenv("VITE_SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("VITE_SUPABASE_ANON_KEY", ""),
    }


# ── Legacy pipeline UI (Jinja2 at /v1/*) ──────────────────────────────────────
# The React/WholesaleOS frontend is the primary UI (served at /).
# These routes provide direct pipeline access without a frontend build.

@app.get("/v1", response_class=HTMLResponse)
@app.get("/v1/", response_class=HTMLResponse)
def v1_dashboard(request: Request) -> HTMLResponse:
    crm = get_crm()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "active": "dashboard",
        "lead_count":   len(crm.get_all_leads()),
        "deal_count":   len(crm.get_active_deals()),
        "buyer_count":  len(crm.get_active_buyers()),
        "recent_audit": crm.get_audit_log(limit=8),
    })


@app.get("/v1/leads", response_class=HTMLResponse)
def v1_leads(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("leads.html", {
        "request": request, "active": "leads", "leads": get_crm().get_all_leads(),
    })


@app.post("/v1/leads/ingest", response_class=HTMLResponse)
def v1_ingest_leads(
    request: Request,
    file:   UploadFile = File(...),
    source: str        = Form("manual"),
) -> HTMLResponse:
    crm = get_crm()
    message: Optional[str] = None
    error:   Optional[str] = None
    try:
        records = list(csv.DictReader(io.StringIO(file.file.read().decode("utf-8"))))
        if not records:
            error = "CSV file is empty or has no data rows."
        else:
            leads_out = MasterOrchestrator().ingest_leads(records, _source_enum(source))
            for lead in leads_out:
                crm.save_lead(lead)
            message = f"Ingested {len(leads_out)} lead(s) from {file.filename}"
    except Exception as exc:
        logger.exception("Ingest failed")
        error = str(exc)
    return templates.TemplateResponse("leads.html", {
        "request": request, "active": "leads",
        "leads": crm.get_all_leads(), "message": message, "error": error,
    })


@app.get("/v1/pipeline", response_class=HTMLResponse)
def v1_pipeline(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("pipeline.html", {"request": request, "active": "pipeline"})


@app.post("/v1/pipeline/run", response_class=HTMLResponse)
def v1_run_pipeline(
    request: Request,
    file:   UploadFile = File(...),
    source: str        = Form("manual"),
) -> HTMLResponse:
    crm = get_crm()
    state = None
    error: Optional[str] = None
    try:
        records = list(csv.DictReader(io.StringIO(file.file.read().decode("utf-8"))))
        if not records:
            error = "CSV file is empty."
        else:
            orch  = MasterOrchestrator()
            state = orch.run_full_pipeline(records, _source_enum(source))
            for lead in state.raw_leads:   crm.save_lead(lead)
            for deal in state.active_deals: crm.save_deal(deal)
            for entry in orch.export_audit_log():
                crm.save_audit_entry(AuditLogEntry(**entry))
    except Exception as exc:
        logger.exception("Pipeline run failed")
        error = str(exc)
    return templates.TemplateResponse("pipeline.html", {
        "request": request, "active": "pipeline",
        "state": state, "error": error,
        "fmt_currency": _fmt_currency, "truncate": _truncate,
    })


@app.get("/v1/deals", response_class=HTMLResponse)
def v1_deals(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("deals.html", {
        "request": request, "active": "deals",
        "deals": get_crm().get_active_deals(), "fmt_currency": _fmt_currency,
    })


@app.get("/v1/buyers", response_class=HTMLResponse)
def v1_buyers(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("buyers.html", {
        "request": request, "active": "buyers", "buyers": get_crm().get_active_buyers(),
    })


@app.get("/v1/audit", response_class=HTMLResponse)
def v1_audit(request: Request, agent: str = "") -> HTMLResponse:
    return templates.TemplateResponse("audit.html", {
        "request": request, "active": "audit",
        "entries": get_crm().get_audit_log(agent=agent or None, limit=200),
        "agent_filter": agent,
    })


# ── Serve React frontend (WholesaleOS) ────────────────────────────────────────
# MUST be registered last — acts as catch-all for all unmatched paths.
# html=True means any unknown path returns index.html, letting React Router
# handle client-side navigation (/leads, /pipeline, /buyers, etc.).
_frontend_dist = ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="wholesaleos")
    logger.info(f"[WholesaleOS] Serving React build from {_frontend_dist}")
else:
    logger.info("[WholesaleOS] No React build. Run:  cd frontend && npm install && npm run build")
