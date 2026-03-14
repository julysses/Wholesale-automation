"""
Web interface for the TX Wholesale Agency.

Run from the project root:
    uvicorn web.app:app --reload --port 8000
    then open http://localhost:8000
"""

from __future__ import annotations

import csv
import io
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# ── Ensure project root is importable ─────────────────────────────────────────
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator import MasterOrchestrator          # noqa: E402
from schemas.compliance import AuditLogEntry         # noqa: E402
from schemas.property import DataSource              # noqa: E402
from tools.crm import CRMStore                       # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(title="TX Wholesale Agency", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# ── Shared CRM singleton ───────────────────────────────────────────────────────
_crm: Optional[CRMStore] = None


def get_crm() -> CRMStore:
    global _crm
    if _crm is None:
        _crm = CRMStore()
    return _crm


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Health-check endpoint for Railway / load-balancer probes."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    crm = get_crm()
    leads   = crm.get_all_leads()
    deals   = crm.get_active_deals()
    buyers  = crm.get_active_buyers()
    audit   = crm.get_audit_log(limit=8)
    return templates.TemplateResponse("dashboard.html", {
        "request":     request,
        "active":      "dashboard",
        "lead_count":  len(leads),
        "deal_count":  len(deals),
        "buyer_count": len(buyers),
        "recent_audit": audit,
    })


# ── Leads ─────────────────────────────────────────────────────────────────────

@app.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request) -> HTMLResponse:
    crm = get_crm()
    leads = crm.get_all_leads()
    return templates.TemplateResponse("leads.html", {
        "request": request,
        "active":  "leads",
        "leads":   leads,
    })


@app.post("/leads/ingest", response_class=HTMLResponse)
def ingest_leads(
    request: Request,
    file:   UploadFile = File(...),
    source: str        = Form("manual"),
) -> HTMLResponse:
    crm = get_crm()
    message: Optional[str] = None
    error:   Optional[str] = None
    ingested = 0

    try:
        content = file.file.read().decode("utf-8")
        reader  = csv.DictReader(io.StringIO(content))
        records = list(reader)
        if not records:
            error = "CSV file is empty or has no data rows."
        else:
            orch        = MasterOrchestrator()
            source_enum = _source_enum(source)
            leads_out   = orch.ingest_leads(records, source_enum)
            for lead in leads_out:
                crm.save_lead(lead)
            ingested = len(leads_out)
            message  = f"Ingested {ingested} lead(s) from {file.filename}"
    except Exception as exc:
        logger.exception("Ingest failed")
        error = str(exc)

    return templates.TemplateResponse("leads.html", {
        "request": request,
        "active":  "leads",
        "leads":   crm.get_all_leads(),
        "message": message,
        "error":   error,
    })


# ── Pipeline ──────────────────────────────────────────────────────────────────

@app.get("/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("pipeline.html", {
        "request": request,
        "active":  "pipeline",
    })


@app.post("/pipeline/run", response_class=HTMLResponse)
def run_pipeline(
    request: Request,
    file:   UploadFile = File(...),
    source: str        = Form("manual"),
) -> HTMLResponse:
    crm = get_crm()
    state = None
    error: Optional[str] = None

    try:
        content = file.file.read().decode("utf-8")
        reader  = csv.DictReader(io.StringIO(content))
        records = list(reader)
        if not records:
            error = "CSV file is empty."
        else:
            orch        = MasterOrchestrator()
            source_enum = _source_enum(source)
            state       = orch.run_full_pipeline(records, source_enum)

            for lead in state.raw_leads:
                crm.save_lead(lead)
            for deal in state.active_deals:
                crm.save_deal(deal)
            for entry in orch.export_audit_log():
                crm.save_audit_entry(AuditLogEntry(**entry))
    except Exception as exc:
        logger.exception("Pipeline run failed")
        error = str(exc)

    return templates.TemplateResponse("pipeline.html", {
        "request":      request,
        "active":       "pipeline",
        "state":        state,
        "error":        error,
        "fmt_currency": _fmt_currency,
        "truncate":     _truncate,
    })


# ── Deals ─────────────────────────────────────────────────────────────────────

@app.get("/deals", response_class=HTMLResponse)
def deals_page(request: Request) -> HTMLResponse:
    crm   = get_crm()
    deals = crm.get_active_deals()
    return templates.TemplateResponse("deals.html", {
        "request":      request,
        "active":       "deals",
        "deals":        deals,
        "fmt_currency": _fmt_currency,
    })


# ── Buyers ────────────────────────────────────────────────────────────────────

@app.get("/buyers", response_class=HTMLResponse)
def buyers_page(request: Request) -> HTMLResponse:
    crm    = get_crm()
    buyers = crm.get_active_buyers()
    return templates.TemplateResponse("buyers.html", {
        "request": request,
        "active":  "buyers",
        "buyers":  buyers,
    })


# ── Audit Log ─────────────────────────────────────────────────────────────────

@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, agent: str = "") -> HTMLResponse:
    crm     = get_crm()
    entries = crm.get_audit_log(agent=agent or None, limit=200)
    return templates.TemplateResponse("audit.html", {
        "request":      request,
        "active":       "audit",
        "entries":      entries,
        "agent_filter": agent,
    })
