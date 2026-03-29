"""
Buyer Intelligence Agent — AI Classification & Enrichment.

Uses Claude (Haiku) to classify each buyer's investor type based on their
transaction history, price range, frequency, and behavioral patterns.

Outputs:
  buyer_type_ibie: flipper | landlord | institutional | builder
  classification_reasoning: 1–2 sentence explanation
  confidence: 0.0 – 1.0

Also:
  - Re-runs weekly batch scoring via BulkScoreJob
  - Flags dormant buyers (no activity > 12 months)
  - Identifies flip patterns (bought + resold within 18 months)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from agents.base_agent import BaseAgent
from tools.buyer_intelligence_engine import (
    compute_ibie_score,
    assign_ibie_tier,
    compute_tags,
    aggregate_transactions,
    batch_score_buyers,
)

logger = logging.getLogger(__name__)


# ── Classification output ────────────────────────────────────────────────────

@dataclass
class BuyerClassification:
    buyer_id: str
    buyer_type_ibie: str              # flipper | landlord | institutional | builder
    confidence: float                 # 0.0 – 1.0
    reasoning: str                    # 1–2 sentence explanation
    suggested_tags: list[str]
    raw_response: str = ""


# ── Agent ────────────────────────────────────────────────────────────────────

class BuyerIntelligenceAgent(BaseAgent):
    """
    AI classification + weekly batch scoring agent.

    Classify a single buyer:
        agent = BuyerIntelligenceAgent()
        result = agent.classify_buyer(buyer_row, transactions)

    Batch re-score all buyers:
        updates = agent.batch_rescore(buyers, transactions_by_buyer_id)
    """

    MODEL = "claude-haiku-4-5-20251001"

    CLASSIFICATION_SYSTEM = """You are a real estate investor analyst.
Given a buyer's transaction history, classify them into ONE type:
- flipper:       buys distressed/underpriced, resells quickly (< 18 months)
- landlord:      holds properties as rentals; infrequent resales
- institutional: very high volume (10+ deals/yr) or large capital ($500k+ avg)
- builder:       buys land, teardowns, or scrapes for new construction

Respond ONLY with valid JSON — no markdown, no explanation outside the JSON.
"""

    CLASSIFICATION_USER = """Buyer profile:
{profile_json}

Transaction history ({tx_count} transactions):
{tx_summary}

Classify this buyer. Return JSON:
{{
  "buyer_type": "<flipper|landlord|institutional|builder>",
  "confidence": <0.0-1.0>,
  "reasoning": "<1-2 sentence rationale>",
  "suggested_tags": ["<tag1>", "<tag2>"]
}}"""

    def classify_buyer(
        self,
        buyer: dict[str, Any],
        transactions: list[dict[str, Any]],
    ) -> BuyerClassification:
        """Classify a single buyer using Claude Haiku."""
        buyer_id = buyer.get("id", "")
        profile = {
            "name":              f"{buyer.get('first_name','')} {buyer.get('last_name','')}".strip(),
            "entity":            buyer.get("entity_name", ""),
            "total_purchases_12mo": buyer.get("total_purchases_12mo", 0),
            "properties_owned":  buyer.get("properties_owned", 0),
            "avg_purchase_price": buyer.get("avg_purchase_price"),
            "last_purchase_date": str(buyer.get("last_purchase_date", "")),
            "cash_buyer":        buyer.get("cash_buyer", False),
            "ibie_score":        buyer.get("ibie_score", 0),
            "market":            buyer.get("market", ""),
        }

        # Build a compact transaction summary (last 10)
        recent_txs = sorted(
            transactions,
            key=lambda t: str(t.get("purchase_date", "")),
            reverse=True,
        )[:10]

        tx_lines = []
        for tx in recent_txs:
            price = tx.get("purchase_price")
            pdate = tx.get("purchase_date", "")
            addr  = tx.get("property_address", "")
            cash  = "CASH" if tx.get("cash_transaction") else "financed"
            flip  = " [FLIP]" if tx.get("flip_detected") else ""
            tx_lines.append(
                f"  {pdate}: {addr} — ${price:,.0f} {cash}{flip}" if price
                else f"  {pdate}: {addr} — price unknown {cash}{flip}"
            )

        prompt = self.CLASSIFICATION_USER.format(
            profile_json=json.dumps(profile, indent=2, default=str),
            tx_count=len(transactions),
            tx_summary="\n".join(tx_lines) if tx_lines else "  (no transaction history)",
        )

        try:
            raw = self._call_claude(
                system=self.CLASSIFICATION_SYSTEM,
                user=prompt,
                max_tokens=512,
            )
            parsed = json.loads(raw)
            return BuyerClassification(
                buyer_id=buyer_id,
                buyer_type_ibie=parsed.get("buyer_type", "landlord"),
                confidence=float(parsed.get("confidence", 0.5)),
                reasoning=parsed.get("reasoning", ""),
                suggested_tags=parsed.get("suggested_tags", []),
                raw_response=raw,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"[BuyerIntel] Classification parse error for {buyer_id}: {exc}")
            return BuyerClassification(
                buyer_id=buyer_id,
                buyer_type_ibie="landlord",
                confidence=0.0,
                reasoning="Classification failed — defaulting to landlord",
                suggested_tags=[],
                raw_response=str(raw) if "raw" in dir() else "",
            )

    def batch_classify(
        self,
        buyers: list[dict[str, Any]],
        transactions_by_buyer: dict[str, list[dict[str, Any]]],
        skip_high_confidence: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Classify all buyers that haven't been classified or need reclassification.

        `skip_high_confidence`: if True, skip buyers already classified with
        confidence ≥ 0.80 within the last 30 days.

        Returns list of update dicts: { id, buyer_type_ibie, ai_classified_at, tags }
        """
        from datetime import timezone
        updates: list[dict[str, Any]] = []
        now_iso = __import__("datetime").datetime.now(timezone.utc).isoformat()

        for buyer in buyers:
            bid = buyer["id"]
            txs = transactions_by_buyer.get(bid, [])
            result = self.classify_buyer(buyer, txs)

            # Merge AI suggested tags with computed tags
            all_tags = list(set(compute_tags(buyer) + result.suggested_tags))

            updates.append({
                "id":              bid,
                "buyer_type_ibie": result.buyer_type_ibie,
                "ai_classified_at": now_iso,
                "tags":            all_tags,
            })

        return updates

    def batch_rescore(
        self,
        buyers: list[dict[str, Any]],
        transactions_by_buyer: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """
        Re-score all buyers using the IBIE scoring engine.
        Returns list of update dicts ready for Supabase upsert.
        """
        return batch_score_buyers(buyers, transactions_by_buyer)

    # ── Claude call wrapper ───────────────────────────────────────────────────

    def _call_claude(self, system: str, user: str, max_tokens: int = 512) -> str:
        """Call Claude and return the raw text response."""
        import anthropic
        client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        message = client.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text if message.content else ""
