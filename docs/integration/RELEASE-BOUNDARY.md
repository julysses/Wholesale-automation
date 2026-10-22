# Draft integration: not approved for release

This branch must not be deployed or merged until its isolated regression requirements pass and the owner approves the release. Code preparation is not SMS, provider or collection activation.

## Current candidate — twenty-one proposals, still unapplied

The authoritative ordered allowlist is `forward-migration-order.json` (21 files).
Later checkpoints add durable buyer outreach claims, reviewed buyer SMS consent,
dedicated buyer transport and invitation-bound enrollment. The sections below
record earlier checkpoints and must not be used as the current migration count.
The nineteenth proposal adds private manual buyer creation/cancellation receipts
and changes only future SMS/email consent defaults to false. No existing row is
opted in/out by that DDL. Preserve these receipts on rollback; a stopped request
must not be reopened by replay or a return to the old direct browser create.
The twentieth proposal adds private retained analysis requests, claims, one-way paid
authorizations, results, commits and stop tombstones. They are durable evidence.
Rollback must preserve paid unknown holds and saved results; do not restore the
old BackgroundTasks/classification fallback or remove receipts to retry a charge.

The twenty-first proposal retains single-buyer edits/deletes and cancellation in a
private immutable ledger. Retain these receipts on rollback; reverting to direct
browser deletion is not recovery for an uncertain request. Contact changes revoke
that channel's opt-in; a runtime rollback must never restore an older contact choice.

Owner approval on October 22 covers the exact buyer policy wording only; it does
not approve this release, fees, registration or activation.

Before any production application, record the actual deployed source/artifact and
refresh the production catalog/history/ACL and paused configuration. Capture and
verify a restorable backup at the approved maintenance boundary. The disposable
saved-catalog rehearsal proves candidate behavior against that snapshot, not a
current production backup or a live restore. Verify the exact twenty-one-file set
and hashes against the reviewed commit; apply only that set in order. Keep calling,
email, SMS, enrollment, collection workers and broad schedules paused throughout.

After schema application, deploy the matching reviewed runtime in paused mode.
Set only approved policy identity/support/origin/version for publication when the
release is authorized, leaving enrollment and sending disabled. Verify the exact
public text/routes, business-site link, operator auth and current grants before
using them in registration. Buyer provider routing and controlled messaging are
separate later steps; they are not side effects of a successful deploy.

Current Linux release evidence is tracked in LINUX-RELEASE-CHECK.md. A container
check cannot prove the Vercel deployment's interpreter/installer/configuration or
its exact artifact. Record those separately before promoting Vercel production.

## October 22 atomic buyer CSV checkpoint

The additional proposal `20261022190018_integration_buyer_csv_transaction.sql`
introduces private immutable receipts and a service-only transaction. Apply schema
before matching API. Fourteen proposals are now allowlisted. Buyer and transaction
write locks, production APN uniqueness and production-volume acceptance require
review before deployment. No historical migrations or APN indexes were modified.
See `BUYER-CSV-TRANSACTION.md`; broad schedules remain paused.

## October 22 buyer visibility checkpoint

Complete buyer reads/history and existing land preference editing now pass local
checks, including 1,003-row capped real-SQL reads. No additional migration. Buyer
import/background-result durability, outreach-log completeness and signed-in
operator/live acceptance remain open; see `BUYER-READ-COMPLETENESS.md`. This did
not add a migration. The subsequent fourteenth proposal is described above; neither
checkpoint authorizes provider activation.

## Separate Facebook handoff repair

The native blocker is now repaired locally. `FACEBOOK-HANDOFF-FIX.md` records passing connected journeys; `facebook-handoff-release-manifest.json` contains one additional native-receipt migration, applied only to disposable databases. It is separate from the eleven county feature migrations below. Production-shaped upgrade review and separately authorized release/live acceptance are still required.

## Schema proposal

`forward-migration-map.json` records the original eleven ported feature files. The October 22 manual CSV repair adds `20261022160020_integration_manual_land_import.sql`; `forward-migration-order.json` explicitly listed fourteen files at that checkpoint, including `20261022170346_integration_csv_lead_intake.sql` for connected main CSV intake and one-way optional AI claims/results. Matching schema must precede runtime; missing RPCs fail closed. Bounded AI batch recovery now passes; real provider/production-volume behavior and operator review remain open; see `CSV-LEAD-TRANSACTION.md`. `MANUAL-LAND-IMPORT.md` and its manifest explain this additional proposal. The four historical collection SMS-install migrations are excluded. All production historical migration files, including the unapplied empty-session repair, remain byte-identical to the production baseline.

**Never run a directory-wide database push against production.** Repository history does not match server timestamps, and the earlier empty-session reconciliation file is deliberately unapplied and excluded from this integration. Applying all pending migrations would exceed authorization.

Read-only production metadata on October 20 confirms:

- Migration history ends with `20261019195321_sms_reply_notification_handoff`.
- No `private.reconcile_empty_retell_session`, offer review functions, lot workflow functions, land valuation receipt functions, or versioned-call claim function were present in the inspected catalog.
- Existing `land_leads` and `land_comps` tables are present. `retell_call_requests` does not have the collection pinned-identity columns.
- `wholesale_ingest.scan_at` preserves evidence; its current body has no expiry cleanup.
- `public.scan_list_pipeline` already adds scoring monitoring. The proposed lot-worker migration preserves that composition and adds lot monitoring without replacing `scan_at`.
- Critical production receipt/claim RPCs are not public: inspected ACLs grant execution to postgres and service_role.

The metadata is a point-in-time planning snapshot, not full schema acceptance. Recheck before any approved application. No business rows were read or changed for this snapshot.

## Eventual ordering

1. Refresh deployed schema, history and ACL fingerprints.
2. Verify baseline compatibility using a disposable production-shaped database and the current explicit twenty-one-file allowlist.
3. Independently review historical timestamp equivalence. Do not repair migration history by guesswork.
4. After separate release authorization, apply only the reviewed new feature schema in allowlist order, with workers and calling off.
5. Deploy the matching tested runtime in paused mode. The versioned-call migration revokes the old RPC, so calling must remain off across the schema/runtime transition.
6. Verify intake, consent, suppression and receipts without sending. Do not change transport identity, requeue jobs, clear suppression, reconcile the held session or enable schedules.

## Rollback limits

The new call-identity schema revokes the old call RPC. Returning to the old runtime would leave that path unavailable; preserve the pause and use a forward-compatible runtime repair rather than broadly restoring obsolete grants.

Offer, lot, valuation, import, outreach, consent, enrollment and signed provider
receipts are durable evidence. Do not drop them, erase approvals, reverse owner-nullability blindly, or restore old cleanup functions as a runtime rollback. Existing production intake/SMS schema is intentionally not replaced by these migrations.

Keep buyer event receivers and the matching saved sender identity available while
outbound messaging is paused, so in-flight delivery/replies/STOP retain evidence.
Do not move or rotate the homeowner sender to satisfy buyer registration. Do not
clear unknown attempts, requeue reserved messages, drop consent/choice receipts,
restore opted-out buyers, or reset DNC as a rollback. Preserve refusal ordering
and old callbacks; changing transport identity requires a separate reviewed plan.
A runtime rollback is acceptable only if its functions/grants remain compatible
with the applied schema. Otherwise keep the relevant capability unavailable and
ship a reviewed forward repair; do not reverse the twenty-one migrations or restore
a pre-upgrade backup over new live receipts as a routine recovery action.

## Outstanding evidence

Local backend, UI, SQL and SMS contention tests have now run. See `FACEBOOK-LAUNCH-READINESS.md` for exact results and the original native Facebook Retell handoff blocker (now fixed locally; see `FACEBOOK-HANDOFF-FIX.md`). The populated saved-catalog upgrade, injected rollback, ten connected intake journeys and separate feature concurrency checks now pass; see `FRIDAY-UPGRADE-REHEARSAL.md`. R1–R12 are not fully satisfied: current shape drift, view security and pinned-call overlap now pass. Remaining cross-feature/import coverage, exact release/recovery review, runtime flag verification, live delivery and operator acceptance remain outstanding. No production promotion or activation is requested by this draft.
