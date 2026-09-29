# Lead & Buyer Scoring Audit (2026-09-29)

## Findings (before)

| # | Area | Problem | Impact |
|---|------|---------|--------|
| 1 | Lead scoring | Every lead was scored by Claude Haiku from **address + name + source only** (5 leads/call, 25/request, driven by a browser loop). Equity, ARV, ask, beds/sqft/year, phones, DNC, stack count were never sent on the main path. | ~17k leads = ~700 paid calls and ~10+ min; scores were guesses; non-reproducible; a closed tab stalled the run. |
| 2 | Import | `import-master-list` with scoring on made all Claude calls serially inside **one HTTP request**. | Timeouts on large lists. |
| 3 | Re-score | `rescore_existing=true` re-read the same first page forever (no cursor). | Infinite loop / repeated paid calls. |
| 4 | Lists | No link between a lead/buyer and the upload it came from; only one-at-a-time delete. CORS also blocked `DELETE`. | Cannot remove a bad list; must hand-clean the CRM. |
| 5 | Buyer score | Institutional = avg price > $500k AND > 10 deals (wrong: SFR operators buy at $150-450k). Frequency cap 12/yr and volume cap 20 flatten real volume buyers. No credit for proof of funds or close speed. `engagement_delta` unbounded. | Big buyers mis-tagged and under-ranked. |
| 6 | Buyer pipeline | Scoring not run after import; `buyers` and `buyer_transactions` read un-paginated (PostgREST 1000 cap, huge `in` URL); O(buyers x transactions) matching loop. | Truncated scores on large books; slow imports. |

## What changed

* `tools/lead_scoring_engine.py` - deterministic engine, same 5 x (1-3) factors and HOT >= 13 / WARM >= 8 tiers so nothing downstream changes.
  * Motivation: stacked distress (probate, pre-foreclosure, tax, code, vacant, absentee, life event) + multi-list stack count.
  * Timeline: hard clocks (foreclosure/probate/tax) and urgency language; long-worked leads step down.
  * Equity: stated % or (ARV - loan)/ARV; 30%+ needed to leave room for an assignment fee.
  * Condition = **exit-ability to large buyers**: SFR only, 3+ bd, 900-3,200 sf, built 1960+, $90-450k. Wrong product type (mobile, land, multi-unit, condo) caps the score.
  * Flexibility: ask vs. 70% of ARV, reachability (phones/email), DNC never auto-routes to calling.
  * 20k leads score in well under a second; every score has human-readable reasons + next action.
* `POST /api/ai/score-unscored-leads` and import default to `engine="rules"` (1000 leads/request, bulk upserts of 500). `engine="ai"` remains for optional narrative enrichment. Re-score uses keyset pagination. The UI runs it automatically after every import.
* Lists: `lead_lists` + `leads.list_id`, `buyers.import_log_id` (migration `20260929030000`). `GET /api/lead-lists`, `DELETE /api/lead-lists/{id}` (keeps already-worked leads unless `include_worked=true`), `POST /api/lead-lists/{id}/rescore`, `GET/DELETE /api/buyers/imports[/{id}]` (deletes only buyers that upload created). "Manage Lists" modal on the Leads page; CSV imports register a list.
* Buyer engine: concave frequency/volume curves (24/yr, 50 lifetime), +10 readiness bonus (POF, <=14-day close), engagement clamp +/-30, institutional by volume or known SFR operator names. Auto-scoring after import; paginated/chunked loading; indexed transaction matching.

## Deploy checklist

1. Apply `frontend/supabase/migrations/20260929030000_lead_lists_and_buyer_import_tracking.sql` **before** deploying the API (the API selects/writes `list_id` / `import_log_id`).
2. Deploy API, then frontend.
3. Existing leads have no list; they stay put. Existing AI-scored leads keep their scores until "Re-score".

## Recommended next steps (not done)

* Feed real signals into the engine: PropStream/BatchData equity, lien and owner-occupancy fields into `leads` columns rather than free-text tags.
* Backtest weights against closed deals; add `score_version` + `scored_by` columns to leads so rules vs. AI scores are distinguishable.
* Add buyer buy-box match to lead score (does a proven buyer actually buy this zip/price?) using `match_buyers_to_deal` counts.
* Move Claude to a "why this lead" narrative on HOT leads only.
* Frontend toolchain could not be installed in the review sandbox (xlsx CDN 403), so the TypeScript/vitest changes were not executed - run `npm test` and `npm run build` in CI before merging.
