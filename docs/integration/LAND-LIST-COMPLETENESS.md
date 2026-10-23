# Complete land import visibility — October 22

Status: verified candidate; no production deployment or schema change.

The land cards and funnel used separate single-page responses. A configured API
cap could hide imported records, understate funnel counts, and turn read failures
into apparent empty states. The import receipt refreshed the card query but left
the separate funnel cache stale. The comping map also included dead records when
another eligible record made the section visible.

The land page now reads every page into one checked result, with an exact count
and deterministic created_at/id order. It advances by the actual response length,
including smaller configured row caps. Changing counts, duplicate/missing identities,
range-ignoring responses and incomplete reads fail before partial data can replace
confirmed data. The count is checked on each page; duplicate identities stop the
read immediately rather than permitting an unbounded range loop. This is checked
client pagination, not a transactional database snapshot across all HTTP requests.

Cards, funnel totals, search and status/workflow filters share this complete query.
Only 25 cards render at once; Previous/Next, search and status controls navigate all
loaded records. Vetting and comping are paginated too, and dead records stay out of
comping. A CSV receipt invalidates the shared query so cards and totals refresh
together. The original 30-second visible-page refresh interval is retained.

A failed initial read shows an error and unavailable totals, with no false empty
workflow. A failed refresh keeps the previous complete result, marks it as last
confirmed and offers explicit retry. A verified zero-count read still shows the
normal empty state. The independently queried buyer hub remains available.

Nine regression cases in `frontend/tests/land-list-completeness.test.tsx` cover:

- A 1,003-record dataset beyond the API cap, stable paging, total counts, 25-card
  navigation, search and status filtering for late records.
- Later-page errors without false empty/zero results in the main, vetting or comping tabs.
- Prior complete data surviving failed refresh and being replaced only by complete retry.
- Unconfirmed counts, changing counts and duplicate identities failing closed.
- A known empty result behaving normally.
- Confirmed import receipt immediately refreshing both list and funnel.
- Dead-record exclusion from comping.
- Immediate termination when responses repeat identities instead of honoring ranges.

Seven of the initial eight tests failed before repair; the verified-empty control
passed. The ninth separately reproduced a repeated-range read before the early
identity guard. All 254 frontend tests across 53 files now pass with maxWorkers=4.
Typecheck/build and the lint gate pass (143 existing findings); the existing chunk
size warnings remain. No test assertion or timeout was weakened. Relevant API/SQL
and pipeline code is unchanged from the previous verified checkpoint, so unrelated
backend/database/provider suites were not repeated for this frontend-only change.

Evidence: `land-list-completeness-result.json`; local ignored logs
`logs/friday-land-list-reproduction.log`, `friday-land-list-range-reproduction.log`,
`friday-land-list-frontend.log`, `friday-land-list-build.log`, and
`friday-land-list-lint.log`. Reproduce:

```sh
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend test -- --maxWorkers=4
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend run build
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend run lint:check
```

A read-only production aggregate currently reports zero land records. The volume
and failure-path checks above use synthetic responses; they are not production
imports or a signed-in operator walkthrough. The main-lead CSV ownership/task and
concurrency work, buyer/Master List UI coverage, operator acceptance and live gates
remain open.
