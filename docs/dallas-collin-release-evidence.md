# Dallas/Collin release evidence — October 12, 2026

Status: **draft; not production-ready**. Original archive commit c9a7cbcf30076719e3f88a496dec240595e4d366 restored using its Git bundle. All 23 SHA-256 file checksums matched. Branch pushed to GitHub. Separate worktree preserves prior checkout and unrelated files.

## Current continuation status

The early counts and open-step notes below are historical. The checkpoint is authoritative for later evidence. As of the tracing-ledger continuation:

- Full CI38318215054 passed forca8f0f5. Actual Deno ingress success, overlapping duplicate requests, replay/conflict/expiry and restricted-role checks passed against local PostgreSQL/TLS.
- Human offer review includes UI, paginated audit history, expiry checks and actual simultaneous PostgreSQL decision tests. Signed-in browser/deployed acceptance and offer dispatch enforcement remain open.
- Retell requests now pin and preserve agent identity/version; provider acknowledgements, callbacks and polling validate it. Live agent review and controlled provider acceptance remain open.
- FR9 now has tested atomic reservations/settlement/unknown holds and actual concurrent budget cap proof. Current input snapshots, default-disabled provider interface and atomic validated contact/billing receipts are implemented. Commercial adapter, authenticated provider evidence, worker wiring and operator recovery remain incomplete; no tracing enabled.

## Verified this session

- Existing backend suite: 630 passed. Ten added HTTP regressions cover approved-admin list controls, missing/invalid worker secrets, human-only price input and invalid prices. Final combined result recorded in checkpoint.
- Frontend: production build and 140 tests / 32 files passed. No new lint findings after fixing five recovered Edge-source findings; 148 baseline findings remain. Local frontend dependencies reused from the existing checkout because its package/lock versions match; clean CI remains the authoritative fresh install check.
- Pipeline: 16 tests passed. Original 15 plus a complete operations SQL integration test against isolated PGlite. Covers incomplete and expired batch rejection without lead writes, successful review, repeat review without duplicates, provenance, disabled channel sequences and authenticated-role denial.
- Ajv pinned consistently to 8.20.0 in Edge import and pipeline lockfile; npm audit reports zero pipeline vulnerabilities. Added pipeline test/audit CI job. Edge Deno handler test was not executed locally: Deno is unavailable. Node tests do not establish Edge runtime acceptance.
- Rehearsal resolve_list_record original function body matched recovered source MD5 0614d48ce17036416e55727dfdbd9fd4 before replacement. New local migration 20261012201949_list_review_batch_guard.sql applied ONLY to tbhwxgfzbiaqjurghntj as history 20261012202141/list_review_batch_guard. Rollback-only real-database incomplete-batch proof passed; zero retained fixtures; anon/authenticated execution denied, service_role permitted. Complete/expired/replay paths tested locally in PGlite, not all repeated remotely.
- No production migration, production promotion, seller contact, tracing purchase or ad launch performed. A pushed branch may trigger a Vercel preview; that is not a production release.

## Functional requirements

| Requirement | Current evidence | Remaining acceptance |
|---|---|---|
| FR-1 Source settings | Disabled seeds, admin HTTP denial tests, DB foreclosure constraints | Admin UI save/recovery, schedule/threshold configuration |
| FR-2 Source status | Contract enum/coverage tests | Actual collector delivery and per-source failure handling |
| FR-3 Strict contract | Actual Deno handler and restricted-role PostgreSQL/TLS acceptance | Deployed Edge endpoint and collector credentials |
| FR-4 Idempotency | Actual handler replay/conflict/lost ACK and two overlapping database sessions | Deployed endpoint/collector acceptance |
| FR-5 Retention | Raw-content purge retains receipt hashes and normalized provenance; local and rehearsal SQL proofs | Scheduled execution and full Edge expiry/replay acceptance |
| FR-6 Property identity | County/unit aliases and one reviewed-record replay | Parcel enrichment, conflicting aliases, legacy matching and full dedup matrix |
| FR-7 Windows | Foreclosure 31-day rejection | All inclusive boundaries, future dates and source-specific semantics |
| FR-8 Blocked sources | Local and rehearsal blocked incidents reuse assigned task identity | External alert delivery and operational acceptance |
| FR-9 Tracing | Atomic ledger, replay, cancellation, confirmed settlement, unknown holds; true concurrent cap test | Adapter integration, current input/contact checks, authenticated provider evidence and operator recovery |
| FR-10 Compliance | Existing backend suite remains green; seeds disabled | List-specific DNC freshness, consent, opt-out, quiet-hours and dispatch caps |
| FR-11 Scoring | Existing scoring preserved | Validated list scoring, stored reasons/version/input hash, stale input rejection |
| FR-12 Lot routing | Existing underwriting preserved | Verified list-to-underwriting handoff and acknowledgement |
| FR-13 Digest | Immutable delivery reservation, deterministic email ID, matching-event reconciliation and deadline tasks tested locally and in rehearsal; summary counts/top ten retained | Validated scoring, controlled live email receipt, scheduler and actual owner delivery by07:30 Central |
| FR-14 Heartbeat | Rehearsal scan installed; local deadline, DST, missing/partial/failure and retry tests pass | Scheduler execution, delivered alerts, outages exceeding seven-day backfill |
| FR-15 Provenance | Review creates source observation; local SQL assertion | End-to-end normalized signals and retention acceptance |

## Other release blockers

- Remaining automatic price behavior found in agents/qualification_agent.py (asking-price-derived range) and agents/negotiation_intelligence_agent.py (target offer). Human-only generate-offer endpoint tests do not establish platform-wide compliance. Audit orchestrator/API consumers before changing these contracts.
- Buyer top-three ranking and wholesaler exclusions/outcome tracking are not complete.
- Ingress restricted credentials, scoped collector delivery and existing external GPT schedules are unverified. Do not create duplicates. Sources remain disabled.
- The original combined list_operations migration is partially applied under split names in rehearsal. scan_list_pipeline remains absent; never replay the combined file blindly. Production has none of the new pipeline migrations.
- Retell verification/call/callback, STOP/refusal, secondary-email unsubscribe, Meta consent, restore, delivered monitoring, legal/title/offer approval, staffing and go/no-go remain open.
- Five supervised foreclosure runs and 14-day unattended acceptance have not occurred. The 141 McKinney candidates remain unresolved and were not imported.

## Next implementation step

Finish the scan/heartbeat and retention design with integration tests before installing its missing rehearsal RPC. In parallel within the same implementation sequence, remove remaining automated offer-price generation with consumer tests; then implement the gated downstream pipeline. Preserve existing intake and provider restrictions. This checklist documents work remaining, not approval to enable outreach.

Final local backend result: **640 passed**, 352 existing datetime deprecation warnings. Rehearsal security advisors: 10 no-policy informational findings (including the two service-only private operations tables); 3 existing authenticated definer-function warnings; leaked-password protection and MFA options remain configuration warnings. No guard-function privilege finding. Track remediation: https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable and https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection . Do not grant browser access just to silence intentionally service-only table findings.

Latest continuation supersedes earlier missing-scan/Deno notes: monitor installed in rehearsal under split history entries; 22 pipeline tests and Deno Edge rejection/typecheck passed. See checkpoint for exact mappings. Nothing promoted to production.

Digest continuation: owner-only delivery code now present (default disabled);25pipeline tests and rehearsal rollback proof passed. No actual provider send or scheduled delivery has been accepted. See daily-digest-activation.md.


### October 12 offer-safety follow-up
Qualification ranges, deal-analysis ranges and negotiation midpoint pricing have been removed from their generators. Acquisition cards suppress historical generated price cards and identify saved prose as unapproved historical material. New regression tests cover model-injected offer prose and historical UI data. Full human approval/dispatch enforcement remains an open gate; this is not a go-live approval. See the latest checkpoint for exact validation and next steps.


### October 12 durable human offer review
Private append-only offer events, immutable term revisions, expected-version approval/revocation and admin-only API implemented and verified in rehearsal. Real rollback leaves zero records. Operator UI, real concurrency/expiry acceptance and any offer dispatch integration remain open; this foundation does not certify end-to-end offer approval or launch.
