"""Twilio callbacks: authenticate the public URL, commit events, then acknowledge."""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.datastructures import FormData

from config.settings import settings
from tools.crm import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/twilio", tags=["Twilio"])
STATUSES = {"accepted", "scheduled", "queued", "sending", "sent", "delivered", "undelivered", "failed", "canceled", "read"}


async def _verified(request: Request, kind: str) -> dict:
    from twilio.request_validator import RequestValidator
    token = settings.twilio_auth_token
    base = settings.twilio_webhook_base_url.rstrip("/")
    if not token or not settings.twilio_account_sid or not base.startswith("https://"):
        raise HTTPException(503, "Twilio webhook is not configured")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected form data")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "Payload too large")
    try:
        pairs = parse_qsl(raw.decode("utf-8"), keep_blank_values=True, max_num_fields=100)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid form data")
    form = FormData(pairs)
    # Match exactly the configured public URL; do not trust forwarded/Host headers.
    url = f"{base}/webhooks/twilio/{kind}"
    if request.url.query:
        url += "?" + request.url.query
    signature = request.headers.get("x-twilio-signature", "")
    if not RequestValidator(token).validate(url, form, signature):
        raise HTTPException(401, "Invalid Twilio signature")
    if len({k for k, _ in pairs}) != len(pairs):
        raise HTTPException(400, "Duplicate form fields")
    data = dict(pairs)
    if data.get("AccountSid") != settings.twilio_account_sid:
        raise HTTPException(403, "Unexpected Twilio account")
    if not re.fullmatch(r"SM[0-9a-fA-F]{32}", data.get("MessageSid", "")):
        raise HTTPException(400, "Invalid message SID")
    if kind == "inbound" and data.get("To") != settings.twilio_from_number:
        raise HTTPException(403, "Unexpected destination")
    if kind == "status" and data.get("MessageStatus") not in STATUSES:
        raise HTTPException(400, "Invalid message status")
    if not re.fullmatch(r"\+1\d{10}", data.get("From" if kind == "inbound" else "To", "")):
        raise HTTPException(400, "Invalid US phone")
    return data


async def _receive(request: Request, kind: str) -> Response:
    data = await _verified(request, kind)
    if kind == "status" and request.query_params.get("message_id"):
        try:
            data["app_message_id"] = str(UUID(request.query_params["message_id"]))
        except ValueError:
            raise HTTPException(400, "Invalid message reference")
    event_key = f"twilio:{data['AccountSid']}:{kind}:{data['MessageSid']}"
    if kind == "status":
        event_key += ":" + data["MessageStatus"]
    sb = get_supabase_client()
    if sb is None:
        raise HTTPException(503, "Receipt storage unavailable")
    try:
        result = sb.rpc("record_twilio_event", {
            "p_event": str(uuid5(NAMESPACE_URL, event_key)), "p_kind": kind, "p_payload": data,
        }).execute().data
        if not isinstance(result, dict) or result.get("saved") is not True:
            raise RuntimeError("Receipt unconfirmed")
    except Exception:
        logger.exception("Twilio receipt failed for %s", data["MessageSid"])
        raise HTTPException(503, "Receipt storage unavailable")
    # Twilio Advanced Opt-Out supplies STOP/HELP responses; no duplicate SMS here.
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response/>', media_type="application/xml")


@router.post("/inbound")
async def inbound(request: Request):
    return await _receive(request, "inbound")


@router.post("/status")
async def status(request: Request):
    return await _receive(request, "status")
