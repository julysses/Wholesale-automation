This draft adds county review, human offer approval, lot handoff, land valuation and pinned-call workflows to the production baseline while preserving intake, consent, suppression and receipt protections. It also repairs land CSV imports that saved only five preview rows, makes manual land retries atomic with immutable receipts and owned review tasks, and fixes complete land-list visibility and failed-refresh handling.

The Facebook intake schema is already released in production. Do not reapply it. The new feature allowlist now contains **13 forward migrations**, including the manual land repair and `20261022170346_integration_csv_lead_intake.sql` for the main CSV database foundation. The latter is not yet connected to the application route or optional AI dispatch. Historical SMS installation and held-session recovery migrations remain excluded. Never apply the migration directory wholesale.

The candidate includes production commit `a89815126d9a98ced016167d8e383641d133135f`, including its native queue recovery and competing-insert tests. Both candidate deployment blocks are retained.

Validation to date:
- Backend: 1,290 passed, 10 skipped.
- Frontend: 254 passed across 53 files with four workers; typecheck/build and lint gate pass, with 143 existing findings.
- Pipeline/disposable SQL: 231 passed.
- Fresh production metadata matches the restored baseline plus the released Facebook delta, including 17 view security/grant sets. Thirteen-migration apply, injected failure rollback and historical preservation pass.
- Ten connected API/PostgreSQL intake journeys pass across Hilltop, Jays and native Facebook, including receipt/reply/STOP/no-replay behavior with providers stubbed.
- Actual overlapping PostgreSQL sessions verify offer, trace-budget, scoring, lot, valuation, pinned-call/SMS and manual-import claims. Eight manual-import sessions create one property and one task; retries preserve existing DNC and completed work.
- Main CSV database checks verify 24 normalization cases, configured ownership and due tasks, 501-row task creation, lookup beyond 1,000 existing records, immutable retry, preservation of worked/DNC/history/completed tasks and eight overlapping manual imports creating one property/task. This is a database foundation, not connected main-CSV acceptance.
- Nine new land-list cases cover the API row cap, 1,003 synthetic records, complete totals, bounded card rendering, search/filter, import cache refresh and read-failure recovery.

**Keep this PR draft. It is not approved to merge, deploy or activate.** Main-lead CSV API/UI integration and durable AI claim/result handling, buyer/Master List UI coverage, operator acceptance and exact release/recovery review remain open. Controlled live tests still require confirmed recipient/inbox details, Meta routing review and effective Vercel flag verification. Database sending schedulers remain paused; no production migration, runtime deployment or provider message was performed by these checkpoints.

Tests use synthetic data and stub Auth/provider boundaries; component and SQL checks do not establish live carrier/handset delivery or a real-browser operator walkthrough. Commits skip remote CI and the integration branch is excluded from Vercel deployment.

Review:
- [Friday acceptance status](docs/integration/FRIDAY-ACCEPTANCE-STATUS.md)
- [Release boundary and rollback constraints](docs/integration/RELEASE-BOUNDARY.md)
- [Current upgrade rehearsal](docs/integration/FRIDAY-UPGRADE-REHEARSAL.md)
- [Manual import repair and evidence](docs/integration/MANUAL-LAND-IMPORT.md)
- [Main CSV database foundation and remaining work](docs/integration/CSV-LEAD-TRANSACTION.md)
- [Complete land-list visibility](docs/integration/LAND-LIST-COMPLETENESS.md)
- [Explicit migration order](docs/integration/forward-migration-order.json)

