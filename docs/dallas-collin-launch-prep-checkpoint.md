# Dallas/Collin launch preparation checkpoint — October 12, 2026

Preserved work-in-progress branch: `codex/dallas-collin-launch-prep`. No deployment is authorized by this checkpoint.

## Included work

- Private intake migration, strict JSON contract and scoped authenticated Edge ingress.
- Eight disabled source configurations, review/audit operations, conservative CRM identity resolution, heartbeat and generated digest.
- Admin FastAPI endpoints and Daily Lists screen with source settings, receipts and paginated evidence review.
- Human-entered offer drafts replace AI-generated prices on the modified API path; retired duplicate Edge pricing endpoint.
- Pipeline contract/PGlite/Edge-handler test sources and synthetic fixture.
- Target PRD and acceptance requirements in `wholesaleos-daily-list-ingestion-prd.md`.

## Rehearsal database reconciliation

Production: `dvzhzlipbwzzcliujzyz`. Rehearsal: `tbhwxgfzbiaqjurghntj`.

Only rehearsal was modified in this implementation session. `daily_list_ingestion` succeeded. The large combined `list_operations` request failed twice with expired request state; absence was checked before retrying in smaller pieces. `list_operations_setup`, `list_pipeline_snapshot`, and `configure_list_source` then succeeded as separate migration entries. The call applying `resolve_list_record` and `scan_list_pipeline` was interrupted: inspect actual function definitions and migration history before retrying. Do not assume either success or failure.

Local combined file `20261012174446_list_operations.sql` therefore does not map one-to-one to rehearsal migration entries. Reconcile SQL content before applying; never blindly replay all repository migrations. No production deployment/migration was performed for these changes.

## Verification and limitations

- Prior local pipeline run: 15 Node tests passed, including isolated PGlite schema and role checks.
- Existing backend baseline: 629 passed; one environment-related HTTPX SOCKS dependency failure. Local socksio installation was started; verify environment before rerunning.
- Frontend npm ci completed. A build/lint run was started but its result was not captured in the prior turn; do not claim it passed.
- No complete ingress success/concurrency or end-to-end list-to-outreach acceptance has been established.
- Sources are disabled. Restricted ingress login, collector delivery, secrets and scheduling are unverified.
- Current normalization intentionally requires reviewed county/property evidence. It is not unattended matching.
- Digest generation is not owner delivery. Full blocked-source task coverage, delivery acknowledgement, worker scheduling and alerts need final testing/completion.
- Downstream skip tracing, capped provider integration, validated Claude scoring, underwriting and existing queue dispatch integration remain unfinished.
- Audit other agents/offer paths for price generation. The modified draft UI/API does not establish complete platform-wide offer approval.
- Buyer ranking integration/exclusions and wider launch acceptance remain open.
- The actual McKinney collection contains unresolved personal/property data and is deliberately excluded from this commit. Only synthetic fixtures are included.

## Resume

Inspect the working tree, this commit and rehearsal state first. Finish missing integrations against the target PRD; run backend/frontend/build/lint and meaningful SQL/HTTP/concurrency/recovery tests. Preserve existing consent and live recipient gates. Prepare a draft PR/reviewable release. Do not deploy or contact sellers without separate authorization.

## Recovered October 12 in local Codex

Archive c9a7cbc verified and restored to separate worktree `work/wholesale-launch-prep` under the September 28 task. Exact original commit pushed to origin/codex/dallas-collin-launch-prep. Source-recovery blocker resolved. See `dallas-collin-release-evidence.md` for FR-1 through FR-15 evidence and open work.

Rehearsal reconciliation: resolve_list_record exists (original history20261012181414); scan_list_pipeline absent. Added batch completeness/expiry guard after matching original remote function body to archive source. Guard applied in rehearsal only as20261012202141 (source20261012201949). Zero rollback QA fixtures retained. Production unchanged by this work.

Fixed five new lint regressions, patched Ajv, added pipeline CI and SQL/HTTP guard tests. Follow the release-evidence next step; do not mistake these tests for downstream implementation or launch acceptance.

## Monitoring and receipt retention — October 12 continuation

Previous implementation turn made progress (recovered branch, guard fix, tests and draft PR20). This continuation keeps the full launch goal active.

- Added service-only scan_at plus scan_list_pipeline. Missing/incomplete deliveries alert at the inclusive deadline; blocked/partial/failed and property-review outcomes create one incident/task per source/day. Retry/recovery reuses task identity, records resolved incidents, and retains tasks for operator acknowledgement. Up to seven missed schedule days recovered after procedure approval. Central DST tests verify UTC offset changes; outages beyond this recovery window remain a manual audit gate.
- Digest snapshot includes all eight sources (including disabled/not-received), latest receipts, counts, open incidents and the latest evaluation per lead ranked top ten. Generation still does not mean email delivery. Scoring validity/freshness remains a downstream gate.
- Retention now removes raw payload content and staged records after expiry but retains receipt hashes/counts and normalized provenance. Expired ingress runs return410 rather than accept another batch. Complete ingress success/concurrent replay and live expiry-path acceptance remain unverified.
- Source migration20261012205453_list_monitor_receipts.sql applied ONLY to rehearsal. Original combined tool request expired; readback proved no changes before splitting. Applied histories:20261012210041/list_monitor_receipts_setup and20261012210141/list_monitor_receipts_functions. Do not replay setup or combined historical operations migrations.
- Local pipeline22tests passed. Added monitor deadline/dedup/recovery, unavailable-owner recovery, status handling, DST, ranking and retention/provenance SQL tests. Real rehearsal rollback proof tests/sql/list_monitor_receipts.sql passed. Independent verification: sourcesenabled0, incidents0, fixtures0; anon/authenticated functions denied. No providers contacted.
- Deno2.9.6 installed temporarily via npm cache; real Edge handler typecheck caught JSONValue incompatibility, corrected. Edge test passed; added pinned Deno CI step. This proves rejection paths only, not successful database ingestion.
- Security advisors:11 no-policy informational findings (new monitor table intentionally service-only), unchanged3 definer warnings and Auth password/MFA warnings. Remediation https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy . No browser policies added to silence service-only findings.
- Next: durable owner-digest delivery and provider acknowledgements/uncertain-send recovery; worker secret/schedule acceptance; then downstream tracing/compliance/scoring/lot-routing, platform-wide human offer safeguards and buyer ranking. Production and all real outreach remain unchanged. Full launch not certified.

CI follow-up: monitoring commit dc416df passed full CI38308344870. Frozen Deno lock introduced in ab68563; CI38308500040 exposed a working-directory mismatch (pipeline package.json workspace metadata versus root-generated lock). Reproduced exact failure locally. Corrected only the Edge step to run from repository root, matching the successfully tested frozen-lock command. Final corrected commit CI must be checked before declaring it green.

## Durable owner digest — October 12 continuation

Previous monitoring turn made verified progress; final corrected CI38308635987 passed at d3d12b2. This turn implements owner-only digest delivery while retaining the full launch objective.

- tools/list_digest.py reserves immutable report/recipient/message identity and uses the existing EmailClient claim/suppression/allowlist gates. Date-derived UUID prevents new retry IDs. No send before07:00 Central or when LIST_DIGEST_ENABLED=false (default). Worker calls it after scan; busy scan exits without delivery. Admin scan remains read/processing-only with respect to email.
- Reserve/reconcile SQL distinguishes provider acceptance from matching delivered events. Uncertain attempts cannot resend; adverse events remain review even with a delivered event. Missing delivery after07:30 produces one assigned task; late delivery is explicitly not on-time. Missing recipient still reconciles alerts. Delivery snapshots remain frozen while new scan summaries refresh.
- Migration source20261012210944_list_digest_delivery.sql applied only to rehearsal as20261012211339/list_digest_delivery. Real SQL rollback proof passed. Synthetic ledger events are not live signed provider receipts. Verification: digestrows0/syntheticemails0/sourcesenabled0; anon/authenticated functions denied. Advisor categories/counts unchanged.
- Pipeline25tests passed; backend652passed before adding two additional route-level regressions (busy scan and uncertain delivery503). Focused final test result and CI must be checked. Existing datetime warnings remain. No real emails/calls/texts or production settings changed.
- docs/daily-digest-activation.md contains the exact scheduling/activation/acceptance plan. Five-minute cron is proposed but not installed. Vercel team metadata did not expose plan; supported scheduler/secret and actual timed delivery still unverified. Do not assume Supabase Pro covers Vercel cron requirements. Independent missing-worker monitoring remains required.
- Next independent implementation: remove remaining automated offer-price paths with consumer tests, then list enrichment/scoring/compliance/underwriting and buyer-ranking work. Digest live provider/scheduler acceptance and all earlier operator/business/provider launch gates remain open.
