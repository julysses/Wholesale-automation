"""
Buyer Intelligence API — REST endpoints for the IBIE system.

Routes (all under /api/buyers):
  POST /api/buyers/import          CSV upload → parse → upsert buyers + transactions
  POST /api/buyers/score           Re-score one buyer (or all if no buyer_id)
  GET  /api/buyers/leaderboard     Top buyers sorted by ibie_score
  POST /api/buyers/match           Match buyers to a deal (returns ranked list)
  POST /api/buyers/outreach/sms    Send SMS blast to matched buyers
  POST /api/buyers/outreach/email  Send email blast to matched buyers
  GET  /api/buyers/{buyer_id}/transactions   Purchase history for a buyer
  POST /api/buyers/{buyer_id}/classify       Run AI classification for a buyer
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from tools.buyer_intelligence_engine import (
    DealMatchInput,
    build_deal_email,
    build_deal_sms,
    compute_ibie_score,
    assign_ibie_tier,
    compute_tags,
    match_buyers_to_deal,
)
from tools.buyer_csv_parser import parse_buyer_csv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/buyers", tags=["Buyer Intelligence"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    buyer_id: Optional[str] = None   # None = score all buyers


class MatchRequest(BaseModel):
    deal_id: Optional[str] = None
    zip_code: str = ""
    buyer_price: float = 0.0
    property_type: str = ""
    condition: str = ""
    arv: float = 0.0
    city: str = ""
    market: str = ""
    limit: int = 50


class OutreachRequest(BaseModel):
    buyer_ids: list[str]
    deal_id: Optional[str] = None
    property_address: str = ""
    zip_code: str = ""
    price: float = 0.0
    arv: float = 0.0
    assignment_fee: float = 0.0
    property_type: str = "property"
    beds: int = 0
    baths: float = 0.0
    condition: str = ""
    custom_message: str = ""         # overrides template if provided


class ClassifyRequest(BaseModel):
    buyer_id: str


# ── Supabase helper ───────────────────────────────────────────────────────────

def _get_supabase() -> Optional[Any]:
    url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    if not (url and key):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        logger.error(f"[buyers_api] Supabase init failed: {exc}")
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/import")
async def import_buyers_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    market: str = Form(default=""),
    cash_only: bool = Form(default=False),
    entities_only: bool = Form(default=False),
    min_price: float = Form(default=0.0),
    max_price: float = Form(default=0.0),
) -> dict:
    """
    Upload a county deed / PropStream CSV and ingest buyers + transactions.

    Responds immediately with an import_log_id.
    All Supabase writes happen in the background.
    """
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")
    filename = file.filename or "upload.csv"

    sb = _get_supabase()
    log_id = None
    if sb:
        try:
            log_resp = sb.table("buyer_import_log").insert({
                "source":   "county_csv",
                "filename": filename,
                "market":   market,
                "status":   "processing",
            }).execute()
            log_id = (log_resp.data or [{}])[0].get("id")
        except Exception as exc:
            logger.error(f"[buyers_api/import] log insert failed: {exc}")

    background_tasks.add_task(
        _process_import,
        text=text,
        filename=filename,
        market=market,
        cash_only=cash_only,
        entities_only=entities_only,
        min_price=min_price,
        max_price=max_price,
        log_id=log_id,
    )

    return {
        "status": "processing",
        "import_log_id": log_id,
        "message": f"Processing {filename} — check import log for results",
    }


async def _process_import(
    text: str,
    filename: str,
    market: str,
    cash_only: bool,
    entities_only: bool,
    min_price: float,
    max_price: float,
    log_id: Optional[str],
) -> None:
    """Background: parse CSV → upsert buyers + transactions → update log."""
    sb = _get_supabase()

    result = parse_buyer_csv(
        io.StringIO(text),
        market=market,
        cash_only=cash_only,
        entities_only=entities_only,
        min_price=min_price,
        max_price=max_price,
        filename=filename,
    )

    buyers_created = 0
    buyers_updated = 0
    tx_created = 0

    if sb:
        try:
            # Upsert buyers (match on company+email or first+last+phone)
            for buyer in result.buyers:
                try:
                    # Try to find existing buyer by entity_name or name+phone
                    entity = buyer.get("entity_name", "").strip()
                    existing = None
                    if entity:
                        resp = sb.table("buyers").select("id").eq("entity_name", entity).limit(1).execute()
                        existing = (resp.data or [{}])[0].get("id")
                    if not existing:
                        phone = buyer.get("phone", "")
                        if phone:
                            resp = sb.table("buyers").select("id").eq("phone", phone).limit(1).execute()
                            existing = (resp.data or [{}])[0].get("id")

                    if existing:
                        # Update existing buyer with richer data
                        update = {k: v for k, v in buyer.items() if k not in ("id", "created_at")}
                        sb.table("buyers").update(update).eq("id", existing).execute()
                        buyer_db_id = existing
                        buyers_updated += 1
                    else:
                        resp = sb.table("buyers").insert(buyer).execute()
                        buyer_db_id = (resp.data or [{}])[0].get("id")
                        buyers_created += 1

                    # Insert transactions for this buyer
                    if buyer_db_id:
                        for tx in result.transactions:
                            if tx.get("grantee", "").upper() == (buyer.get("entity_name") or f"{buyer['first_name']} {buyer['last_name']}").upper():
                                tx_row = {**tx, "buyer_id": buyer_db_id}
                                tx_row.pop("grantee", None)
                                try:
                                    sb.table("buyer_transactions").upsert(
                                        tx_row,
                                        on_conflict="buyer_id,apn" if tx_row.get("apn") else "id",
                                    ).execute()
                                    tx_created += 1
                                except Exception:
                                    sb.table("buyer_transactions").insert(tx_row).execute()
                                    tx_created += 1

                except Exception as exc:
                    logger.error(f"[buyers_api/import] Buyer upsert failed: {exc}")

            # Update import log
            if log_id:
                sb.table("buyer_import_log").update({
                    "rows_total":         result.log.get("rows_total", 0),
                    "rows_imported":      result.log.get("rows_imported", 0),
                    "buyers_created":     buyers_created,
                    "buyers_updated":     buyers_updated,
                    "transactions_created": tx_created,
                    "rows_skipped":       result.log.get("rows_skipped", 0),
                    "errors":             result.log.get("errors", []),
                    "status":             "complete",
                    "completed_at":       datetime.now(timezone.utc).isoformat(),
                }).eq("id", log_id).execute()

        except Exception as exc:
            logger.error(f"[buyers_api/import] Batch persist failed: {exc}")
            if sb and log_id:
                sb.table("buyer_import_log").update({
                    "status": "failed",
                    "errors": [{"error": str(exc)}],
                }).eq("id", log_id).execute()

    logger.info(
        f"[buyers_api/import] Done — {buyers_created} created, "
        f"{buyers_updated} updated, {tx_created} transactions"
    )


@router.post("/score")
async def score_buyers(req: ScoreRequest, background_tasks: BackgroundTasks) -> dict:
    """
    Re-score one buyer or all buyers (buyer_id=None).
    Returns immediately; scoring happens in background.
    """
    background_tasks.add_task(_run_scoring, req.buyer_id)
    return {
        "status": "scoring_queued",
        "buyer_id": req.buyer_id or "all",
        "message": "Scores will be updated in the background",
    }


async def _run_scoring(buyer_id: Optional[str]) -> None:
    """Background: load buyers + transactions → compute + persist scores."""
    sb = _get_supabase()
    if not sb:
        return

    try:
        if buyer_id:
            buyer_resp = sb.table("buyers").select("*").eq("id", buyer_id).single().execute()
            buyers = [buyer_resp.data] if buyer_resp.data else []
        else:
            buyer_resp = sb.table("buyers").select("*").eq("active", True).execute()
            buyers = buyer_resp.data or []

        if not buyers:
            return

        buyer_ids = [b["id"] for b in buyers]

        # Load all transactions for these buyers
        tx_resp = (
            sb.table("buyer_transactions")
            .select("*")
            .in_("buyer_id", buyer_ids)
            .execute()
        )
        txs_all = tx_resp.data or []

        # Group by buyer_id
        tx_map: dict[str, list] = {bid: [] for bid in buyer_ids}
        for tx in txs_all:
            bid = tx.get("buyer_id")
            if bid in tx_map:
                tx_map[bid].append(tx)

        from tools.buyer_intelligence_engine import batch_score_buyers
        updates = batch_score_buyers(buyers, tx_map)

        for update in updates:
            bid = update.pop("id")
            sb.table("buyers").update(update).eq("id", bid).execute()

        logger.info(f"[buyers_api/score] Scored {len(updates)} buyers")

    except Exception as exc:
        logger.error(f"[buyers_api/score] Scoring failed: {exc}")


@router.get("/leaderboard")
def get_leaderboard(
    limit: int = 100,
    tier: str = "",
    buyer_type: str = "",
    market: str = "",
    cash_only: bool = False,
) -> dict:
    """Return top buyers sorted by ibie_score, with optional filters."""
    sb = _get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")

    try:
        query = sb.table("buyer_leaderboard").select("*")
        if tier:
            query = query.eq("ibie_tier", tier)
        if buyer_type:
            query = query.eq("buyer_type_ibie", buyer_type)
        if market:
            query = query.eq("market", market)
        if cash_only:
            query = query.eq("cash_buyer", True)

        resp = query.order("ibie_score", desc=True).limit(limit).execute()
        buyers = resp.data or []

        return {
            "buyers": buyers,
            "total": len(buyers),
        }
    except Exception as exc:
        raise HTTPException(500, f"Leaderboard query failed: {exc}")


@router.post("/match")
def match_deal_to_buyers(req: MatchRequest) -> dict:
    """
    Match buyers to a deal and return ranked list.
    If deal_id is provided, also persists results to deal_matches table.
    """
    sb = _get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")

    try:
        # Load active buyers
        buyer_resp = sb.table("buyers").select("*").eq("active", True).execute()
        buyers = buyer_resp.data or []

        deal = DealMatchInput(
            deal_id=req.deal_id or "",
            zip_code=req.zip_code,
            buyer_price=req.buyer_price,
            property_type=req.property_type,
            condition=req.condition,
            arv=req.arv,
            city=req.city,
            market=req.market,
        )

        matches = match_buyers_to_deal(deal, buyers, limit=req.limit)

        # Optionally persist to deal_matches
        if req.deal_id and matches:
            try:
                rows = [{
                    "deal_id":     req.deal_id,
                    "buyer_id":    m.buyer_id,
                    "zip_score":   m.zip_score,
                    "price_score": m.price_score,
                    "type_score":  m.type_score,
                    "ibie_score":  m.ibie_score,
                    "match_score": m.match_score,
                    "rank":        m.rank,
                } for m in matches]
                sb.table("deal_matches").upsert(rows, on_conflict="deal_id,buyer_id").execute()
            except Exception as exc:
                logger.warning(f"[buyers_api/match] deal_matches persist failed: {exc}")

        return {
            "total_matches": len(matches),
            "deal_id": req.deal_id,
            "matches": [
                {
                    "rank":          m.rank,
                    "buyer_id":      m.buyer_id,
                    "buyer_name":    m.buyer_name,
                    "company":       m.company,
                    "phone":         m.phone,
                    "email":         m.email,
                    "ibie_score":    m.ibie_score,
                    "match_score":   m.match_score,
                    "zip_score":     m.zip_score,
                    "price_score":   m.price_score,
                    "type_score":    m.type_score,
                    "tags":          m.tags,
                    "match_reasons": m.match_reasons,
                }
                for m in matches
            ],
        }
    except Exception as exc:
        raise HTTPException(500, f"Deal matching failed: {exc}")


@router.post("/outreach/sms")
async def send_sms_blast(req: OutreachRequest, background_tasks: BackgroundTasks) -> dict:
    """Send a deal-blast SMS to the specified buyer IDs."""
    background_tasks.add_task(_send_sms_blast, req)
    return {
        "status": "queued",
        "recipient_count": len(req.buyer_ids),
        "message": "SMS blast queued for delivery",
    }


async def _send_sms_blast(req: OutreachRequest) -> None:
    sb = _get_supabase()
    from tools.sms_client import SMSClient
    sms = SMSClient()

    for buyer_id in req.buyer_ids:
        try:
            if sb:
                buyer_resp = sb.table("buyers").select("first_name,last_name,phone,sms_opt_in").eq("id", buyer_id).single().execute()
                buyer = buyer_resp.data or {}
            else:
                buyer = {}

            phone = buyer.get("phone", "")
            if not phone or not buyer.get("sms_opt_in", True):
                continue

            name = f"{buyer.get('first_name','')} {buyer.get('last_name','')}".strip()
            body = req.custom_message or build_deal_sms(
                buyer_name=name,
                zip_code=req.zip_code,
                price=req.price,
                property_type=req.property_type,
                beds=req.beds,
                baths=req.baths,
            )

            result = sms.send(to=phone, body=body)
            status = "sent" if result else "failed"

            if sb:
                sb.table("buyer_outreach_log").insert({
                    "buyer_id":     buyer_id,
                    "deal_id":      req.deal_id,
                    "channel":      "sms",
                    "status":       status,
                    "body":         body,
                    "to_address":   phone,
                    "provider":     "twilio",
                }).execute()

                # Update ignore count if this is a re-blast (not first contact)
                sb.table("buyers").update({
                    "last_contact_date": datetime.now(timezone.utc).date().isoformat()
                }).eq("id", buyer_id).execute()

        except Exception as exc:
            logger.error(f"[buyers_api/sms] Send to {buyer_id} failed: {exc}")


@router.post("/outreach/email")
async def send_email_blast(req: OutreachRequest, background_tasks: BackgroundTasks) -> dict:
    """Send a deal-blast email to the specified buyer IDs."""
    background_tasks.add_task(_send_email_blast, req)
    return {
        "status": "queued",
        "recipient_count": len(req.buyer_ids),
        "message": "Email blast queued for delivery",
    }


async def _send_email_blast(req: OutreachRequest) -> None:
    sb = _get_supabase()
    from config.settings import settings

    for buyer_id in req.buyer_ids:
        try:
            if sb:
                buyer_resp = sb.table("buyers").select("first_name,last_name,email,email_opt_in").eq("id", buyer_id).single().execute()
                buyer = buyer_resp.data or {}
            else:
                buyer = {}

            email_addr = buyer.get("email", "")
            if not email_addr or not buyer.get("email_opt_in", True):
                continue

            name = f"{buyer.get('first_name','')} {buyer.get('last_name','')}".strip()
            subject, html_body = build_deal_email(
                buyer_name=name,
                property_address=req.property_address,
                zip_code=req.zip_code,
                price=req.price,
                arv=req.arv,
                assignment_fee=req.assignment_fee,
                property_type=req.property_type,
                beds=req.beds,
                baths=req.baths,
                condition=req.condition,
                sender_name=settings.agency_contact_name or "Alex",
                agency_name=settings.agency_name or "Texas Wholesale Solutions",
            )

            status = "sent"
            try:
                import sendgrid
                from sendgrid.helpers.mail import Mail
                sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
                mail = Mail(
                    from_email=settings.from_email,
                    to_emails=email_addr,
                    subject=subject,
                    html_content=html_body,
                )
                sg.send(mail)
            except Exception as exc:
                logger.error(f"[buyers_api/email] SendGrid failed: {exc}")
                status = "failed"

            if sb:
                sb.table("buyer_outreach_log").insert({
                    "buyer_id":   buyer_id,
                    "deal_id":    req.deal_id,
                    "channel":    "email",
                    "status":     status,
                    "subject":    subject,
                    "body":       html_body,
                    "to_address": email_addr,
                    "provider":   "sendgrid",
                }).execute()

        except Exception as exc:
            logger.error(f"[buyers_api/email] Send to {buyer_id} failed: {exc}")


@router.get("/{buyer_id}/transactions")
def get_buyer_transactions(buyer_id: str) -> dict:
    """Return all purchase transactions for a buyer."""
    sb = _get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    try:
        resp = (
            sb.table("buyer_transactions")
            .select("*")
            .eq("buyer_id", buyer_id)
            .order("purchase_date", desc=True)
            .execute()
        )
        return {"transactions": resp.data or [], "buyer_id": buyer_id}
    except Exception as exc:
        raise HTTPException(500, f"Transaction query failed: {exc}")


@router.post("/{buyer_id}/classify")
async def classify_buyer(buyer_id: str, background_tasks: BackgroundTasks) -> dict:
    """Run AI classification for a single buyer."""
    background_tasks.add_task(_run_classify, buyer_id)
    return {
        "status": "classification_queued",
        "buyer_id": buyer_id,
    }


async def _run_classify(buyer_id: str) -> None:
    sb = _get_supabase()
    if not sb:
        return
    try:
        buyer_resp = sb.table("buyers").select("*").eq("id", buyer_id).single().execute()
        buyer = buyer_resp.data
        if not buyer:
            return

        tx_resp = sb.table("buyer_transactions").select("*").eq("buyer_id", buyer_id).execute()
        txs = tx_resp.data or []

        from agents.buyer_intelligence_agent import BuyerIntelligenceAgent
        agent = BuyerIntelligenceAgent()
        result = agent.classify_buyer(buyer, txs)

        from tools.buyer_intelligence_engine import compute_tags
        tags = compute_tags({**buyer, "buyer_type_ibie": result.buyer_type_ibie})
        all_tags = list(set(tags + result.suggested_tags))

        sb.table("buyers").update({
            "buyer_type_ibie":  result.buyer_type_ibie,
            "ai_classified_at": datetime.now(timezone.utc).isoformat(),
            "tags":             all_tags,
        }).eq("id", buyer_id).execute()

        logger.info(f"[buyers_api/classify] {buyer_id} → {result.buyer_type_ibie} ({result.confidence:.2f})")

    except Exception as exc:
        logger.error(f"[buyers_api/classify] Failed for {buyer_id}: {exc}")
