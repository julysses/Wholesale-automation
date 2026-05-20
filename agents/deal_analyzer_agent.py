"""
AI Property Deal Analyzer Agent

Combines ARV estimation, repair cost modeling, and MAO calculation into a
single structured output per PRD Section 10–12.

PRD repair tiers (per sqft):
  Light renovation        $15 – $25 / sqft
  Moderate renovation     $25 – $45 / sqft
  Heavy renovation        $45 – $75 / sqft
  Full gut renovation     $75+       / sqft

PRD MAO formula:
  MAO = (ARV × investor_buy_ratio) − repair_cost − holding_costs
        − closing_costs − assignment_fee

Typical investor ratio: 0.70 – 0.75 × ARV

Outputs:
  • ARV estimate (low / mid / high)
  • repair tier + cost estimate (low / mid / high)
  • as-is value
  • MAO
  • recommended offer range
  • projected assignment fee
  • deal spread
  • recommended exit strategy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings
from tools.batchdata_adapter import BatchDataAdapter

logger = logging.getLogger(__name__)


# ── Repair tier constants ─────────────────────────────────────────────────────

REPAIR_TIERS: dict[str, tuple[float, float]] = {
    "light":     (15.0, 25.0),   # $15–$25/sqft
    "moderate":  (25.0, 45.0),   # $25–$45/sqft
    "heavy":     (45.0, 75.0),   # $45–$75/sqft
    "full_gut":  (75.0, 120.0),  # $75+/sqft
}

REPAIR_TIER_LABELS: dict[str, str] = {
    "light":    "Light Renovation",
    "moderate": "Moderate Renovation",
    "heavy":    "Heavy Renovation",
    "full_gut": "Full Gut Renovation",
}


# ── PRD cost assumptions ──────────────────────────────────────────────────────

HOLDING_COST_DEFAULT    = 0.02   # 2% of ARV (6 months holding ÷ 12 months × 4% annual)
CLOSING_COST_DEFAULT    = 0.02   # 2% of ARV (title, escrow, transfer)
ASSIGNMENT_FEE_DEFAULT  = 15_000 # target assignment fee per PRD
INVESTOR_BUY_RATIO_LOW  = 0.70   # conservative
INVESTOR_BUY_RATIO_HIGH = 0.75   # aggressive


# ── Conservative fallback market assumptions ─────────────────────────────────

DEFAULT_MARKET_PPSF = 125.0

STATE_MARKET_PPSF: dict[str, float] = {
    "TX": 135.0,
}

CITY_MARKET_PPSF: dict[tuple[str, str], float] = {
    ("TX", "austin"): 210.0,
    ("TX", "round rock"): 185.0,
    ("TX", "cedar park"): 190.0,
    ("TX", "dallas"): 175.0,
    ("TX", "fort worth"): 165.0,
    ("TX", "arlington"): 160.0,
    ("TX", "plano"): 205.0,
    ("TX", "frisco"): 220.0,
    ("TX", "houston"): 155.0,
    ("TX", "katy"): 170.0,
    ("TX", "spring"): 150.0,
    ("TX", "san antonio"): 145.0,
    ("TX", "new braunfels"): 165.0,
    ("TX", "el paso"): 130.0,
    ("TX", "corpus christi"): 135.0,
    ("TX", "lubbock"): 125.0,
    ("TX", "waco"): 135.0,
    ("TX", "mcallen"): 120.0,
}

ZIP_PREFIX_MARKET_PPSF: dict[tuple[str, str], float] = {
    ("TX", "787"): 215.0,  # Austin
    ("TX", "750"): 190.0,  # North Dallas suburbs
    ("TX", "752"): 175.0,  # Dallas
    ("TX", "760"): 160.0,  # Arlington / mid-cities
    ("TX", "761"): 165.0,  # Fort Worth
    ("TX", "770"): 155.0,  # Houston
    ("TX", "774"): 165.0,  # Houston suburbs
    ("TX", "780"): 145.0,  # San Antonio area
    ("TX", "782"): 145.0,  # San Antonio
    ("TX", "799"): 130.0,  # El Paso
}


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class ARVEstimate:
    low: float
    mid: float
    high: float
    comp_count: int = 0
    confidence: str = "medium"   # low | medium | high
    notes: str = ""
    arv_source: str = "heuristic"  # batchdata | heuristic

    @property
    def range_str(self) -> str:
        return f"${self.low:,.0f} – ${self.high:,.0f}"


@dataclass
class RepairEstimate:
    tier: str                    # light | moderate | heavy | full_gut
    tier_label: str
    sqft: int
    cost_per_sqft_low: float
    cost_per_sqft_high: float
    cost_low: float
    cost_mid: float
    cost_high: float
    notes: str = ""

    @property
    def range_str(self) -> str:
        return f"${self.cost_low:,.0f} – ${self.cost_high:,.0f}"


@dataclass
class DealAnalysis:
    """Complete PRD deal analysis output for one property."""

    lead_id: str
    property_address: str

    # ARV
    arv: ARVEstimate = field(default_factory=lambda: ARVEstimate(0, 0, 0))

    # Repair
    repair: RepairEstimate = field(default_factory=lambda: RepairEstimate(
        tier="moderate", tier_label="Moderate Renovation",
        sqft=0, cost_per_sqft_low=25, cost_per_sqft_high=45,
        cost_low=0, cost_mid=0, cost_high=0,
    ))

    # Cost assumptions
    holding_costs: float = 0.0
    closing_costs: float = 0.0
    assignment_fee: float = ASSIGNMENT_FEE_DEFAULT
    investor_buy_ratio: float = INVESTOR_BUY_RATIO_LOW

    # Key outputs
    mao: float = 0.0                     # Max Allowable Offer
    as_is_value: float = 0.0             # ARV minus cost to make retail-ready
    offer_range_low: float = 0.0
    offer_range_high: float = 0.0
    projected_assignment_fee: float = 0.0
    deal_spread: float = 0.0             # MAO − offer_range_high (margin)

    # Strategy
    exit_strategy: str = "wholesale"     # wholesale | wholetail | novation | investor_resale
    is_viable: bool = True
    weak_deal_reasons: list[str] = field(default_factory=list)

    # ARV data source (propagated from ARVEstimate for easy access)
    arv_source: str = "heuristic"        # batchdata | heuristic

    # LLM notes
    summary: str = ""

    @property
    def offer_range_str(self) -> str:
        return f"${self.offer_range_low:,.0f} – ${self.offer_range_high:,.0f}"

    @property
    def mao_str(self) -> str:
        return f"${self.mao:,.0f}"

    @property
    def assignment_fee_str(self) -> str:
        return f"${self.projected_assignment_fee:,.0f}"


# ── Core calculation engine ───────────────────────────────────────────────────

def determine_repair_tier(
    condition: str,
    year_built: int = 0,
    vacancy_months: int = 0,
    has_code_violation: bool = False,
) -> str:
    """
    Map property signals to PRD repair tier.

    condition values (from qualification_agent): fully_updated | minor_repairs |
    needs_repairs | major_repairs
    """
    if condition in ("major_repairs",) or has_code_violation or vacancy_months > 12:
        return "full_gut" if (year_built > 0 and year_built < 1970) else "heavy"
    if condition == "needs_repairs":
        return "moderate"
    if condition == "minor_repairs":
        return "light"
    return "light"   # fully_updated


def estimate_repair_cost(
    tier: str,
    sqft: int,
) -> RepairEstimate:
    """Build a RepairEstimate for the given tier and square footage."""
    if sqft <= 0:
        sqft = 1_500   # fallback if unknown

    low_rate, high_rate = REPAIR_TIERS.get(tier, REPAIR_TIERS["moderate"])
    mid_rate = (low_rate + high_rate) / 2

    return RepairEstimate(
        tier=tier,
        tier_label=REPAIR_TIER_LABELS.get(tier, tier),
        sqft=sqft,
        cost_per_sqft_low=low_rate,
        cost_per_sqft_high=high_rate,
        cost_low=round(low_rate * sqft, -2),
        cost_mid=round(mid_rate * sqft, -2),
        cost_high=round(high_rate * sqft, -2),
    )


def calculate_mao(
    arv: float,
    repair_cost: float,
    investor_buy_ratio: float = INVESTOR_BUY_RATIO_LOW,
    holding_costs: float = 0.0,
    closing_costs: float = 0.0,
    assignment_fee: float = ASSIGNMENT_FEE_DEFAULT,
) -> float:
    """
    PRD MAO formula:
      MAO = (ARV × investor_buy_ratio) − repair_cost
            − holding_costs − closing_costs − assignment_fee
    """
    return max(
        0.0,
        (arv * investor_buy_ratio)
        - repair_cost
        - holding_costs
        - closing_costs
        - assignment_fee,
    )


def fallback_price_per_sqft(
    city: str = "",
    state: str = "TX",
    zip_code: str = "",
    beds: int = 0,
) -> tuple[float, str]:
    """
    Conservative fallback price-per-sqft when comp/AVM sources are unavailable.

    This is intentionally a last-resort underwriting guardrail, not a comp model.
    """
    normalized_state = (state or "TX").strip().upper()
    normalized_city = (city or "").strip().lower()
    zip_prefix = (zip_code or "").strip()[:3]

    source = f"{normalized_state} default"
    ppsf = STATE_MARKET_PPSF.get(normalized_state, DEFAULT_MARKET_PPSF)

    city_key = (normalized_state, normalized_city)
    if normalized_city and city_key in CITY_MARKET_PPSF:
        ppsf = CITY_MARKET_PPSF[city_key]
        source = f"{city.title()}, {normalized_state}"
    elif zip_prefix and (normalized_state, zip_prefix) in ZIP_PREFIX_MARKET_PPSF:
        ppsf = ZIP_PREFIX_MARKET_PPSF[(normalized_state, zip_prefix)]
        source = f"{normalized_state} ZIP prefix {zip_prefix}"

    if beds >= 4:
        ppsf *= 1.04
    elif beds in (1, 2):
        ppsf *= 0.94

    return ppsf, source


def build_deal_analysis(
    lead_id: str,
    property_address: str,
    arv_low: float,
    arv_mid: float,
    arv_high: float,
    sqft: int = 0,
    condition: str = "needs_repairs",
    year_built: int = 0,
    has_code_violation: bool = False,
    vacancy_months: int = 0,
    comp_count: int = 0,
    confidence: str = "medium",
    arv_notes: str = "",
    arv_source: str = "heuristic",
    repair_tier_override: str = "",
    assignment_fee: float = ASSIGNMENT_FEE_DEFAULT,
) -> DealAnalysis:
    """
    Build a complete DealAnalysis from raw property inputs.

    Uses PRD MAO formula and repair tier model.
    Returns offer_range as (MAO × 0.92) to (MAO × 0.97) to maintain
    a $3k–$8k margin below MAO for negotiation room.
    """
    arv = ARVEstimate(
        low=arv_low, mid=arv_mid, high=arv_high,
        comp_count=comp_count, confidence=confidence, notes=arv_notes,
        arv_source=arv_source,
    )

    tier = repair_tier_override or determine_repair_tier(
        condition, year_built, vacancy_months, has_code_violation,
    )
    repair = estimate_repair_cost(tier, sqft or 1_500)

    holding_costs = round(arv_low * HOLDING_COST_DEFAULT, -2)
    closing_costs = round(arv_low * CLOSING_COST_DEFAULT, -2)

    mao = calculate_mao(
        arv=arv_low,
        repair_cost=repair.cost_high,   # conservative: use high repair estimate
        investor_buy_ratio=INVESTOR_BUY_RATIO_LOW,
        holding_costs=holding_costs,
        closing_costs=closing_costs,
        assignment_fee=assignment_fee,
    )

    # Offer range: 92–97% of MAO (keeps negotiation room)
    offer_low  = round(mao * 0.92, -3)
    offer_high = round(mao * 0.97, -3)

    # As-is value ≈ ARV − repair_mid − transaction costs
    as_is = max(0.0, arv_low - repair.cost_mid - closing_costs)

    # Projected assignment fee = MAO − offer_high (what we keep)
    projected_fee = max(0.0, mao - offer_high)
    deal_spread   = max(0.0, mao - offer_high)

    # Exit strategy heuristic
    if mao <= 0 or offer_high <= 0:
        exit_strategy = "too_risky"
        is_viable = False
        reasons = ["MAO ≤ 0 — deal has insufficient spread"]
    elif repair.tier in ("heavy", "full_gut"):
        exit_strategy = "wholesale"
        is_viable = True
        reasons = []
    elif arv_low > 350_000:
        exit_strategy = "wholetail"
        is_viable = True
        reasons = []
    else:
        exit_strategy = "wholesale"
        is_viable = True
        reasons = []

    return DealAnalysis(
        lead_id=lead_id,
        property_address=property_address,
        arv=arv,
        repair=repair,
        holding_costs=holding_costs,
        closing_costs=closing_costs,
        assignment_fee=assignment_fee,
        investor_buy_ratio=INVESTOR_BUY_RATIO_LOW,
        mao=mao,
        as_is_value=as_is,
        offer_range_low=offer_low,
        offer_range_high=offer_high,
        projected_assignment_fee=projected_fee,
        deal_spread=deal_spread,
        exit_strategy=exit_strategy,
        is_viable=is_viable,
        weak_deal_reasons=reasons,
        arv_source=arv_source,
        summary=(
            f"ARV: ${arv_low:,.0f}–${arv_high:,.0f} | "
            f"Repairs ({repair.tier_label}): {repair.range_str} | "
            f"MAO: ${mao:,.0f} | Offer: {offer_low:,.0f}–{offer_high:,.0f} | "
            f"Proj. fee: ${projected_fee:,.0f}"
        ),
    )


# ── LLM-powered Deal Analyzer Agent ──────────────────────────────────────────

class DealAnalyzerAgent:
    """
    AI Property Deal Analyzer Agent.

    Uses BatchData as the primary ARV source, falling back to Claude (LLM)
    to estimate ARV from property characteristics when no
    real data is available, then applies the deterministic PRD formula
    for repair cost, MAO, and offer range.

    Falls back to conservative heuristics if ANTHROPIC_API_KEY is not set.
    """

    name = "deal_analyzer_agent"

    _SYSTEM_PROMPT = """
You are a real estate investment analyst specializing in off-market wholesale deals in Texas.

Given property details, estimate:
1. ARV (After Repair Value) — low, mid, high range
2. Number of comparable sales you can reference (comp_count)
3. Notes explaining your ARV reasoning

Return ONLY a valid JSON object (no markdown):
{
  "arv_low": <number>,
  "arv_mid": <number>,
  "arv_high": <number>,
  "comp_count": <number>,
  "confidence": "<low|medium|high>",
  "arv_notes": "<brief reasoning>"
}

Rules:
- All values in USD, no $ symbols, no commas
- Be conservative — use the low end of the market
- If data is sparse, set confidence = "low" and widen the range
""".strip()

    def __init__(self) -> None:
        import anthropic  # lazy
        self._client = None
        if settings.anthropic_api_key:
            try:
                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            except Exception as exc:
                logger.warning(f"[{self.name}] Anthropic init failed: {exc}")
        else:
            logger.warning(f"[{self.name}] ANTHROPIC_API_KEY not set — using heuristic ARV")

        # BatchData adapter for real-world ARV
        self.batchdata = BatchDataAdapter()

    def analyze(
        self,
        lead_id: str,
        property_address: str,
        city: str,
        state: str = "TX",
        zip_code: str = "",
        beds: int = 3,
        baths: float = 2.0,
        sqft: int = 1_500,
        year_built: int = 0,
        condition: str = "needs_repairs",
        has_code_violation: bool = False,
        vacancy_months: int = 0,
        tax_assessed_value: float = 0.0,
        equity_pct: float = 0.0,
        assignment_fee: float = ASSIGNMENT_FEE_DEFAULT,
    ) -> DealAnalysis:
        """
        Full deal analysis for one property.

        1. Try BatchData for real-world ARV
        2. Fall back to LLM (Claude) if BatchData fails or returns 0
        3. Fall back to heuristic if LLM is unavailable
        4. Repair tier determined from condition signals
        5. PRD formula calculates MAO, offer range, assignment fee
        """
        arv_data = None
        arv_source = "heuristic"

        # Step 1: Real comparable sales from BatchData (primary)
        if self.batchdata:
            comps = self.batchdata.get_comparable_sales(
                address=property_address, city=city, state=state,
                zip_code=zip_code, sqft=sqft, beds=beds, lead_id=lead_id,
            )
            if comps.success and comps.arv_estimate > 0:
                arv_mid = comps.arv_estimate
                arv_data = {
                    "arv_low":    round(arv_mid * 0.90, -3),
                    "arv_mid":    round(arv_mid, -3),
                    "arv_high":   round(arv_mid * 1.10, -3),
                    "comp_count": comps.comp_count,
                    "confidence": "high",
                    "arv_notes":  (
                        f"ARV from {comps.comp_count} BatchData comps "
                        f"(median ${arv_mid:,.0f})"
                    ),
                }
                arv_source = "batchdata"

        # Step 1b: Fallback to BatchData property valuation if comps returned nothing
        if not arv_data and self.batchdata:
            prop_details = self.batchdata.get_property_details(
                property_address, city, state, zip_code, lead_id=lead_id
            )
            if prop_details.success and prop_details.estimated_value > 0:
                arv_mid = prop_details.estimated_value
                arv_data = {
                    "arv_low":    round(arv_mid * 0.90, -3),
                    "arv_mid":    round(arv_mid, -3),
                    "arv_high":   round(arv_mid * 1.10, -3),
                    "comp_count": 0,
                    "confidence": "medium",
                    "arv_notes":  f"BatchData AVM estimate: ${arv_mid:,.0f} (no comps)",
                }
                arv_source = "batchdata"
                # Enrich local variables with real property data
                if prop_details.sqft: sqft = prop_details.sqft
                if prop_details.beds: beds = prop_details.beds
                if prop_details.baths: baths = prop_details.baths
                if prop_details.year_built: year_built = prop_details.year_built

        # Step 2: Fallback to LLM
        if not arv_data:
            if self._client:
                arv_data = self._llm_arv(
                    property_address, city, state, zip_code,
                    beds, baths, sqft, year_built, condition, tax_assessed_value,
                )
            else:
                # Step 3: Fallback to heuristic
                arv_data = self._heuristic_arv(
                    tax_assessed_value, sqft, beds, condition,
                    city=city, state=state, zip_code=zip_code,
                )

        return build_deal_analysis(
            lead_id=lead_id,
            property_address=property_address,
            arv_low=arv_data["arv_low"],
            arv_mid=arv_data["arv_mid"],
            arv_high=arv_data["arv_high"],
            sqft=sqft,
            condition=condition,
            year_built=year_built,
            has_code_violation=has_code_violation,
            vacancy_months=vacancy_months,
            comp_count=arv_data.get("comp_count", 0),
            confidence=arv_data.get("confidence", "medium"),
            arv_notes=arv_data.get("arv_notes", ""),
            arv_source=arv_source,
            assignment_fee=assignment_fee,
        )

    def _llm_arv(
        self,
        address: str, city: str, state: str, zip_code: str,
        beds: int, baths: float, sqft: int, year_built: int,
        condition: str, tax_assessed: float,
    ) -> dict:
        import json
        prompt = (
            f"Address: {address}, {city}, {state} {zip_code}\n"
            f"Beds/Baths: {beds}/{baths} | Sqft: {sqft} | Year Built: {year_built or 'unknown'}\n"
            f"Condition: {condition.replace('_', ' ')}\n"
            f"Tax Assessed Value: ${tax_assessed:,.0f}\n"
        )
        try:
            msg = self._client.messages.create(  # type: ignore[union-attr]
                model=settings.claude_model,
                max_tokens=300,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            return json.loads(text)
        except Exception as exc:
            logger.error(f"[{self.name}] LLM ARV failed: {exc}")
            return self._heuristic_arv(
                tax_assessed, sqft, beds, condition,
                city=city, state=state, zip_code=zip_code,
            )

    @staticmethod
    def _heuristic_arv(
        tax_assessed: float,
        sqft: int,
        beds: int,
        condition: str,
        city: str = "",
        state: str = "TX",
        zip_code: str = "",
    ) -> dict:
        """
        Conservative ARV heuristic when real data and LLM are unavailable.

        Uses market-aware local assumptions instead of a flat statewide sqft
        value, and blends tax assessment when both signals are available.
        """
        ppsf, market_source = fallback_price_per_sqft(city, state, zip_code, beds)
        market_mid = sqft * ppsf if sqft > 0 else 0
        tax_mid = tax_assessed * 1.10 if tax_assessed > 0 else 0

        if tax_assessed > 0:
            if market_mid > 0:
                lower_bound = market_mid * 0.85
                arv_mid = max((tax_mid * 0.65) + (market_mid * 0.35), lower_bound)
            else:
                arv_mid = tax_mid
        elif market_mid > 0:
            arv_mid = market_mid
        else:
            arv_mid = 150_000

        # Adjust for condition
        condition_adj = {
            "fully_updated": 1.05,
            "minor_repairs": 1.00,
            "needs_repairs": 0.92,
            "major_repairs": 0.85,
        }.get(condition, 1.0)
        arv_mid *= condition_adj

        arv_low  = round(arv_mid * 0.90, -3)
        arv_high = round(arv_mid * 1.10, -3)
        arv_mid  = round(arv_mid, -3)

        return {
            "arv_low":   arv_low,
            "arv_mid":   arv_mid,
            "arv_high":  arv_high,
            "comp_count": 0,
            "confidence": "low",
            "arv_notes": (
                "Market-aware heuristic estimate — no BatchData comps/AVM "
                f"or LLM available; used {market_source} at ${ppsf:,.0f}/sqft"
                + (f" blended with tax assessment ${tax_assessed:,.0f}" if tax_mid else "")
            ),
        }


# ── Module-level convenience function ─────────────────────────────────────────

_agent: Optional[DealAnalyzerAgent] = None


def get_deal_analyzer() -> DealAnalyzerAgent:
    global _agent
    if _agent is None:
        _agent = DealAnalyzerAgent()
    return _agent
