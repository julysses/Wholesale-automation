"""
Retell AI / Air AI voice calling adapter.

Supports both Retell AI (retellai.com) and Air AI (air.ai) as interchangeable
AI calling providers. Both use REST API calls to create outbound calls and
webhook callbacks for call completion events.

Blueprint call script:
  "Hello, this is [agent_name] calling about the property at [property_address].
   I was wondering if you would consider an offer on the property?"

Qualification questions:
  1. Timeline to sell
  2. Property condition (good / fair / needs work)
  3. Occupancy (owner-occupied / tenant / vacant)
  4. Mortgage balance (if any)
  5. Asking price / offer range

Outcomes → canonical dispositions:
  NO_ANSWER, VOICEMAIL, WRONG_NUMBER, NOT_INTERESTED, CALLBACK,
  WARM, HOT, APPOINTMENT_SET

HOT and APPOINTMENT_SET trigger acquisition alerts via Supabase notification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Provider enum ─────────────────────────────────────────────────────────────

class AICallingProvider(str, Enum):
    RETELL = "retell"
    AIR_AI = "air_ai"


# ── Disposition mapping ───────────────────────────────────────────────────────

class CallDisposition(str, Enum):
    NO_ANSWER        = "no_answer"
    VOICEMAIL        = "voicemail"
    WRONG_NUMBER     = "wrong_number"
    NOT_INTERESTED   = "not_interested"
    CALLBACK         = "callback"
    WARM             = "warm"
    HOT              = "hot"
    APPOINTMENT_SET  = "appointment_set"
    UNKNOWN          = "unknown"


# Retell AI call status → canonical disposition
RETELL_DISPOSITION_MAP: dict[str, CallDisposition] = {
    "no_answer":              CallDisposition.NO_ANSWER,
    "voicemail":              CallDisposition.VOICEMAIL,
    "wrong_number":           CallDisposition.WRONG_NUMBER,
    "not_interested":         CallDisposition.NOT_INTERESTED,
    "callback_requested":     CallDisposition.CALLBACK,
    "interested":             CallDisposition.WARM,
    "hot_lead":               CallDisposition.HOT,
    "appointment_set":        CallDisposition.APPOINTMENT_SET,
    # Retell system statuses
    "call_error":             CallDisposition.UNKNOWN,
    "completed":              CallDisposition.UNKNOWN,  # resolved by AI analysis
}

# Air AI call outcomes → canonical disposition
AIR_DISPOSITION_MAP: dict[str, CallDisposition] = {
    "no_answer":              CallDisposition.NO_ANSWER,
    "voicemail":              CallDisposition.VOICEMAIL,
    "wrong_number":           CallDisposition.WRONG_NUMBER,
    "not_interested":         CallDisposition.NOT_INTERESTED,
    "call_back":              CallDisposition.CALLBACK,
    "interested":             CallDisposition.WARM,
    "hot":                    CallDisposition.HOT,
    "appointment":            CallDisposition.APPOINTMENT_SET,
    "error":                  CallDisposition.UNKNOWN,
}


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class CallRequest:
    """
    Input for creating an outbound AI call.

    Matches the blueprint call payload structure:
    {
      "lead_id": "uuid",
      "phone_number": "+15551234567",
      "property_address": "123 Main St",
      "owner_name": "John Doe",
      "metadata": {
        "seller_score": 82,
        "distress_flags": ["vacant", "tax_delinquent"]
      }
    }
    """
    lead_id: str
    phone_number: str               # E.164 format e.g. +12145551234
    property_address: str
    owner_name: str
    agent_name: str = ""
    campaign_id: str = ""
    seller_score: Optional[int] = None
    distress_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return the canonical blueprint call payload dict."""
        meta = {
            **self.metadata,
        }
        if self.seller_score is not None:
            meta["seller_score"] = self.seller_score
        if self.distress_flags:
            meta["distress_flags"] = self.distress_flags
        if self.campaign_id:
            meta["campaign_id"] = self.campaign_id
        return {
            "lead_id": self.lead_id,
            "phone_number": self.phone_number,
            "property_address": self.property_address,
            "owner_name": self.owner_name,
            "metadata": meta,
        }


@dataclass
class CallRecord:
    """Stored reference to a created call."""
    call_id: str
    lead_id: str
    provider: AICallingProvider
    phone_number: str
    status: str = "initiated"
    provider_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class QualificationAnswers:
    """Structured answers extracted by the AI from the conversation."""
    timeline_to_sell: Optional[str] = None       # e.g. "ASAP", "3 months", "not sure"
    property_condition: Optional[str] = None     # good | fair | needs_work | unknown
    occupancy: Optional[str] = None              # owner_occupied | tenant | vacant | unknown
    mortgage_balance: Optional[float] = None     # dollar amount if disclosed
    asking_price: Optional[float] = None         # dollar amount if disclosed
    notes: str = ""                              # raw transcript notes


@dataclass
class CallResultEvent:
    """Normalized result from a completed AI call webhook."""
    call_id: str
    lead_id: str
    provider: AICallingProvider
    disposition: CallDisposition
    duration_seconds: int = 0
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    qualification: Optional[QualificationAnswers] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_hot(self) -> bool:
        return self.disposition in (CallDisposition.HOT, CallDisposition.APPOINTMENT_SET)

    @property
    def is_appointment(self) -> bool:
        return self.disposition == CallDisposition.APPOINTMENT_SET

    @property
    def reached_seller(self) -> bool:
        return self.disposition not in (
            CallDisposition.NO_ANSWER,
            CallDisposition.VOICEMAIL,
            CallDisposition.WRONG_NUMBER,
            CallDisposition.UNKNOWN,
        )


# ── Retell AI adapter ─────────────────────────────────────────────────────────

class RetellAdapter:
    """
    Retell AI REST API adapter for outbound AI calling campaigns.

    Retell AI docs: https://docs.retellai.com
    Key endpoints:
      POST /v2/create-phone-call  → initiate call
      GET  /v2/get-call/{call_id} → check call status
      Webhooks: call_started, call_ended, call_analyzed
    """

    BASE_URL = "https://api.retellai.com"

    def __init__(self) -> None:
        self.api_key = settings.retell_api_key
        self.agent_id = settings.retell_agent_id
        self.from_number = settings.retell_from_number
        self._dry_run = not self.api_key

        if self._dry_run:
            logger.warning("[retell] RETELL_API_KEY not set — running in dry-run mode")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_call(self, req: CallRequest) -> CallRecord:
        """Initiate an outbound AI call via Retell AI."""
        if self._dry_run:
            logger.info(
                f"[retell][dry-run] Would call {req.phone_number} for lead {req.lead_id} "
                f"re: {req.property_address}"
            )
            return CallRecord(
                call_id=f"dry_run_{req.lead_id}",
                lead_id=req.lead_id,
                provider=AICallingProvider.RETELL,
                phone_number=req.phone_number,
                status="dry_run",
            )

        payload = build_retell_call_payload(req, self.agent_id, self.from_number)

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.BASE_URL}/v2/create-phone-call",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        call_id = data.get("call_id", "")
        logger.info(f"[retell] Created call {call_id} for lead {req.lead_id}")

        return CallRecord(
            call_id=call_id,
            lead_id=req.lead_id,
            provider=AICallingProvider.RETELL,
            phone_number=req.phone_number,
            status=data.get("call_status", "registered"),
            provider_data=data,
        )

    def get_call_status(self, call_id: str) -> dict[str, Any]:
        """Fetch current status of a call from Retell AI."""
        if self._dry_run:
            return {"call_id": call_id, "call_status": "dry_run"}

        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{self.BASE_URL}/v2/get-call/{call_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def parse_webhook(payload: dict[str, Any]) -> Optional[CallResultEvent]:
        """
        Parse a Retell AI webhook payload into a CallResultEvent.

        Retell webhook event types:
          retell.call.started   → call_started  (call initiated)
          retell.call.answered  → call_answered (seller picked up)
          retell.call.transcript → call_transcript (real-time transcript chunk)
          retell.call.completed → call_ended / call_analyzed (final result)

        Only call_ended and call_analyzed return a full CallResultEvent;
        earlier events return None (caller should persist for real-time transcript).
        """
        # Handle both "event" (Retell v1) and "event_type" (Retell v2) field names
        event_type = payload.get("event") or payload.get("event_type", "")
        call_data = payload.get("call", {})
        call_id = call_data.get("call_id", "")

        if not call_id:
            logger.warning("[retell] Webhook missing call_id")
            return None

        # Non-final events — return None; caller handles storage separately
        NON_FINAL = {
            "call_started", "call_answered", "call_transcript",
            "retell.call.started", "retell.call.answered", "retell.call.transcript",
        }
        if event_type in NON_FINAL:
            logger.debug(f"[retell] Non-final event {event_type!r} for call {call_id}")
            return None

        if event_type not in (
            "call_ended", "call_analyzed",
            "retell.call.completed", "retell.call.analyzed",
        ):
            logger.debug(f"[retell] Unknown event type {event_type!r}")
            return None

        metadata = call_data.get("metadata", {})
        lead_id = metadata.get("lead_id", "")

        # Extract disposition from call_analysis block (call_analyzed event)
        analysis = call_data.get("call_analysis", {})
        raw_disposition = (
            analysis.get("custom_analysis_data", {}).get("disposition")
            or call_data.get("disconnection_reason", "")
        )

        disposition = RETELL_DISPOSITION_MAP.get(
            str(raw_disposition).lower(),
            CallDisposition.UNKNOWN,
        )

        # Extract qualification answers if AI filled them in
        custom_data = analysis.get("custom_analysis_data", {})
        qualification = QualificationAnswers(
            timeline_to_sell=custom_data.get("timeline_to_sell"),
            property_condition=custom_data.get("property_condition"),
            occupancy=custom_data.get("occupancy"),
            mortgage_balance=_safe_float(custom_data.get("mortgage_balance")),
            asking_price=_safe_float(custom_data.get("asking_price")),
            notes=analysis.get("call_summary", ""),
        )

        result = CallResultEvent(
            call_id=call_id,
            lead_id=lead_id,
            provider=AICallingProvider.RETELL,
            disposition=disposition,
            duration_seconds=int(call_data.get("duration_ms", 0) // 1000),
            recording_url=call_data.get("recording_url"),
            transcript=call_data.get("transcript"),
            qualification=qualification,
            raw_payload=payload,
        )

        logger.info(
            f"[retell] Call {call_id} lead={lead_id} "
            f"disposition={disposition.value} hot={result.is_hot}"
        )
        return result


# ── Air AI adapter ────────────────────────────────────────────────────────────

class AirAIAdapter:
    """
    Air AI REST API adapter for outbound AI calling.

    Air AI docs: https://air.ai/api
    Air AI uses agent-based calling with configurable scripts.
    """

    BASE_URL = "https://api.air.ai"

    def __init__(self) -> None:
        self.api_key = settings.air_ai_api_key
        self.agent_id = settings.air_ai_agent_id
        self.from_number = settings.air_ai_from_number
        self._dry_run = not self.api_key

        if self._dry_run:
            logger.warning("[air_ai] AIR_AI_API_KEY not set — running in dry-run mode")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_call(self, req: CallRequest) -> CallRecord:
        """Initiate an outbound AI call via Air AI."""
        if self._dry_run:
            logger.info(
                f"[air_ai][dry-run] Would call {req.phone_number} for lead {req.lead_id} "
                f"re: {req.property_address}"
            )
            return CallRecord(
                call_id=f"dry_run_{req.lead_id}",
                lead_id=req.lead_id,
                provider=AICallingProvider.AIR_AI,
                phone_number=req.phone_number,
                status="dry_run",
            )

        agent_name = req.agent_name or settings.agency_contact_name or "Alex"

        payload = {
            "agent_id": self.agent_id,
            "phone_number": req.phone_number,
            "from_number": self.from_number,
            "variables": {
                "property_address": req.property_address,
                "owner_name": req.owner_name,
                "agent_name": agent_name,
                "agency_name": settings.agency_name,
            },
            "external_id": req.lead_id,
            "metadata": {
                "lead_id": req.lead_id,
                "campaign_id": req.campaign_id,
                **req.metadata,
            },
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.BASE_URL}/v1/calls",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        call_id = data.get("id", data.get("call_id", ""))
        logger.info(f"[air_ai] Created call {call_id} for lead {req.lead_id}")

        return CallRecord(
            call_id=call_id,
            lead_id=req.lead_id,
            provider=AICallingProvider.AIR_AI,
            phone_number=req.phone_number,
            status=data.get("status", "initiated"),
            provider_data=data,
        )

    @staticmethod
    def parse_webhook(payload: dict[str, Any]) -> Optional[CallResultEvent]:
        """Parse an Air AI webhook payload into a CallResultEvent."""
        call_id = payload.get("id") or payload.get("call_id", "")
        if not call_id:
            logger.warning("[air_ai] Webhook missing call id")
            return None

        # Air AI sends call completion events with 'outcome' or 'disposition'
        raw_disposition = (
            payload.get("outcome")
            or payload.get("disposition")
            or payload.get("status", "")
        )
        disposition = AIR_DISPOSITION_MAP.get(
            str(raw_disposition).lower(),
            CallDisposition.UNKNOWN,
        )

        metadata = payload.get("metadata", {})
        lead_id = (
            metadata.get("lead_id")
            or payload.get("external_id", "")
        )

        # Air AI qualification data (if agent fills custom fields)
        custom = payload.get("custom_data", payload.get("analysis", {}))
        qualification = QualificationAnswers(
            timeline_to_sell=custom.get("timeline_to_sell"),
            property_condition=custom.get("property_condition"),
            occupancy=custom.get("occupancy"),
            mortgage_balance=_safe_float(custom.get("mortgage_balance")),
            asking_price=_safe_float(custom.get("asking_price")),
            notes=payload.get("summary", ""),
        )

        result = CallResultEvent(
            call_id=str(call_id),
            lead_id=lead_id,
            provider=AICallingProvider.AIR_AI,
            disposition=disposition,
            duration_seconds=int(payload.get("duration", 0)),
            recording_url=payload.get("recording_url"),
            transcript=payload.get("transcript"),
            qualification=qualification,
            raw_payload=payload,
        )

        logger.info(
            f"[air_ai] Call {call_id} lead={lead_id} "
            f"disposition={disposition.value} hot={result.is_hot}"
        )
        return result


# ── Unified facade ─────────────────────────────────────────────────────────────

class AICallingAdapter:
    """
    Provider-agnostic facade. Selects Retell AI or Air AI based on settings.

    Usage:
        adapter = AICallingAdapter()
        record  = adapter.create_call(CallRequest(...))

        # In webhook handler:
        event = AICallingAdapter.parse_webhook(payload)
    """

    def __init__(self, provider: Optional[AICallingProvider] = None) -> None:
        chosen = provider or AICallingProvider(
            settings.ai_calling_provider or "retell"
        )
        if chosen == AICallingProvider.AIR_AI:
            self._impl: RetellAdapter | AirAIAdapter = AirAIAdapter()
        else:
            self._impl = RetellAdapter()
        self.provider = chosen
        logger.info(f"[ai_calling] Using provider: {chosen.value}")

    def create_call(self, req: CallRequest) -> CallRecord:
        return self._impl.create_call(req)

    def create_call_for_lead(
        self,
        lead_id: str,
        phone_number: str,
        property_address: str,
        owner_name: str,
        campaign_id: str = "",
    ) -> CallRecord:
        """Convenience wrapper matching the most common call pattern."""
        return self.create_call(CallRequest(
            lead_id=lead_id,
            phone_number=phone_number,
            property_address=property_address,
            owner_name=owner_name,
            campaign_id=campaign_id,
        ))

    @staticmethod
    def parse_webhook(
        payload: dict[str, Any],
        provider: Optional[str] = None,
    ) -> Optional[CallResultEvent]:
        """
        Route a raw webhook payload to the correct parser.

        provider hint: "retell" | "air_ai". If omitted, auto-detected from payload shape.
        """
        if provider == "air_ai" or "external_id" in payload:
            return AirAIAdapter.parse_webhook(payload)
        # Default to Retell (has 'event' + 'call' envelope)
        if "event" in payload and "call" in payload:
            return RetellAdapter.parse_webhook(payload)
        # Fallback: try both
        result = RetellAdapter.parse_webhook(payload)
        if result is None:
            result = AirAIAdapter.parse_webhook(payload)
        return result


# ── Blueprint call script template ────────────────────────────────────────────

RETELL_AGENT_PROMPT = """
You are {agent_name}, a real estate acquisitions specialist calling on behalf of {agency_name}.

Your goal is to have a friendly conversation and determine if the property owner would consider
selling their property at {property_address}.

OPENING:
"Hello, may I speak with {owner_name}? Hi {owner_name}, this is {agent_name} calling about
the property at {property_address}. I was wondering if you would consider an offer on the property?"

IF INTERESTED — ask the following qualification questions (naturally, not as a list):
1. "What's your timeline for making a decision — are you looking to move quickly, or is this
   more of a long-term consideration?"
2. "Can you tell me a little about the condition of the property — is it in good shape or does
   it need some work?"
3. "Is the property currently occupied, or is it vacant?"
4. "Do you have an existing mortgage on the property, and if so, roughly what's the balance?"
5. "Do you have a number in mind for what you'd need to get for the property?"

OUTCOMES (set disposition accordingly):
- Owner hangs up / not interested → NOT_INTERESTED
- Owner wants a callback → CALLBACK
- Owner shows some interest → WARM
- Owner is motivated, open to offer → HOT
- Owner schedules a time to discuss → APPOINTMENT_SET
- No answer / voicemail → NO_ANSWER / VOICEMAIL
- Wrong person / number → WRONG_NUMBER

Fill custom_analysis_data with:
  disposition, timeline_to_sell, property_condition, occupancy, mortgage_balance,
  asking_price, call_summary
""".strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val: Any) -> Optional[float]:
    """Convert a value to float, returning None if not possible."""
    if val is None:
        return None
    try:
        # Strip common currency symbols
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def build_call_script_prompt(
    property_address: str,
    owner_name: str,
    agent_name: str = "",
    agency_name: str = "",
) -> str:
    """Return the filled-in agent prompt for a given lead."""
    return RETELL_AGENT_PROMPT.format(
        property_address=property_address,
        owner_name=owner_name,
        agent_name=agent_name or settings.agency_contact_name or "Alex",
        agency_name=agency_name or settings.agency_name or "Texas Wholesale Solutions",
    )


# ── Transcript utilities ───────────────────────────────────────────────────────

@dataclass
class TranscriptTurn:
    """A single speaker turn in a call transcript."""
    role: str          # "agent" | "user" (seller)
    content: str
    timestamp_ms: Optional[int] = None


def parse_transcript(raw_transcript: Any) -> list[TranscriptTurn]:
    """
    Normalize a Retell transcript into a list of TranscriptTurn objects.

    Retell returns transcript as either:
    - A plain string (older API)
    - A list of {"role": str, "content": str, "words": [...]} dicts (newer API)

    Always returns a list regardless of input shape.
    """
    if not raw_transcript:
        return []

    # List format (Retell v2+)
    if isinstance(raw_transcript, list):
        turns = []
        for item in raw_transcript:
            if isinstance(item, dict):
                turns.append(TranscriptTurn(
                    role=item.get("role", "unknown"),
                    content=item.get("content", ""),
                    timestamp_ms=item.get("words", [{}])[0].get("start") if item.get("words") else None,
                ))
        return turns

    # Plain string — split by common patterns like "Agent: ..." / "User: ..."
    if isinstance(raw_transcript, str):
        turns = []
        for line in raw_transcript.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("agent:"):
                turns.append(TranscriptTurn(role="agent", content=line[6:].strip()))
            elif line.lower().startswith(("user:", "seller:", "owner:")):
                content = line.split(":", 1)[1].strip() if ":" in line else line
                turns.append(TranscriptTurn(role="user", content=content))
            else:
                # Append to last turn if ambiguous
                if turns:
                    turns[-1].content += " " + line
                else:
                    turns.append(TranscriptTurn(role="unknown", content=line))
        return turns

    return []


def transcript_to_text(turns: list[TranscriptTurn]) -> str:
    """Convert structured turns back to a flat readable string."""
    lines = []
    for t in turns:
        label = "Agent" if t.role == "agent" else "Seller"
        lines.append(f"{label}: {t.content}")
    return "\n".join(lines)


def extract_lead_signals(
    transcript: Any,
    property_address: str = "",
    owner_name: str = "",
) -> "QualificationResult":  # type: ignore[name-defined]  # noqa: F821
    """
    Parse transcript + run LLM qualification analysis.

    Returns a QualificationResult with:
    - Extracted signals (timeline, condition, occupancy, asking_price, etc.)
    - qualification_score (blueprint formula)
    - classification: HOT | WARM | COLD

    This is the primary entry point used by the webhook handler after
    receiving a completed call transcript from Retell AI.
    """
    from agents.qualification_agent import QualificationAgent  # lazy import

    # Convert transcript to text if it's structured
    if isinstance(transcript, list):
        turns = parse_transcript(transcript)
        text = transcript_to_text(turns)
    elif isinstance(transcript, str):
        text = transcript
    else:
        text = ""

    agent = QualificationAgent()
    return agent.analyze_transcript(text, property_address, owner_name)


# ── Blueprint call payload builder ────────────────────────────────────────────

def build_retell_call_payload(
    req: CallRequest,
    agent_id: str,
    from_number: str,
) -> dict[str, Any]:
    """
    Build the full Retell API payload for POST /v2/create-phone-call.

    Merges the blueprint metadata structure (seller_score, distress_flags)
    with Retell-specific fields (agent_id, retell_llm_dynamic_variables).
    """
    agent_name = req.agent_name or settings.agency_contact_name or "Alex"
    agency_name = settings.agency_name or "Texas Wholesale Solutions"

    blueprint_payload = req.to_payload()

    return {
        "agent_id": agent_id,
        "from_number": from_number,
        "to_number": req.phone_number,
        # Blueprint metadata (lead_id, seller_score, distress_flags, etc.)
        "metadata": {
            **blueprint_payload["metadata"],
            "lead_id": req.lead_id,
            "property_address": req.property_address,
            "owner_name": req.owner_name,
        },
        # Dynamic variables injected into the agent script at runtime
        "retell_llm_dynamic_variables": {
            "property_address": req.property_address,
            "owner_name": req.owner_name,
            "agent_name": agent_name,
            "agency_name": agency_name,
        },
    }
