This draft adds county review, human offer approval, lot handoff, land valuation and pinned-call workflows to the production baseline while preserving intake, consent, suppression and receipt protections. It also repairs land imports that saved only five preview rows, restores complete land-list visibility, and connects main CSV intake to atomic owner/task creation and durable scoring claims.

Main CSV uploads now use verified operator identity, immutable import receipts and a configured approved intake owner with due tasks. Exact retries and overlapping manual uploads preserve existing work and avoid duplicate properties/tasks. Default free rules scoring runs inside the data transaction. Optional AI uses durable 25-lead batches committed before model calls, immutable batch results, disabled SDK retries and uncertain/stale-result holds. Original upload replay cannot advance paid batches; a separate progress/continuation endpoint and operator panel support single/all remaining scoring and pause without replay. The three import screens validate request identity and support stable explicit retries; Master List no longer starts separate global background scoring after saving.

The Facebook intake schema is already released in production. Do not reapply it. The feature allowlist contains **13 forward migrations**, including the manual land repair and the expanded, still-unreleased `20261022170346_integration_csv_lead_intake.sql`. Schema must precede matching runtime; the new CSV API fails closed if its RPCs are unavailable. Historical SMS installation and held-session recovery migrations remain excluded. Never apply the migration directory wholesale.

The candidate includes production commit `a89815126d9a98ced016167d8e383641d133135f`, including native queue recovery and competing-insert tests. Both candidate deployment blocks are retained.

Validation to date:

- Backend: 1,334 passed, 10 skipped; frontend: 274 tests across 56 files passed. Typecheck/build and lint gate pass, with 143 existing findings. Pipeline source is unchanged from its prior 231-test checkpoint.
- The October 22 production metadata capture matches the restored baseline plus the released Facebook delta, including 17 view security/grant sets. Thirteen-migration apply, full/injected failure rollback and historical preservation pass.
- Ten connected API/PostgreSQL intake journeys pass across Hilltop, Jays and native Facebook with Auth/providers stubbed (final timing recorded in the upgrade result).
- Main CSV real-SQL checks cover 24 normalization cases, configured ownership/due tasks, 501-row task creation, lookup beyond 1,000 existing records, immutable retry, history/DNC/completed-task preservation and eight overlapping uploads creating one property/task.
- Connected CSV API/scoring checks prove commit-then-lost-response recovery at data/claim/result boundaries, timeout no-repeat behavior, invalid/stale result holds, eight contending scoring claims with one dispatch winner and eight exact finish replays. Actual provider calls: zero.
- Multi-batch checks complete 60 leads as 25/25/10, retain earlier scores after an unknown later batch, recover a lost finish acknowledgment without repeating IDs and deny another approved actor access. Read-only progress starts no model.
- Component checks prove exact explicit retries, wrong-reference refusal, all-row import, saved-data vs scoring-review outcomes stable Master List identity across SPA remounts, single/all remaining scoring, pause, stopped advancement after uncertainty and full-body transport limits.
- Existing offer, trace-budget, scoring, lot, valuation and pinned-call/SMS contention checks pass. Nine land-list cases cover row caps, 1,003 synthetic records, complete totals, bounded rendering, filters and failed-refresh recovery.

**Keep this PR draft. It is not approved to merge, deploy or activate.** Real-provider latency/maximum database volume, buyer UI coverage, signed-in operator acceptance, dependency/security review and exact release/recovery review remain open. Controlled live tests still require confirmed recipient/inbox details, Meta routing and effective sending-flag verification. Broad sending schedules remain paused; these checkpoints performed no production migration, deployment or provider message.

Synthetic/local checks do not establish production Auth/JWT behavior, carrier/handset delivery, production-volume locks or a real-browser operator walkthrough. Commits skip remote CI and candidate branches are excluded from Vercel deployment.

Review:

- [Friday acceptance status](docs/integration/FRIDAY-ACCEPTANCE-STATUS.md)
- [Release boundary and rollback constraints](docs/integration/RELEASE-BOUNDARY.md)
- [Current upgrade rehearsal](docs/integration/FRIDAY-UPGRADE-REHEARSAL.md)
- [Durable AI batch recovery and runtime evidence](docs/integration/CSV-BATCH-RECOVERY.md)
- [Connected main CSV and remaining work](docs/integration/CSV-LEAD-TRANSACTION.md)
- [Manual land import repair](docs/integration/MANUAL-LAND-IMPORT.md)
- [Complete land-list visibility](docs/integration/LAND-LIST-COMPLETENESS.md)
- [Explicit migration order](docs/integration/forward-migration-order.json)
