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
