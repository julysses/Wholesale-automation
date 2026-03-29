"""
VAPI.ai voice calling adapter — "Local Neighbor" Acquisition Specialist.

VAPI is the preferred AI dialer for WholesaleOS:
  - $0.07/min vs Retell's $0.11/min
  - Same adapter interface as retell_adapter.py — swap with one env var

Role: qualification only.  The VAPI agent gathers the 4 Pillars, probes for
a price anchor, then hands off.  It NEVER quotes a final offer — that is
reserved for the human Team Manager (the platform user).

Webhook event types (VAPI):
  call-started      → call initiated
  call-ended        → call finished (final; run qualification)
  transcript        → real-time transcript chunk
  function-call     → agent invoked a tool (e.g. "handoff_to_manager")

HOT / APPOINTMENT_SET dispositions trigger the same acquisition pipeline as
Retell (notification → task → SMS to user).

VAPI docs: https://docs.vapi.ai
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from config.vapi_prompt import VAPI_VOICE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ── Disposition mapping ───────────────────────────────────────────────────────

class CallDisposition(str, Enum):
    NO_ANSWER        = "no_answer"
    VOICEMAIL        = "voicemail"
    WRONG_NUMBER     = "wrong_number"
    NOT_INTERESTED   = "not_interested"
    DNC              = "dnc"
    CALLBACK         = "callback"
    WARM             = "warm"
    HOT              = "hot"
    APPOINTMENT_SET  = "appointment_set"
    UNKNOWN          = "unknown"


# VAPI end-of-call reason → canonical disposition
# VAPI uses `endedReason` in the call-ended payload
VAPI_ENDED_REASON_MAP: dict[str, CallDisposition] = {
    # Call not connected
    "no-answer":                  CallDisposition.NO_ANSWER,
    "voicemail":                  CallDisposition.VOICEMAIL,
    "machine-detected-greeting":  CallDisposition.VOICEMAIL,
    "machine-detected-long-greeting": CallDisposition.VOICEMAIL,
    "machine-end-call":           CallDisposition.VOICEMAIL,
    "machine-end-silence":        CallDisposition.VOICEMAIL,
    "machine-end-other":          CallDisposition.VOICEMAIL,
    "busy":                       CallDisposition.NO_ANSWER,
    "number-not-in-service":      CallDisposition.WRONG_NUMBER,
    "invalid-number":             CallDisposition.WRONG_NUMBER,
    "failed":                     CallDisposition.UNKNOWN,
    "error":                      CallDisposition.UNKNOWN,
    # Connected — outcome determined by assistant analysis
    "customer-ended-call":        CallDisposition.UNKNOWN,  # resolved by analysis
    "assistant-ended-call":       CallDisposition.UNKNOWN,  # resolved by analysis
    "exceeded-max-duration":      CallDisposition.WARM,     # long calls → warm at minimum
    "pipeline-error":             CallDisposition.UNKNOWN,
    "silence-timed-out":          CallDisposition.NO_ANSWER,
    "customer-did-not-give-microphone-permission": CallDisposition.UNKNOWN,
}

# VAPI custom analysis data fields set by the assistant during the call
# These are populated if a VAPI assistant "analyze call" step is configured
VAPI_CUSTOM_DISPOSITION_MAP: dict[str, CallDisposition] = {
    "not_interested":   CallDisposition.NOT_INTERESTED,
    "dnc":              CallDisposition.DNC,
    "callback":         CallDisposition.CALLBACK,
    "warm":             CallDisposition.WARM,
    "hot":              CallDisposition.HOT,
    "appointment_set":  CallDisposition.APPOINTMENT_SET,
    "voicemail":        CallDisposition.VOICEMAIL,
    "no_answer":        CallDisposition.NO_ANSWER,
    "wrong_number":     CallDisposition.WRONG_NUMBER,
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class VapiCallRequest:
    """
    Input for creating an outbound VAPI call.

    Matches the blueprint call payload structure used across all providers:
    {
      "lead_id": "uuid",
      "phone_number": "+15551234567",
      "property_address": "123 Main St",
      "owner_name": "John Doe",
      "metadata": {...}
    }
    """
    lead_id: str
    phone_number: str            # E.164 e.g. +12145551234
    property_address: str
    owner_name: str
    agent_name: str = ""         # Name the AI uses when introducing itself
    campaign_id: str = ""
    seller_score: Optional[int] = None
    distress_flags: list[str] = field(default_factory=list)
    city: str = ""               # Used in "Local Neighbor" framing ("I'm near [City]")
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VapiCallRecord:
    """Stored reference to a created VAPI call."""
    call_id: str
    lead_id: str
    phone_number: str
    status: str = "queued"
    provider_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class VapiQualification:
    """
    4-Pillar qualification answers extracted from the VAPI transcript.

    These map to the same fields as QualificationAnswers in retell_adapter.py
    so the downstream qualification_agent and Supabase tables are unchanged.
    """
    # Pillar 1 — Motivation
    motivation: Optional[str] = None         # foreclosure|probate|divorce|tired_landlord|…
    is_urgent: bool = False                  # hard deadline detected
    # Pillar 2 — Timeline
    timeline_to_sell: Optional[str] = None  # timeline_30|timeline_60|timeline_90|timeline_flexible
    # Pillar 3 — Condition
    property_condition: Optional[str] = None  # needs_major_work|needs_cosmetic|move_in_ready|unknown
    occupancy: Optional[str] = None           # owner_occupied|tenant|vacant|unknown
    # Pillar 4 — Price anchor (what seller wants net in pocket)
    asking_price: Optional[float] = None     # dollar amount if disclosed
    price_anchor_given: bool = False          # did seller give any number?
    # Supporting fields
    mortgage_balance: Optional[float] = None
    notes: str = ""


@dataclass
class VapiCallResult:
    """Normalized result from a completed VAPI call (call-ended event)."""
    call_id: str
    lead_id: str
    disposition: CallDisposition
    duration_seconds: int = 0
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    qualification: Optional[VapiQualification] = None
    ended_reason: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_hot(self) -> bool:
        return self.disposition in (CallDisposition.HOT, CallDisposition.APPOINTMENT_SET)

    @property
    def is_dnc(self) -> bool:
        return self.disposition == CallDisposition.DNC

    @property
    def reached_seller(self) -> bool:
        return self.disposition not in (
            CallDisposition.NO_ANSWER,
            CallDisposition.VOICEMAIL,
            CallDisposition.WRONG_NUMBER,
            CallDisposition.UNKNOWN,
        )


# ── VAPI adapter ───────────────────────────────────────────────────────────────

class VapiAdapter:
    """
    VAPI.ai REST API adapter for outbound AI calling.

    VAPI uses a transient-assistant pattern for outbound calls: you can either
    reference a pre-built assistant by ID (VAPI_ASSISTANT_ID) or pass a full
    assistant config inline. We default to the inline pattern so the
    VAPI_VOICE_SYSTEM_PROMPT from config/vapi_prompt.py is always authoritative.

    Endpoints used:
      POST /call/phone           → create outbound call
      GET  /call/{call_id}       → check call status
      Webhooks: call-started, call-ended, transcript, function-call
    """

    BASE_URL = "https://api.vapi.ai"

    def __init__(self) -> None:
        self.api_key = settings.vapi_api_key
        self.phone_number_id = settings.vapi_phone_number_id
        self.assistant_id = settings.vapi_assistant_id   # optional: use pre-built assistant
        self._dry_run = not self.api_key

        if self._dry_run:
            logger.warning("[vapi] VAPI_API_KEY not set — running in dry-run mode")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_call(self, req: VapiCallRequest) -> VapiCallRecord:
        """
        Initiate an outbound AI call via VAPI.

        If VAPI_ASSISTANT_ID is set, the pre-built assistant is used (cheaper —
        no prompt tokens on every call).  Otherwise the full system prompt is
        sent inline so no VAPI dashboard setup is required.
        """
        if self._dry_run:
            logger.info(
                f"[vapi][dry-run] Would call {req.phone_number} for lead {req.lead_id} "
                f"re: {req.property_address}"
            )
            return VapiCallRecord(
                call_id=f"dry_run_{req.lead_id}",
                lead_id=req.lead_id,
                phone_number=req.phone_number,
                status="dry_run",
            )

        payload = build_vapi_call_payload(req, self.phone_number_id, self.assistant_id)

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.BASE_URL}/call/phone",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        call_id = data.get("id", "")
        logger.info(f"[vapi] Created call {call_id} for lead {req.lead_id}")

        return VapiCallRecord(
            call_id=call_id,
            lead_id=req.lead_id,
            phone_number=req.phone_number,
            status=data.get("status", "queued"),
            provider_data=data,
        )

    def get_call_status(self, call_id: str) -> dict[str, Any]:
        """Fetch current status of a VAPI call."""
        if self._dry_run:
            return {"id": call_id, "status": "dry_run"}

        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{self.BASE_URL}/call/{call_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def parse_webhook(payload: dict[str, Any]) -> Optional[VapiCallResult]:
        """
        Parse a VAPI webhook payload into a VapiCallResult.

        VAPI webhook message types:
          call-started      → call initiated (return None)
          transcript        → real-time transcript chunk (return None)
          function-call     → agent called a tool (return None; handled separately)
          call-ended        → final result with analysis (return VapiCallResult)
          end-of-call-report → alias for call-ended in some VAPI versions

        Only `call-ended` / `end-of-call-report` return a full VapiCallResult.
        """
        msg_type = payload.get("message", {}).get("type", "") or payload.get("type", "")

        # Normalise: VAPI wraps events under payload["message"]
        msg = payload.get("message", payload)
        call = msg.get("call", {})
        call_id = call.get("id", "") or msg.get("callId", "")

        if not call_id:
            logger.warning("[vapi] Webhook missing call id")
            return None

        NON_FINAL = {"call-started", "transcript", "function-call", "assistant-request",
                     "speech-update", "conversation-update", "tool-calls"}
        if msg_type in NON_FINAL:
            logger.debug(f"[vapi] Non-final event {msg_type!r} for call {call_id}")
            return None

        if msg_type not in ("call-ended", "end-of-call-report", ""):
            logger.debug(f"[vapi] Unhandled VAPI message type {msg_type!r}")
            return None

        # ── Extract lead_id from metadata ─────────────────────────────────────
        metadata = call.get("metadata", {}) or msg.get("metadata", {})
        lead_id = metadata.get("lead_id", "")

        # ── Resolve disposition ────────────────────────────────────────────────
        ended_reason = (
            call.get("endedReason")
            or msg.get("endedReason", "")
            or ""
        ).lower().replace("_", "-")

        # Check call analysis first (most accurate)
        analysis = msg.get("analysis", {}) or call.get("analysis", {})
        custom = analysis.get("structuredData", {}) or analysis.get("customAnalysisData", {})
        raw_disposition = str(custom.get("disposition", "")).lower()

        if raw_disposition and raw_disposition in VAPI_CUSTOM_DISPOSITION_MAP:
            disposition = VAPI_CUSTOM_DISPOSITION_MAP[raw_disposition]
        else:
            # Fall back to endedReason
            disposition = VAPI_ENDED_REASON_MAP.get(ended_reason, CallDisposition.UNKNOWN)

        # If still unknown and the call lasted > 60s, treat as WARM minimum
        duration_ms = call.get("endedAt", 0)
        duration_seconds = int(msg.get("durationSeconds", 0) or 0)
        if disposition == CallDisposition.UNKNOWN and duration_seconds > 60:
            disposition = CallDisposition.WARM

        # ── Extract 4-Pillar qualification ────────────────────────────────────
        qualification = _extract_vapi_qualification(custom, analysis)

        # ── Transcript ───────────────────────────────────────────────────────
        raw_transcript = msg.get("transcript") or call.get("transcript")
        if isinstance(raw_transcript, list):
            transcript_text = _turns_to_text(raw_transcript)
        else:
            transcript_text = raw_transcript

        result = VapiCallResult(
            call_id=call_id,
            lead_id=lead_id,
            disposition=disposition,
            duration_seconds=duration_seconds,
            recording_url=call.get("recordingUrl") or msg.get("recordingUrl"),
            transcript=transcript_text,
            qualification=qualification,
            ended_reason=ended_reason,
            raw_payload=payload,
        )

        logger.info(
            f"[vapi] Call {call_id} lead={lead_id} "
            f"disposition={disposition.value} hot={result.is_hot} "
            f"duration={duration_seconds}s"
        )
        return result


# ── VAPI call payload builder ─────────────────────────────────────────────────

def build_vapi_call_payload(
    req: VapiCallRequest,
    phone_number_id: str,
    assistant_id: str = "",
) -> dict[str, Any]:
    """
    Build the VAPI POST /call/phone payload.

    If assistant_id is provided, reference the pre-built assistant.
    Otherwise, embed the full Local Neighbor system prompt inline so
    no VAPI dashboard configuration is required.

    Dynamic variables (property_address, owner_name, agent_name, city) are
    injected via VAPI's `assistantOverrides.variableValues` so the prompt
    template is filled at call time.
    """
    agent_name = req.agent_name or settings.agency_contact_name or "Alex"
    city = req.city or settings.agency_state or "the area"

    variable_values = {
        "property_address": req.property_address,
        "owner_name":       req.owner_name,
        "agent_name":       agent_name,
        "city":             city,
        "manager_name":     settings.agency_contact_name or "my Team Manager",
    }

    metadata = {
        "lead_id":          req.lead_id,
        "campaign_id":      req.campaign_id,
        "property_address": req.property_address,
        "owner_name":       req.owner_name,
    }
    if req.seller_score is not None:
        metadata["seller_score"] = req.seller_score
    if req.distress_flags:
        metadata["distress_flags"] = req.distress_flags
    metadata.update(req.metadata)

    # Analysis schema — VAPI will extract these from the transcript automatically
    analysis_schema = {
        "type": "object",
        "properties": {
            "disposition": {
                "type": "string",
                "enum": [
                    "hot", "warm", "callback", "not_interested",
                    "dnc", "voicemail", "no_answer", "wrong_number", "appointment_set",
                ],
                "description": "Call outcome based on seller response",
            },
            "motivation": {
                "type": "string",
                "description": "Seller's reason for selling (foreclosure, probate, divorce, tired_landlord, etc.)",
            },
            "timeline_to_sell": {
                "type": "string",
                "enum": ["timeline_30", "timeline_60", "timeline_90", "timeline_flexible"],
                "description": "How soon the seller wants to close",
            },
            "property_condition": {
                "type": "string",
                "enum": ["needs_major_work", "needs_cosmetic", "move_in_ready", "unknown"],
            },
            "occupancy": {
                "type": "string",
                "enum": ["owner_occupied", "tenant", "vacant", "unknown"],
            },
            "asking_price": {
                "type": "number",
                "description": "Dollar amount the seller mentioned they want (net in pocket)",
            },
            "price_anchor_given": {
                "type": "boolean",
                "description": "Did the seller give any price number at all?",
            },
            "is_urgent": {
                "type": "boolean",
                "description": "Hard deadline mentioned (foreclosure date, estate deadline)?",
            },
            "call_summary": {
                "type": "string",
                "description": "2–3 sentence summary of the call for the acquisition team",
            },
        },
        "required": ["disposition"],
    }

    base: dict[str, Any] = {
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": req.phone_number,
            "name": req.owner_name,
        },
        "metadata": metadata,
        # Analysis step — VAPI extracts structured data from transcript after call
        "analysisSchema": analysis_schema,
    }

    if assistant_id:
        # Reference a pre-built VAPI assistant (no prompt tokens per call)
        base["assistantId"] = assistant_id
        base["assistantOverrides"] = {
            "variableValues": variable_values,
        }
    else:
        # Inline assistant — no VAPI dashboard setup required
        base["assistant"] = {
            "model": {
                "provider": "anthropic",
                "model":    "claude-haiku-4-5-20251001",
                "messages": [
                    {
                        "role":    "system",
                        "content": VAPI_VOICE_SYSTEM_PROMPT,
                    }
                ],
                "temperature": 0.7,
            },
            "voice": {
                "provider": "11labs",
                "voiceId":  "EXAVITQu4vr4xnSDxMaL",  # "Sarah" — warm, approachable female
            },
            "firstMessage": (
                f"Hi, is this {req.owner_name}? "
                f"Hey, my name is {agent_name} — I actually live right nearby in {city} "
                f"and I work with a small group of local investors. "
                f"I came across the property at {req.property_address} through public records "
                f"— are you at all open to a cash offer on that property?"
            ),
            "endCallMessage": (
                "Perfect. I'm going to pass all of this along right now so they're fully prepared "
                "when they call. Thank you so much for your time today — you're going to hear from "
                "us very soon!"
            ),
            "maxDurationSeconds": 600,      # 10-minute hard cap per call
            "backgroundDenoising": True,
            "recordingEnabled": True,
            "variableValues": variable_values,
        }

    return base


# ── Qualification extractor ───────────────────────────────────────────────────

def _extract_vapi_qualification(
    custom: dict[str, Any],
    analysis: dict[str, Any],
) -> VapiQualification:
    """
    Build a VapiQualification from VAPI's structuredData / customAnalysisData.

    Falls back to keyword scanning in call_summary if structured fields are absent.
    """
    summary = analysis.get("summary", "") or custom.get("call_summary", "")

    asking_raw = custom.get("asking_price")
    asking_price = _safe_float(asking_raw)
    price_anchor = bool(custom.get("price_anchor_given", False)) or asking_price is not None

    return VapiQualification(
        motivation=custom.get("motivation"),
        is_urgent=bool(custom.get("is_urgent", False)),
        timeline_to_sell=custom.get("timeline_to_sell"),
        property_condition=custom.get("property_condition"),
        occupancy=custom.get("occupancy"),
        asking_price=asking_price,
        price_anchor_given=price_anchor,
        mortgage_balance=_safe_float(custom.get("mortgage_balance")),
        notes=summary,
    )


# ── Transcript utilities ───────────────────────────────────────────────────────

def _turns_to_text(turns: list[dict[str, Any]]) -> str:
    """Convert VAPI transcript turns to readable text."""
    lines = []
    for turn in turns:
        role = turn.get("role", "unknown")
        text = turn.get("message", turn.get("content", ""))
        label = "Agent" if role in ("bot", "assistant") else "Seller"
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


def extract_vapi_lead_signals(
    transcript: Any,
    property_address: str = "",
    owner_name: str = "",
) -> Any:
    """
    Run LLM qualification on a VAPI transcript string.

    Same interface as retell_adapter.extract_lead_signals() — both route
    through qualification_agent.QualificationAgent.analyze_transcript().
    """
    from agents.qualification_agent import QualificationAgent  # lazy import

    if isinstance(transcript, list):
        text = _turns_to_text(transcript)
    elif isinstance(transcript, str):
        text = transcript
    else:
        text = ""

    agent = QualificationAgent()
    return agent.analyze_transcript(text, property_address, owner_name)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None
