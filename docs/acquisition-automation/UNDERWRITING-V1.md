# Acquisition underwriting v1

Implementation: `schemas/acquisition_underwriting.py` and `tools/acquisition_underwriting.py`. Calculation identifier: `acquisition-underwriting-v1`. This is an internal, deterministic preview engine, not an offer, market-data service or persisted scenario lifecycle. Existing legacy analyzer/manual-save behavior remains unchanged.

## Inputs and evidence

Supply explicit base, downside and upside cases using the same strategy. Every numeric assumption carries a source, basis (`estimate` or `source_reported`), confidence, and optional as-of date. Neither basis asserts independent verification. Missing fields and null values remain missing. A deliberate zero must be supplied as a sourced assumption; no omitted market value, repair budget, financing cost, vacancy or expense defaults to zero. Unknown required inputs produce an incomplete result with no MAO/offer range. An assignment can still report a known gross spread while buyer economics remain incomplete.

Rates are fractions (0.06 means 6%). Currency inputs have cent precision and bounded magnitude. Rates have at most eight decimal places; holding months support fractional periods. NaN, infinity, negative costs, invalid rates, unsupported extra cost buckets and average debt balances above principal are rejected. Rental target cap and cash-on-cash rates must be positive. Required rental amortization months are explicit: zero means interest-only; otherwise at least 12 months.

The engine does not retrieve property facts or fabricate market estimates. Property dimensions/condition/comps, legal/title evidence, valuation freshness and repair diligence must be integrated before persisted offer preparation. The response retains all supplied provenance and marks inputs as not independently verified. Confidence is the weakest supplied numeric assumption, reduced to low when required inputs are missing. Cases labeled downside/upside are checked against the corresponding profit/cash-flow measure; inconsistent label ordering is flagged without silently reordering inputs.

## Cost definitions and formulas

All calculations use Decimal precision; intermediate arithmetic is unrounded. Displayed currency rounds half up, ratios to six places, and offer ceilings/floors round down to cents so a maximum offer cannot round above the computed ceiling. Rounded displayed cost components can differ by a cent from rounded totals.

Acquisition closing excludes financing fees and liens entered separately. Liens are incremental buyer-paid liabilities, not amounts already included in the purchase price. Holding monthly costs exclude interest. Points use supplied committed principal; interest uses the supplied average outstanding balance and holding months. Other financing fees exclude points/interest. No debt principal is treated as an expense. These definitions must be enforced by source adapters and operator review; the engine cannot detect an expense already embedded in an external quoted amount.

- Simple holding interest = average debt balance × annual rate × holding months / 12.
- Points = principal × points rate.
- Holding costs = holding months × monthly carrying costs excluding interest.
- Variable selling costs = exit value × selling rate; selling-fixed excludes that amount.

For flips, non-purchase costs are acquisition closing, liens, repairs, contingency, holding costs, financing interest/points/fees, and variable/fixed selling costs. **MAO = ARV − non-purchase costs − target profit.** Profit at the proposed purchase price = ARV − purchase price − non-purchase costs.

Development uses the same sale economics with completed project value and separate hard costs, soft costs, infrastructure, permits and contingency. Soft costs must exclude permits/infrastructure entered separately. No zoning, density, entitlement or construction feasibility is assumed to be confirmed.

Sale outputs include total project cost, profit, profit/project-cost, profit margin, and profit/net-project-cash. Net-project-cash = total project cost − debt principal. This is a defined aggregate denominator, not peak equity or an annualized IRR. Cash timing/draw schedules, refinancing, income taxes and peak funding are not modeled. Nonpositive net cash leaves the corresponding ratio undefined and suppresses the proposed offer range pending financing review.

For rentals, holding costs and simple interest cover only the pre-stabilization period; the stabilized operating year is separate. Annual effective rent accounts for vacancy. NOI subtracts property tax, insurance, maintenance, utilities, HOA, other operating costs and management on effective rent. NOI excludes capital reserves and debt service. Cash flow subtracts those two items after NOI. The fixed loan amortizes beginning at stabilization; the holding period is modeled as interest-only. At zero interest, amortizing payment is principal / term. Interest-only debt service is principal × annual rate.

Rental purchase ceilings are the minimum of:

1. NOI / target cap rate − non-purchase project basis costs.
2. Annual cash flow / target cash-on-cash + debt principal − non-purchase project basis costs.
3. Supplied market value − non-purchase project basis costs.

These are ceilings on the modeled investment basis using fixed debt assumptions, not an appraisal. Debt-service coverage is undefined for zero debt service. Rental outputs are one stabilized year, not a multi-year return or refinance/exit model. A changed price requires financing re-underwriting.

For assignments, **gross spread = end buyer price − contract price**; net proceeds subtract assignment expenses. A separate flip/rental/development buyer case must use the same end buyer purchase price and independently support it. Supported buyer price is the lesser of proposed price and the buyer's calculated MAO. Contract MAO = supported buyer price − assignment expenses − target net fee. Unsupported/incomplete buyer economics suppress the proposed offer range, even if the arithmetic gross spread is positive. Contract enforceability, assignability, disclosures, title and closing approval are separate mandatory gates.

## Offers and access

The proposed range uses an explicit input floor fraction × MAO through MAO. No default discount is invented. A negative MAO remains visible and produces no range; it is never silently clamped to zero. All ranges are preliminary internal calculations, require human approval and are unsuitable for direct seller display. Binding offers and contracts are not transmitted.

`POST /api/acquisition/workspaces/{workspace_id}/leads/{lead_id}/underwriting/preview` first checks the canonical workspace lead binding through the user-scoped store/RLS. Owner/admin/operator roles can read this binding; callers/agencies cannot. The response derives property ID from the binding rather than accepting it from the client. The endpoint performs only a scoped read, reports `persisted=false`, and changes no lead MAO, analysis record, offer or source data.

## Remaining persistence work

Extend the existing `deal_analyses` table for strategy, versioned input/output snapshots and case relationships rather than adding a duplicate analysis store. Its legacy `sync_deal_to_lead` trigger must be adapted/tested so historic or downside/upside scenarios cannot overwrite current lead MAO. Add immutable approvals, historical versions, current-scenario selection and offer linkage under workspace roles. The current preview alone does not satisfy UW-002/UW-007 persistence or offer lifecycle requirements. Full-schema migration and production activation remain separately gated.
