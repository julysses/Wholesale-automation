# Acquisition underwriting v1

Implementation: `schemas/acquisition_underwriting.py` and `tools/acquisition_underwriting.py`. Calculation identifier: `acquisition-underwriting-v1`. This is an internal deterministic calculation engine with immutable scenario persistence, not an offer or market-data service. Unbound legacy analysis synchronization is preserved; workspace-bound analyses use the new lifecycle.

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

## Immutable scenario persistence

Migration `20261026040321_acquisition_analysis_versions.sql` extends existing `deal_analyses`; no parallel analysis store is created. POST `/api/acquisition/workspaces/{workspace_id}/leads/{lead_id}/underwriting/scenarios` accepts a stable UUID `id` and `inputs` in preview format. Reuse the exact ID and inputs on retries. Each new ID allocates the next lead revision under a database lock. Canonical property ID comes from the binding. GET on the same path returns bounded revision history (`after`, `limit`).

The user-scoped reservation saves immutable inputs and a pending result, with actor, original session, input hash and calculation version. A separate server worker reads that snapshot and completes through two service-only RPCs. Clients cannot supply computed outputs. Raw service-role analysis changes are also rejected; only reviewed database functions can finalize. The worker credential is privileged and remains a trusted server boundary, not a cryptographically verified arithmetic service. Results and completed versions cannot be rewritten; calculation/request audit events are append-only. Saving a scenario does not change current lead MAO or approve an offer. Legacy writes to a bound lead's analysis are held, including moving it to an unbound lead.

`ACQUISITION_CALCULATOR_ENABLED=true` and an explicit server-only `ACQUISITION_CALCULATOR_SERVICE_KEY` are required in addition to acquisition activation. There is no fallback to the general service credential or user token. No credential or runtime flag was configured. The API reserves with the user JWT, invokes the worker for that exact ID, then reads the result again through current user RLS. A disabled/unavailable worker leaves pending input history and reports the hold. A timeout has an unknown outcome: retry the same ID, never create another reference automatically.

Worker read and completion each recheck the original creator's approved profile, active workspace/operator membership, live original session and activation. Revoked/expired original sessions leave requests held; after authorized review, a new session can submit a new revision with a new ID. No job reassignment or background scheduler is implemented. Schema-invalid inputs submitted directly through the reservation RPC produce an explicit invalid result; unsupported calculation versions are held rather than reinterpreted.

Compensation: disable calculator execution and acquisition activation, retain scenarios/jobs/audit, and correct calculation errors through a new version/revision. Do not reverse this migration by deleting history or replay old saves to select a lead MAO. Full-schema upgrade rehearsal and coordinated legacy UI/API cutover remain gates.

## Remaining lifecycle work

Internal amount proposal/approval history now links to exact analysis revisions; see OFFER-REVIEW.md. Current-scenario selection and final written-offer approval remain open. Property/comparable evidence, explicit uncertainty review, full offer history, seller-facing isolation and approval UI remain incomplete. Focused SQL tests validate persistence/security using synthetic result payloads; Python tests validate arithmetic and worker orchestration separately. This is not a complete PostgREST-to-production acceptance test. Production activation remains separately gated.
