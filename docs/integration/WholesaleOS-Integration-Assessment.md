# WholesaleOS branch integration assessment

Prepared October 20, 2026. Repository investigation only; no implementation or operational resumption.

**Recommendation: use `codex/retell-sms-production` as the eventual integration baseline and selectively port the collection branch’s missing feature bundles. Do not merge PR #20 wholesale or replay its migration directory.** Production already contains most of the county ingestion, tracing, scoring, and review foundation. The remaining differences include both valuable collection safeguards and older implementations that would undermine production intake and SMS protections if selected during reconciliation.

## Evidence and scope

| Item | Pinned evidence |
|---|---|
| Shared ancestor | `5c138f1afaaa37651682eff211bca2a56903a61c` |
| Collection branch | `8bec6d825071993d59bc623b346046c3f249fba2` |
| Production branch | `19c117ad7a8ab10656bf116a2a6835508f7f1f01` |
| Exclusive commits | Collection 134; production 96 |
| Changed paths since ancestor | Collection 311; production 292; union 431 |
| Paths changed on both branches | 172: **124 byte-identical at the tips; 48 divergent** |
| Migration files in changed-path union | 69: 30 identical shared, 1 divergent shared, 15 collection-only deltas, 23 production-only deltas |
| PR #20 | Open draft; head matches the collection SHA; targets `claude/ai-wholesaling-agency-KkDF1`, not the production branch |

Authenticated GitHub GETs verified the PR metadata and production branch head. Existing local Git objects matched both remote SHAs; all comparisons used those immutable objects. “Collection-only delta” means only that branch changed the file since the ancestor; it does not necessarily mean the file is absent from production. Divergent blobs are not a count of textual merge conflicts. No merge simulation or tests were executed.

Sources: [PR #20](https://github.com/julysses/Wholesale-automation/pull/20), [production checkpoint at reviewed SHA](https://github.com/julysses/Wholesale-automation/blob/19c117ad7a8ab10656bf116a2a6835508f7f1f01/docs/START-HERE-NEXT-CHAT.md), [collection checkpoint at reviewed SHA](https://github.com/julysses/Wholesale-automation/blob/8bec6d825071993d59bc623b346046c3f249fba2/docs/START-HERE-NEXT-CHAT.md).

The production checkpoint’s October 19 pause supersedes earlier activation and testing approvals. It reports both SMS schedulers disabled and migration `20261019213545_retell_empty_session_reconciliation.sql` pushed but **not applied**, with no corresponding production function. These are repository-recorded operational facts, not a fresh live inspection. Branch HEAD is also not proof of the deployed runtime: that checkpoint identifies runtime `7b406f5c44a39fd8eec67bb7801c1d32c0526ea5`.

This review performed no pull, checkout, merge, push, provider request, database query, migration application, worker invocation, test run, schedule change, or deployment. Only assessment artifacts were written in this task’s output directory. The explicit read-only brief takes precedence over the general instruction to pull/push after updates.

## File-level deliverables

- [Complete 431-path matrix](file-integration-matrix.csv): disposition, rationale, ancestor/tip blob IDs, file modes, and immutable source links.
- [All 48 divergent overlapping files](divergent-files.md): readable per-file disposition.
- [All 69 migration paths](migration-integration-matrix.csv): separate schema inventory.
- [Comparison snapshot](comparison-snapshot.json): exact revisions and counts.

The inventory is exhaustive for changed paths, but not a certification of every implementation. Shared identical files need no port; collection-only files remain candidates until their dependency bundle and future regression requirements are satisfied.

## Findings that block a direct integration

### 1. Duplicate SMS installation and competing function definitions — critical

Collection has four separate migrations:

| Collection file under `frontend/supabase/migrations/` | Collision / disposition |
|---|---|
| `20261015175138_retell_form_sms_queue.sql` | Creates `public.retell_form_sms_jobs`, its index and `claim_retell_form_sms`; replaces `claim_twilio_sms`. Production’s consolidated install already creates the queue. Exclude from production migration replay. |
| `20261015181957_retell_sms_scheduler.sql` | Creates `private.retell_sms_scheduler`, `private.tick_retell_sms`, and registers an inactive cron job. Production already has its own installation. Exclude; do not execute even though its initial flag is false. |
| `20261015184900_twilio_retell_reply_suppression.sql` | Replaces `public.record_twilio_event`; superseded by production’s installation and October 19 reply-task repair. Exclude old definition. |
| `20261015185153_twilio_reply_legacy_payloads.sql` | Another older replacement of `public.record_twilio_event`. Exclude old definition. |

Production’s `20261015192903_retell_form_sms_production.sql` creates the same queue and scheduler objects and installs receipt handling. A combined historical migration chain would attempt duplicate `CREATE TABLE` operations; simply adding `IF NOT EXISTS` would hide rather than resolve differences in constraints, claims and permissions.

Collection’s queue claims use `twilio-sms:` phone locks; production’s later native/app claims and receipt handling use `seller-outreach:` and shared recipient-limit checks. Reintroducing an older claim can break cross-channel serialization and bypass newer transport/scoping behavior. This is a semantic hazard even if an edited migration executes successfully.

Preserve production’s progression: reviewed resubscription, unclassified-DNC preservation, scoped native claims, immutable transport ownership, app outbox, recovery, automatic queue, intake handoff, and the October 19 reply notification function. Do not mix old queue definitions with newer application workers.

Evidence: [collection queue](https://github.com/julysses/Wholesale-automation/blob/8bec6d825071993d59bc623b346046c3f249fba2/frontend/supabase/migrations/20261015175138_retell_form_sms_queue.sql), [production consolidated installation](https://github.com/julysses/Wholesale-automation/blob/19c117ad7a8ab10656bf116a2a6835508f7f1f01/frontend/supabase/migrations/20261015192903_retell_form_sms_production.sql), [production transport ownership](https://github.com/julysses/Wholesale-automation/blob/19c117ad7a8ab10656bf116a2a6835508f7f1f01/frontend/supabase/migrations/20261017012707_retell_app_transport_ownership.sql).

### 2. Same migration ID, different destructive behavior — critical

`frontend/supabase/migrations/20261015023121_weekly_tax_monitoring.sql` is the only shared migration whose tip contents differ. Collection’s `wholesale_ingest.scan_at` deletes expired `records` and `contacts` and nulls expired raw payloads. Production removed those actions so monitoring does not delete intake evidence.

Keep production’s non-deleting definition. Editing the historical file does not repair an already-deployed function, and equal migration IDs do not establish equal deployed bodies. Future reconciliation must compare the deployed function, migration history and actual schema, then use a reviewed forward change only if needed.

Also preserve `20261016230511_protect_website_inquiry_retention.sql`: website receipts must not become disposable imported-list duplicates. DNC records remain permanent suppression evidence.

Evidence: [monitor migration, collection](https://github.com/julysses/Wholesale-automation/blob/8bec6d825071993d59bc623b346046c3f249fba2/frontend/supabase/migrations/20261015023121_weekly_tax_monitoring.sql), [monitor migration, production](https://github.com/julysses/Wholesale-automation/blob/19c117ad7a8ab10656bf116a2a6835508f7f1f01/frontend/supabase/migrations/20261015023121_weekly_tax_monitoring.sql).

### 3. Application compatibility depends on production SMS transport ownership — critical

| File / bundle | Preserve or reconcile |
|---|---|
| `tools/retell_form_sms.py` | Production’s `retell_native` versus `app_twilio` selection, immutable existing-job identity, next contact window, original expiry, exact-job drain, integer version and no transport fallback. |
| `tools/retell_reply_routing.py`, `tools/sms_controls.py` | Native redirect only for a unique eligible native conversation; controls and app-owned conversations cannot fall through. |
| `tools/retell_sms.py` | API-chat routing to its own archiver, exact saved-chat identity resolution, and wrong-number suppression. |
| `tools/retell_api_chat.py`, `retell_api_receipts.py`, `retell_api_turns.py`, `retell_api_inspect.py` | Preserve as production bundle. Version checks accept either `agent_version` or `version` only when all supplied aliases are exact integers matching the pin. |
| `tools/retell_app_dispatch.py`, `retell_app_routing.py`, `retell_app_automatic.py`, `retell_app_test_scope.py`, `sms_reply_budget.py` | Preserve production ownership, finite scope, acknowledgment/reply claims, generation budget and recovery holds together with their migrations. |
| `tools/sms_client.py`, `schemas/outreach.py` | Preserve explicit blocked/failed/accepted/unknown outcomes and reason codes. An uncertain attempt is not an eligible retry. |
| `web/api/nurture_api.py` | Preserve secret-protected, exact job/turn workers, recovery and inspect APIs; importing the collection file would remove these endpoints. |

The reconciliation migration remains a separately reviewed, unapplied repair. Its presence in Git must not become permission to apply it, reconcile the held session, or replay the expired “Please call ASAP” turn.

### 4. Intake and receipt/notification order must survive — critical

`web/api/lead_forms_api.py` in production claims the owner notification before attempting Retell queueing and records `schedule_unconfirmed` when a queue write may have committed without a response. Collection queues first. Selecting that older code could prevent owner follow-up when queueing fails and lose the newer explicit SMS outcome reporting.

`web/api/twilio_webhooks.py` in production:

1. Authenticates and persists the carrier event through `record_twilio_event`.
2. Reconciles status callbacks against the exact outbound receipt, including app-owned jobs while sending is paused.
3. For inbound events, attempts the durable owner-email notification after the receipt/task/suppression transaction.
4. Queues an app-owned reply, or considers native redirect only when the app does not own the conversation.

Keep `tools/seller_reply_email.py`, `tools/twilio_receipts.py`, production `record_twilio_event`, and this ordering. Carrier receipt identity and STOP suppression must not depend on optional AI success. Persistence uncertainty returns retryable failure; deduplication must prevent repeated SMS, tasks or email.

Production’s `20261019195020_sms_reply_notification_handoff.sql` assigns reply tasks to an approved owner and makes them due immediately. The checkpoint reports deployment history version `20261019195321` for that same migration. Map that discrepancy before any future migration planning; do not apply both timestamps.

### 5. Collection has valuable missing safeguards — high

Keeping every production file wholesale would also discard useful work:

| Collection feature | Required files / schema | Integration decision |
|---|---|---|
| Human-entered offers and content-bound review | `web/api/offer_review_api.py`; offer components; `frontend/src/lib/offerReview.ts`; `web/api/__init__.py`; `frontend/src/hooks/useAIAgent.ts`; offer Edge functions; migrations `20261012213446`, `20261012222753`, `20261013035456` | Port as one reviewed contract. Production’s `/api/ai/generate-offer` currently generates model-priced options; collection requires a human price and returns `approval_required:true`, `sent:false`. Preserve production CSV import safeguards in the same API file. |
| Guarded draft outreach and suppression of inferred prices | `agents/{deal_analyzer,distress_scoring,negotiation_intelligence,qualification,seller_outreach}_agent.py`; `orchestrator/master_orchestrator.py`; `web/api/{__init__,marketing,webhooks}.py`; `frontend/supabase/functions/{generate-offer,write-outreach}/index.ts`; affected offer/deal UI | Reconcile across every entry point. Updating only one endpoint leaves alternate pricing paths. Preserve the collection restriction against treating inferred prices as approved contract terms. |
| Pinned call identity | `tools/retell_adapter.py`, `web/api/calls_api.py`, `config/settings.py`, `.env.example`, migration `20261012223527_retell_claim_identity.sql` | Atomic API/schema/ACL bundle. The migration revokes the old `claim_retell_call` RPC that production still uses. Porting only SQL breaks that path; porting only code calls a missing RPC. Keep calling disabled. |
| Call follow-up tasks | Collection hunks in `web/api/webhooks.py` and disposition aliases in `tools/retell_adapter.py` | Preserve callback/appointment/warm task intent and pending-task cancellation on opt-out; reconcile owner/due-date requirements with production. Do not reopen completed human work. |
| Lot handoff, receipt and reconciliation | `web/api/list_pipeline_api.py`, `tools/list_lot_worker.py`, `LotOperations.tsx`, `LotInbox.tsx`, `LotReconciliation.tsx`, `useLotAction.ts`, `lotWorkflow.ts`; migrations `20261012235926`, `20261013004341`, `20261013013234`, `20261013025354`, `20261013030331` | Port together, with `LIST_LOT_ROUTING_ENABLED` false. Handoff is not outreach permission. Reconcile `public.scan_list_pipeline` so lot monitoring preserves existing trace/scoring monitoring. |
| Land valuation evidence | `web/api/land_valuation_api.py`, `useLandValuation.ts`, `landValuation.ts`, `QuickCompCalculator.tsx`, `SevenMustsForm.tsx`, `LandLeads.tsx`; migrations `20261013031711`, `20261013033643` | Port with stale-snapshot/receipt checks and saved valuation radius. Preserve human-price boundaries downstream. |

All timestamp abbreviations in this table map to exact filenames in the migration matrix. “Port” is an eventual implementation recommendation, not approval to deploy or execute anything now.

### 6. County pipeline already shares substantial code; retain production improvements — high

The 124 identical shared paths include `daily-list-ingest` core/schema/coverage, most collectors and scoring/tracing tools, PropStream components, `useLeads.ts`, and 30 migrations. Preserve them once; no duplicate rollout is needed.

Keep production differences in:

- `pipeline/collectors/deliver.mjs`: delivery journal binds payload identity to endpoint/key ID and uses project-specific filenames. Old receipts must not be treated as proof of delivery to another environment.
- `pipeline/collectors/deliver_keychain.py`: source/environment-scoped credentials, explicit production selection, rehearsal default. Do not access the keychain or invoke delivery during this review.
- `pipeline/collectors/foreclosure_batch.mjs`: supported trustee case formats and conflict-aware street-suffix comparison; no guessed OCR correction.
- `pipeline/collectors/tax_roll.py`: zero-filled/missing situs remains unresolved; preserve raw source fields.
- `pipeline/collectors/dallas_notice_pages.mjs`: production-only capture support should remain.
- `20261016193454_county_intake_assignment.sql`: approved owner and durable review task created with property association.
- Production source-filter, tax-evidence, case-reference and address-suffix migrations: retain matched API/UI contracts.

No county record, ownership match or score establishes SMS consent. Website inquiries matching county properties retain their separate submission/consent history. PropStream stays operator-controlled under the existing cumulative $50 cap.

### 7. Frontend dependencies are behavioral, not package-version conflicts — high

No tip-to-tip differences were found in `frontend/package.json`, its lockfile, pipeline package/lock files, Deno lockfiles or the compared Python dependency manifests. Package equality does not prove runtime compatibility.

| Frontend file | Required reconciliation |
|---|---|
| `frontend/src/pages/Leads.tsx` | Keep production `/leads?lead=<uuid>` resolution independent of pagination, keyed drawers and server `/api/ai/import-master-list` reconciliation. Port collection manual contract-price entry and explicit follow-up-date validation without restoring direct browser bulk inserts. |
| `frontend/src/hooks/useNotifications.ts` + `components/layout/NotificationPanel.tsx` | Keep production `error`/`refresh` contract, SMS toasts, focus/reconnect/visible polling, stale-response protection and read-write checks. Collection’s hook lacks the newer panel contract. Also assess DELETE refresh semantics: collection subscribed to `*`; production uses INSERT/UPDATE plus polling. |
| `frontend/src/pages/DailyLists.tsx` + `components/lists/{ReviewControl,ForeclosureActions}.tsx` | Keep source filters, historical-tax warnings, zero-situs rejection, inline reviews and query invalidation; add lot controls only with APIs/RPCs. |
| `frontend/src/App.tsx` | Production puts Daily Lists within Layout; `DailyLists` still checks admin profile. Preserve server authorization too; route relocation alone is not evidence of unauthorized access. |
| `frontend/src/pages/SetupWizard.tsx`, `components/WorkflowGuide.tsx`, `hooks/useWorkflowStep.ts` | Preserve production operational checks and evidence-based wording while restoring collection’s guarded call/offer instructions where appropriate. A checked setup item must not imply dispatch authorization. |
| Offer/land components, `frontend/src/types/index.ts`, API hooks and parsers | Port matching request/response schemas, version/hash conflict handling and router registrations in `web/app.py`. UI-only imports would otherwise produce missing endpoints or incompatible payloads. |

The other import component, `frontend/src/components/leads/LeadImportModal.tsx`, is outside this changed-path set. A production checkout inspection still shows a direct insert path; protecting the updated `Leads.tsx` modal alone does not certify every intake route. Include this separate path in future acceptance.

### 8. Build/deployment coupling can turn integration into an unintended release — high

Preserve `vercel.json`’s `git.deploymentEnabled` exclusion for the older default branch. PR #20 targets that default branch; its destination is not an acceptable proxy for the paused production baseline. The checkpoint also reports linked Railway services auto-rebuilding when the default branch advanced. Deployment behavior must be reviewed before future pushes.

`.github/workflows/ci.yml` must retain production’s scoped-credential and SMS transport contention coverage while preserving collection offer/lot/valuation coverage. The shared `pipeline/integration/run_local.py` is identical, but `ingress-postgres.ts` differs: suite wiring and fixtures need reconciliation, not a branch-wide test-file replacement.

Production tracks `pipeline/node_modules` as an absolute symlink to a local checkout. This is a portability problem, not a package-version conflict. Exclude that machine-specific link in a future approved integration change and use the pinned manifests/lockfiles.

Never run collection `scripts/install_mac_collector.py`, `scripts/sql/enable_bulk_supervision.sql`, production `pipeline/operations/promote_*.sql`, or historical reconciliation scripts as routine setup. They perform operational changes.

## Required regression evidence after explicit resumption

**These are future acceptance requirements. None were executed for this assessment.** Start in an isolated disposable database and provider-stubbed environment. Existing historical passing counts in PR/checkpoint text are not evidence that an integrated result passes.

| ID | Required cases and pass condition | Primary coverage locations |
|---|---|---|
| R1 Intake durability | Both Hilltop and Jays form paths: durable submission, correct lead linkage, approved owner, due follow-up task and notification. Queue timeout cannot lose owner alert or trigger a fallback send. Retry cannot duplicate records or acknowledgment. Missing form/owner and committed-but-response-lost states remain visible and recoverable without outreach. | `tests/test_public_forms.py`, `tests/test_intake_notification_safety.py`, `tests/test_retell_form_sms.py`, `pipeline/tests/intake-handoff.test.mjs`, `production-onboarding.test.mjs` |
| R2 Consent integrity | Opted-out/absent consent stays no-send. Stale rendered disclosure fails; server captures authoritative disclosure hash/source/time. County imports, contact matching, or an operator checkbox cannot synthesize website SMS consent. Phone/property mismatch and uncertain suppression lookup fail closed. | `web/api/lead_forms_api.py`, `tools/sms_client.py`, existing form/Twilio suites |
| R3 Suppression | STOP variants, natural-language opt-out and wrong-number handling persist across phone aliases/leads and cancel/hold pending automation. START alone does not clear suppression. Reviewed resubscription requires matching later carrier START plus fresh matching form consent and operator review; null/unclassified DNC survives. A later callback cannot reactivate a suppressed lead. | `tests/test_twilio_integration.py`, `test_retell_sms.py`, `test_retell_reply_routing.py`, production resubscription/DNC SQL |
| R4 No duplicate cross-transport dispatch | Concurrent native/app/Twilio/call claims share appropriate phone serialization and recipient limits. App-owned jobs never enter native claims/redirect. Unavailable transport never falls back. Missing selected job/turn never becomes a broad drain. Accepted/processing/review/unknown and expired operations cannot be replayed. | `pipeline/integration/retell-app-concurrency.mjs`, `pipeline/tests/retell-scoped-claims.test.mjs`, transport/outbox suites |
| R5 Provider receipts | Reject forged/mismatched callback identity; preserve exact SID/reference/chat/lead/phone/agent bindings. Duplicate/out-of-order callbacks and callback-before-HTTP-response keep receipt evidence and terminal outcomes. Provider acceptance is separate from carrier delivery; API generation cannot masquerade as Twilio delivery. Receipt processing remains functional while sending flags are false. | `tools/twilio_receipts.py`, `web/api/twilio_webhooks.py`, `tools/retell_api_receipts.py`, Twilio/app-outbox tests |
| R6 Pause and expiry | All sending/automation flags false and schedulers inactive remain effective; no HTTP provider call occurs in disabled paths. Original receipt clocks, 9am–7pm Central window, DST boundaries and job/turn expiry are preserved. No extending old windows or replaying held input. Stub providers to prove zero attempted calls. | form SMS, app automatic/test-scope/dispatch suites |
| R7 Reply tasks and owner alerts | Persist receipt, suppression and task before optional routing. Approved owner and immediate due date survive retry. Email uses saved event and configured owner, atomic claim and exact lead link; unknown/accepted attempts cannot resend. STOP email does not clear DNC. Notification refresh failure preserves saved list; duplicate events do not repeat toasts or reset read state. | `pipeline/tests/sms-reply-notifications.test.mjs`, seller reply email tests, `frontend/tests/notifications.test.tsx`, deep-link tests |
| R8 Intake retention/import | Website inquiries and DNC history survive list dedupe, retention refresh and monitor runs. Existing CSV updates are confirmed; retries do not duplicate properties. Test every import component, not just the revised Leads modal. County merges cannot overwrite consent or an existing owner’s completed work. | `pipeline/tests/website-inquiry-retention.test.mjs`, master-list/import tests, both CSV UI paths |
| R9 County/trace/scoring | Incomplete/expired/replayed batch sets rejected; exact identity and current distress review required; tax snapshot is not current payoff. Wrong-environment journals rejected. Trace spend/cap/receipt gates retained; scoring cannot authorize contact; county association creates an owned task atomically. | collector, reviewed-identity, trace, scoring, onboarding suites |
| R10 New feature bundles | Lot handoff requires current evidence, eligible assignee and durable receipt; retries dedupe; changed evidence holds/reconciles. Offer approval binds displayed content, version and human price; no inferred contract price or automatic sending. Valuation preserves snapshot/radius; stale saves fail. Calls require pinned agent/sender/version and claim identity. | collection offer/lot/valuation/concurrency suites and versioned-call tests |
| R11 Schema/authorization | Fresh isolated install and upgrade from a production-shaped snapshot produce the same intended objects. No duplicate SMS installation, loss of immutable constraints, broader grants, public recovery execution or collector privilege escalation. Check replacement function bodies and ACLs, not just migration rows. | migration/real PostgreSQL fixtures; reviewed schema manifest |
| R12 Frontend/release | Both websites’ CRM handoff, admin-only county review, exact lead deep links, notification recovery and new feature routes work with the same API/schema revision. Build/typecheck and appropriate existing suites pass; deployment hooks cannot promote an older default branch. | frontend suites/build, CI configuration, deployment-source review |

Test filenames above identify existing suites or patterns where possible; they do not claim every listed case already exists. Add missing behavior cases during implementation. Live carrier or handset acceptance, if eventually needed, requires separate explicit authorization and a fresh eligible event—never reuse the held session/turn as a shortcut.

## Safest eventual integration sequence

1. **Approve the strategy and retain the pause.** Pin refreshed SHAs, then create an isolated integration branch from the production branch only after implementation resumes. Do not use the older PR base. Confirm CI/deployment hooks cannot turn a push into production promotion.
2. **Establish a schema/history manifest.** With separately authorized read-only live inspection, map actual migration rows, table/trigger/function definitions and ACLs to repository sources. Account for split rehearsal history and the reply-notification timestamp mismatch. Record the empty-session migration as unapplied unless fresh evidence proves otherwise.
3. **Preserve shared and production foundations.** Keep the 124 identical files; retain newer county identity, source filters, owner assignment, website retention, SMS transport/receipts and notification behavior. Exclude the four legacy SMS install migrations. No queues, jobs or source settings are reset.
4. **Design forward-only feature schema changes.** Reconcile offer-review, lot, valuation and pinned-call dependencies against the manifest. Do not retroactively replay old timestamps. Keep the non-deleting monitor body. Keep the empty-session repair outside this integration’s migration bundle.
5. **Port feature bundles in small reviewable changes.** First human-offer/draft protections with API/UI contracts; then lot/valuation evidence workflows; separately pinned-call identity with its API/ACL transition. Retain all production intake/import/receipt protections in shared files. Keep workers and outbound paths disabled.
6. **Validate isolated behavior.** After explicit test resumption, satisfy R1–R12 using local/disposable data and stubs. Exercise both fresh-schema and production-upgrade paths. Review intended changes against the production baseline, including permissions and final function definitions.
7. **Prepare a paused release plan.** Document exact artifact, forward schema order, compatible runtime rollback and evidence checks. Schema needed by new code precedes that code; deploy disabled code only after compatibility checks. Do not plan a destructive down-migration over receipts, consent or handoff history.
8. **Separate integration approval from activation.** A later authorized paused deployment must leave sources, collection schedules, SMS schedulers, flags and provider activity disabled. Operational acceptance, session repair and any future collection/SMS activation each require their own explicit scope. A green build is not permission to resume.

## Checkpoint and remaining uncertainty

- [x] Verified both GitHub tips, PR state/base, ancestor and exclusive commit counts.
- [x] Enumerated every changed path, all shared divergences and all migration deltas.
- [x] Reviewed critical SQL collisions, API/UI contracts, provider receipt paths and production checkpoint.
- [x] Produced dispositions, dependency bundles, future regression requirements and integration sequence.
- [ ] No implementation, tests, live schema audit, deployment or operational acceptance has been performed.
- [ ] Actual deployed schema/history, current scheduler state and external provider state remain unrefreshed by design.
- [ ] Final merge conflict resolution and runtime compatibility remain future work; this report is a static strategy, not merge approval.

Resume from this report and `comparison-snapshot.json`. If branch tips change, regenerate the path inventory and revisit affected findings before implementation. The repository and paused operations were left unchanged.
