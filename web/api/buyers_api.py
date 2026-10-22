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
import hashlib
import json
import math
from uuid import UUID, uuid5, NAMESPACE_URL
import html
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, Request
from starlette.concurrency import run_in_threadpool
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
    custom_subject: str = ""


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


def _read_all_confirmed(query_factory, label: str) -> list[dict[str, Any]]:
    """Read stable, count-checked pages; never rank or show a capped subset as complete."""
    rows = []
    identities = set()
    expected = None
    offset = 0
    while True:
        response = query_factory().range(offset, offset + 499).execute()
        page = response.data
        count = getattr(response, 'count', None)
        if not isinstance(page, list) or type(count) is not int or count < 0:
            raise ValueError(f'{label} count/result could not be confirmed')
        if expected is not None and count != expected:
            raise ValueError(f'{label} changed while loading')
        expected = count
        for row in page:
            identity = row.get('id') if isinstance(row, dict) else None
            if not isinstance(identity, str) or not identity or identity in identities:
                raise ValueError(f'{label} identities changed while loading')
            identities.add(identity)
        if len(identities) > expected:
            raise ValueError(f'{label} count changed while loading')
        if not page:
            if len(rows) != expected:
                raise ValueError(f'{label} read was incomplete')
            return rows
        rows.extend(page)
        offset += len(page)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/import")
async def import_buyers_csv(
    request: Request,
    file: UploadFile = File(...),
    market: str = Form(default=""),
    cash_only: bool = Form(default=False),
    entities_only: bool = Form(default=False),
    min_price: float = Form(default=0.0),
    max_price: float = Form(default=0.0),
    request_id: Optional[UUID] = Form(default=None),
) -> dict:
    """Parse and atomically save the entire buyer import before acknowledging it."""
    operator = getattr(request.state, 'user_id', None)
    if not operator:
        raise HTTPException(401, 'Sign in to import buyers')
    content = await file.read(4_000_001)
    if len(content) > 4_000_000:
        raise HTTPException(413, 'Buyer CSV exceeds the 4 MB upload limit')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise HTTPException(422, 'Buyer CSV must use UTF-8 text')
    sb = _get_supabase()
    if sb is None:
        raise HTTPException(503, 'Database not configured; no import was started')
    options = {'filename': file.filename or 'upload.csv', 'market': market,
        'cash_only': cash_only, 'entities_only': entities_only,
        'min_price': min_price, 'max_price': max_price}
    if not all(math.isfinite(v) and v >= 0 for v in (min_price,max_price)) or (max_price and min_price > max_price):
        raise HTTPException(422, 'Invalid purchase price range')
    fingerprint = hashlib.sha256(content + json.dumps(options, sort_keys=True).encode()).hexdigest()
    reference = str(request_id or uuid5(NAMESPACE_URL, 'wholesaleos:buyer-csv:'+operator+':'+fingerprint))
    parsed = await run_in_threadpool(parse_buyer_csv, io.StringIO(text), **options)
    # Malformed rows cannot be acknowledged as a complete successful import.
    if parsed.errors or parsed.log.get('errors') or parsed.log.get('status') != 'complete':
        raise HTTPException(422, {'message': 'Fix invalid CSV rows before importing; no records saved',
            'errors': (parsed.errors or parsed.log.get('errors', []))[:20]})
    if parsed.log['rows_total'] > 5000:
        raise HTTPException(413, 'Buyer CSV exceeds 5,000 rows; no records saved')
    options.update(rows_total=parsed.log['rows_total'], rows_skipped=parsed.log['rows_skipped'])
    try:
        value = await run_in_threadpool(lambda: sb.rpc('import_buyer_csv', {
            'p_id': reference, 'p_operator': operator, 'p_fingerprint': fingerprint,
            'p_groups': parsed.groups, 'p_options': options}).execute().data)
    except Exception as exc:
        logger.warning('Buyer CSV result unconfirmed for import %s', reference)
        if (getattr(exc, 'code', None) or getattr(exc, 'pgcode', None)) in {'22023','42501'}:
            raise HTTPException(409, 'Import needs identity/history review or its reference changed. No partial batch was saved.')
        raise HTTPException(503, {'message': 'Import outcome unconfirmed. Retry the same file, options and reference.', 'import_id': reference})
    try:
        result = value['result']
        if (value['import_id'] != reference or value['operator_id'] != operator
            or value['fingerprint'] != fingerprint or value['options'] != options
            or value['outreach_authorized'] is not False or type(value['replayed']) is not bool):
            raise ValueError('Uncorrelated import receipt')
        for key in ['buyers_created','buyers_existing','transactions_created','transactions_existing','rows_total','rows_skipped']:
            if type(result.get(key)) is not int or result[key] < 0: raise ValueError('Unconfirmed totals')
        if (result['buyers_created'] + result['buyers_existing'] != len(parsed.groups)
            or result['transactions_created'] + result['transactions_existing'] != len(parsed.transactions)
            or result['rows_total'] != options['rows_total'] or result['rows_skipped'] != options['rows_skipped']
            or len(result['buyer_ids']) != len(parsed.groups)):
            raise ValueError('Unconfirmed row mapping')
        for identity in result['buyer_ids']:
            if str(UUID(identity)) != identity: raise ValueError('Invalid buyer identity')
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(503, {'message': 'Import receipt unconfirmed. Retry the original file and reference.', 'import_id': reference})
    return {'status': 'complete', 'import_id': reference, 'import_log_id': reference,
        'replayed': value['replayed'], 'outreach_authorized': False, **result}


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


SCORE_PAGE = 1000
IN_CHUNK = 200


async def _run_scoring(buyer_id: Optional[str], buyer_ids: Optional[list[str]] = None) -> None:
    """Background: load buyers + transactions → compute + persist scores.

    Pages through buyers (PostgREST caps a response at ~1000 rows) and chunks the
    transaction ``in`` filter so large books don't silently truncate or overflow
    the request URL.
    """
    sb = _get_supabase()
    if not sb:
        return

    try:
        buyers: list[dict[str, Any]] = []
        if buyer_id:
            buyer_resp = sb.table("buyers").select("*").eq("id", buyer_id).single().execute()
            buyers = [buyer_resp.data] if buyer_resp.data else []
        elif buyer_ids:
            for i in range(0, len(buyer_ids), IN_CHUNK):
                resp = sb.table("buyers").select("*").in_("id", buyer_ids[i:i + IN_CHUNK]).execute()
                buyers.extend(resp.data or [])
        else:
            offset = 0
            while True:
                page = (
                    sb.table("buyers").select("*").eq("active", True)
                    .order("id").range(offset, offset + SCORE_PAGE - 1).execute().data or []
                )
                if not page:
                    break
                buyers.extend(page)
                offset += len(page)

        if not buyers:
            return

        all_ids = [b["id"] for b in buyers]
        tx_map: dict[str, list] = {bid: [] for bid in all_ids}
        for i in range(0, len(all_ids), IN_CHUNK):
            offset = 0
            while True:
                page = (
                    sb.table("buyer_transactions").select("*")
                    .in_("buyer_id", all_ids[i:i + IN_CHUNK])
                    .order("id").range(offset, offset + SCORE_PAGE - 1).execute().data or []
                )
                if not page:
                    break
                for tx in page:
                    if tx.get("buyer_id") in tx_map:
                        tx_map[tx["buyer_id"]].append(tx)
                offset += len(page)

        from tools.buyer_intelligence_engine import batch_score_buyers
        updates = batch_score_buyers(buyers, tx_map)

        for update in updates:
            bid = update.pop("id")
            sb.table("buyers").update(update).eq("id", bid).execute()

        logger.info(f"[buyers_api/score] Scored {len(updates)} buyers")

    except Exception as exc:
        logger.error(f"[buyers_api/score] Scoring failed: {exc}")


@router.get("/imports")
def list_buyer_imports(limit: int = 50) -> dict:
    """Every buyer upload with how many of its buyers still exist."""
    sb = _get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    logs = (
        sb.table("buyer_import_log")
        .select("id,created_at,filename,market,status,buyers_created,buyers_updated,rows_total")
        .order("created_at", desc=True).limit(max(1, min(limit, 200))).execute().data or []
    )
    for log in logs:
        resp = sb.table("buyers").select("id", count="exact").eq("import_log_id", log["id"]).limit(1).execute()
        log["buyers_remaining"] = resp.count if getattr(resp, "count", None) is not None else len(resp.data or [])
    return {"imports": logs}


@router.delete("/imports/{import_id}")
def delete_buyer_import(import_id: str) -> dict:
    """Delete an uploaded buyer list: the buyers it *created* (their transactions
    cascade) and the import log row. Buyers that already existed before this
    upload and were merely updated by it are not touched."""
    sb = _get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    found = sb.table("buyer_import_log").select("id,filename").eq("id", import_id).limit(1).execute().data
    if not found:
        raise HTTPException(404, "Import not found")
    deleted = 0
    while True:
        ids = [r["id"] for r in (
            sb.table("buyers").select("id").eq("import_log_id", import_id).limit(1000).execute().data or []
        )]
        if not ids:
            break
        for i in range(0, len(ids), IN_CHUNK):
            sb.table("buyers").delete().in_("id", ids[i:i + IN_CHUNK]).execute()
        deleted += len(ids)
    sb.table("buyer_import_log").delete().eq("id", import_id).execute()
    return {"status": "ok", "filename": found[0].get("filename"), "buyers_deleted": deleted}


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
        buyers = _read_all_confirmed(lambda: sb.table("buyers").select("*",count="exact")
            .eq("active",True).order("id"),"Active buyers")

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
    """Complete a bounded batch and report actual provider results."""
    if not req.buyer_ids or len(req.buyer_ids) > 25:
        raise HTTPException(422, "Send between 1 and 25 buyer IDs per batch.")
    return await run_in_threadpool(_send_sms_blast, req)


def _send_sms_blast(req: OutreachRequest) -> dict:
    sb = _get_supabase()
    if sb is None:
        raise HTTPException(503, "Database not configured")
    from tools.sms_client import SMSClient
    from schemas.outreach import OutreachChannel, OutreachMessage
    from web.api.marketing_api import _contact_suppressed
    sms = SMSClient()
    counts = {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "dry_run_count": 0, "log_failed_count": 0}
    buyer_ids = list(dict.fromkeys(req.buyer_ids))

    for buyer_id in buyer_ids:
        delivery_recorded = False
        try:
            if sb:
                buyer_resp = sb.table("buyers").select("first_name,last_name,phone,sms_opt_in,active").eq("id", buyer_id).single().execute()
                buyer = buyer_resp.data or {}
            else:
                buyer = {}

            phone = buyer.get("phone", "")
            if (not phone or buyer.get("sms_opt_in") is not True or buyer.get("active") is False
                    or _contact_suppressed(sb, phone)):
                counts["skipped_count"] += 1
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

            if not re.search(r"reply\s+stop\b", body, re.IGNORECASE):
                body += " Reply STOP to opt out."
            message = OutreachMessage(
                lead_id=buyer_id, channel=OutreachChannel.SMS,
                body=body, compliance_cleared=True,
            )
            result = sms.send(message, phone)
            status = "dry_run" if result and message.a2p_provider.endswith(":dry-run") else "sent" if result else "failed"
            counts[f"{status}_count"] += 1
            delivery_recorded = True

            if sb:
                sb.table("buyer_outreach_log").insert({
                    "buyer_id":     buyer_id,
                    "deal_id":      req.deal_id,
                    "channel":      "sms",
                    "status":       status,
                    "body":         body,
                    "to_address":   phone,
                    "provider":     message.a2p_provider or sms._provider,
                }).execute()

                # Update ignore count if this is a re-blast (not first contact)
                if status == "sent":
                    sb.table("buyers").update({
                        "last_contact_date": datetime.now(timezone.utc).date().isoformat()
                    }).eq("id", buyer_id).execute()

        except Exception as exc:
            counts["log_failed_count" if delivery_recorded else "failed_count"] += 1
            logger.error(f"[buyers_api/sms] Send to {buyer_id} failed: {exc}")

    return {
        "status": "partial" if counts["failed_count"] or counts["log_failed_count"] else "complete",
        "recipient_count": len(buyer_ids),
        **counts,
    }


@router.post("/outreach/email")
async def send_email_blast(req: OutreachRequest, background_tasks: BackgroundTasks) -> dict:
    """Send a bounded batch and preserve the operator's edited subject/body."""
    if not req.buyer_ids or len(req.buyer_ids) > 25:
        raise HTTPException(422, "Send between 1 and 25 buyer IDs per batch.")
    return await run_in_threadpool(_send_email_blast, req)


def _send_email_blast(req: OutreachRequest) -> dict:
    sb = _get_supabase()
    if sb is None:
        raise HTTPException(503, "Database not configured")
    from config.settings import settings
    from tools.email_client import EmailClient
    email = EmailClient()
    counts = {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "dry_run_count": 0, "log_failed_count": 0}
    buyer_ids = list(dict.fromkeys(req.buyer_ids))

    for buyer_id in buyer_ids:
        delivery_recorded = False
        try:
            if sb:
                buyer_resp = sb.table("buyers").select("first_name,last_name,email,email_opt_in,active").eq("id", buyer_id).single().execute()
                buyer = buyer_resp.data or {}
            else:
                buyer = {}

            email_addr = buyer.get("email", "")
            if not email_addr or buyer.get("email_opt_in") is not True or buyer.get("active") is False:
                counts["skipped_count"] += 1
                continue
            if sb.table("dnc_registry").select("id").eq("email", email_addr.strip().lower()).limit(1).execute().data:
                counts["skipped_count"] += 1
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

            subject = req.custom_subject or subject
            if req.custom_message:
                plain_body = req.custom_message
                html_body = "<p>" + html.escape(plain_body).replace("\n", "<br>\n") + "</p>"
            else:
                plain_body = html.unescape(re.sub(r"<[^>]+>", "", html_body))
            sent = email.send(to_email=email_addr, subject=subject, body=plain_body, html_body=html_body)
            status = "dry_run" if sent and not email._configured else "sent" if sent else "failed"
            counts[f"{status}_count"] += 1
            delivery_recorded = True

            if sb:
                sb.table("buyer_outreach_log").insert({
                    "buyer_id":   buyer_id,
                    "deal_id":    req.deal_id,
                    "channel":    "email",
                    "status":     status,
                    "subject":    subject,
                    "body":       html_body,
                    "to_address": email_addr,
                    "provider":   email._provider,
                }).execute()
                if status == "sent":
                    sb.table("buyers").update({
                        "last_contact_date": datetime.now(timezone.utc).date().isoformat()
                    }).eq("id", buyer_id).execute()

        except Exception as exc:
            counts["log_failed_count" if delivery_recorded else "failed_count"] += 1
            logger.error(f"[buyers_api/email] Send to {buyer_id} failed: {exc}")

    return {
        "status": "partial" if counts["failed_count"] or counts["log_failed_count"] else "complete",
        "recipient_count": len(buyer_ids), **counts,
    }


@router.get("/{buyer_id}/transactions")
def get_buyer_transactions(buyer_id: str) -> dict:
    """Return all purchase transactions for a buyer."""
    sb = _get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    try:
        rows = _read_all_confirmed(lambda: sb.table("buyer_transactions").select("*",count="exact")
            .eq("buyer_id",buyer_id).order("purchase_date",desc=True).order("id"),"Buyer purchase history")
        return {"transactions":rows,"buyer_id":buyer_id,"total":len(rows)}
    except Exception:
        logger.exception("Buyer purchase history read failed")
        raise HTTPException(503,"Purchase history could not be confirmed. Retry loading it.")


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

        txs = _read_all_confirmed(lambda: sb.table("buyer_transactions").select("*",count="exact")
            .eq("buyer_id",buyer_id).order("purchase_date",desc=True).order("id"),"Buyer classification history")

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
