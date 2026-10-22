# Buyer visibility and record-specific purchase history

October 22, 2026. Candidate-only fixes; no production writes, provider calls,
new migrations or schedule/flag changes. PR #21 remains a draft.

## Changes

The buyer leaderboard previously limited its query to 500 rows and presented the
returned length as the active-buyer total. Standard buyers and land buyers also
relied on a single server response. These three screens now read all pages with
stable ordering, exact counts and unique record identities before replacing
confirmed data. Changed counts, repeated IDs, missing count evidence and partial
reads fail visibly. These checks detect incomplete reads; they do not provide a
single database snapshot across concurrent page requests.

Each screen renders 25 records per page. Search and filters apply to the complete
confirmed set, with literal search input. Refresh failures preserve the previous
confirmed records with an error and explicit retry. An initial failure cannot
appear as a verified empty list or zero KPI. Land buyers with no recognized
category are visible under “Needs category review”.

The buyer editor now exposes active status, land/infill preferences and land buyer
category using existing database columns. Unrelated edits preserve nullable flags;
only explicit changes set them. This does not grant SMS/email consent.

Purchase history uses a buyer-specific query and cancellation signal. The response
must identify that buyer, contain only that buyer's rows, have unique IDs and match
its stated total. Late responses cannot populate another buyer's drawer. Failed
refreshes retain only the same buyer's previously confirmed history. The backend
reads complete history and complete active buyers before matching a deal; the
single-buyer classifier also reads complete history before classification.

## Evidence

- 1,340 backend tests passed, 10 skipped; 289 frontend tests in 58 files passed.
- Typecheck/build passed. Lint gate passed with 143 existing findings and no new
  findings. Existing large-bundle warning remains.
- Focused component tests cover capped 1,003-record reads, bounded rendering,
  search beyond row 1,000, literal punctuation, uncategorized land buyers, failed
  refresh recovery, late buyer switching, invalid purchase evidence, history
  pagination and nullable preference preservation/explicit edits.
- The disposable PostgreSQL rehearsal restored the saved production schema and
  applied the same thirteen forward migrations. A new connected check inserts
  1,003 synthetic buyers and 1,003 purchase records with a forced 200-row response
  cap. All history is returned, the best match beyond row 1,000 wins, and deactivation
  excludes that buyer. Auth/provider delivery is not established by this check.
- Ignored logs: `logs/friday-buyer-{focused,backend,frontend,build,lint,upgrade}.log`.
  SQL proof: `pipeline/integration/verify_buyer_reads.py`, run by the full upgrade
  rehearsal. Existing intake-journey result is recorded separately by that runner.

## Remaining buyer and release work

This is complete-read and preference-edit coverage, not complete buyer acceptance.
Buyer CSV import still uses background persistence; atomic/idempotent import,
acknowledgment loss and durable import/classification/rescoring outcomes need review.
Manual buyer creation also needs duplicate/lost-response review. The outreach log's
100-row cap/error behavior and the separate API leaderboard endpoint are outside
this fix. Production-volume read latency/memory, signed-in browser workflow,
production Auth/JWT/tenancy behavior and buyer communication acceptance remain open.
Broad outbound schedules remain paused. Do not bypass DNC, replay held sessions or
send to the shared test number until its identity and fresh per-source scope are
verified. Live owner inbox and handset delivery/reply/STOP remain launch gates.
