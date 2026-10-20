# Draft integration: not approved for release

This branch must not be deployed or merged until its isolated regression requirements pass and the owner approves the release. Code preparation is not SMS, provider or collection activation.

## Separate Facebook handoff repair

The native blocker is now repaired locally. `FACEBOOK-HANDOFF-FIX.md` records passing connected journeys; `facebook-handoff-release-manifest.json` contains one additional native-receipt migration, applied only to disposable databases. It is separate from the eleven county feature migrations below. Production-shaped upgrade review and separately authorized release/live acceptance are still required.

## Schema proposal

`forward-migration-map.json` records the eleven newly generated migration files; `forward-migration-order.json` gives their explicit allowlist and order. The four historical collection SMS-install migrations are excluded. All production historical migration files, including the unapplied empty-session repair, remain byte-identical to the production baseline.

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
2. Verify baseline compatibility using a disposable production-shaped database and the explicit eleven-file allowlist.
3. Independently review historical timestamp equivalence. Do not repair migration history by guesswork.
4. After separate release authorization, apply only the reviewed new feature schema in allowlist order, with workers and calling off.
5. Deploy the matching tested runtime in paused mode. The versioned-call migration revokes the old RPC, so calling must remain off across the schema/runtime transition.
6. Verify intake, consent, suppression and receipts without sending. Do not change transport identity, requeue jobs, clear suppression, reconcile the held session or enable schedules.

## Rollback limits

The new call-identity schema revokes the old call RPC. Returning to the old runtime would leave that path unavailable; preserve the pause and use a forward-compatible runtime repair rather than broadly restoring obsolete grants.

Offer, lot and valuation receipts are durable evidence. Do not drop them, erase approvals, reverse owner-nullability blindly, or restore old cleanup functions as a runtime rollback. Existing production intake/SMS schema is intentionally not replaced by these migrations.

## Outstanding evidence

Local backend, UI, SQL and SMS contention tests have now run. See `FACEBOOK-LAUNCH-READINESS.md` for exact results and the original native Facebook Retell handoff blocker (now fixed locally; see `FACEBOOK-HANDOFF-FIX.md`). R1–R12 are not fully satisfied: continuous journey and production-shaped full upgrade acceptance remain outstanding. No production promotion or activation is requested by this draft.
