# Reviewed lot routing activation

Implementation is on the launch-preparation branch; production activation and signed-in acceptance remain open.

## Contract

- An approved administrator must record lot classification with its source URL, notes and current property snapshot. Classification alone does not certify the source or authorize contact.
- Only the latest validated `underwrite_lot` evaluation is selected. The transaction rechecks current scoring input, latest positive review, property identity and approved receiving owner.
- `app_settings.lead_owner_user_id` supplies the receiving owner. Missing/unapproved owners hold the lead; no fallback identity is invented.
- Automatic receipts use `initiation=worker` and a null initiating operator. The prior review still identifies the human reviewer. Manual receipts remain `initiation=operator`.
- Creation of the land record, assigned underwriting task and receipt is atomic. Existing land identity conflicts hold for reconciliation. One lead cannot produce a second handoff. Unknown owner, price, utilities and buildability remain unknown; SMS stays disabled.
- Blocked candidates rotate behind unseen/less recently attempted candidates. Per-candidate SQL failures roll back that candidate and retain the SQLSTATE as a hold, not raw database details.
- A transaction-level worker lock returns `busy` to overlapping workers. Lost HTTP acknowledgement can be reconciled by the saved handoff; a later run skips already-routed leads.
- Monitoring creates one recovery task per blocked lead when an approved owner is available. It reuses the original receiving task for receipts overdue by 60 minutes. An acknowledgement records receipt only, not completed underwriting. Recovery incident resolution does not silently complete human tasks.
- Monitoring runs in the existing list scan/digest, independently of this worker's enable flag, and after a successful routing batch. No scheduler is installed by this change.

## Configuration (remain disabled until acceptance)

`GET /webhooks/_worker/list-lots` requires `Authorization: Bearer <CRON_SECRET>`.

- `LIST_LOT_ROUTING_ENABLED=false` by default.
- `LIST_LOT_ROUTING_BATCH_SIZE=5`, accepted range 1–10.
- Database-only execution; no Claude, tracing, seller email, SMS or calls.

## Remaining activation evidence

- Apply only reconciled migrations to the approved target. Rehearsal does not authorize production release.
- Verify signed-in review → current score → worker → correct linked land record → assigned inbox → receipt acknowledgement, including lost acknowledgements and conflicts.
- Prove deployed endpoint authentication, runtime/load limits and the chosen scheduler cadence. Batch count is bounded; database scan/lock duration is not a proven wall-clock bound. Land deduplication still uses a table lock.
- Verify actual owner digest delivery for blocked and overdue cases; accepted email is not proof of receipt.
- Add/reconcile stale existing handoffs, durable valuation-save recovery, concurrent editing and validated underwriting inputs.
- Establish independent missing-worker alerts; this monitor cannot prove its own scheduler is running.
- Human pricing, compliance, provider/collector acceptance, buyer ranking and all other launch gates remain required.

## Stale handoff reconciliation

The inbox now compares the latest score and lot review, the full reviewed property snapshot, current lot classification, receiver approval and linked land identity (including known parcel/ZIP). Missing property links retain the original reviewed address in the inbox and remain blocked for review.

Administrators can record a hold or reaffirm current evidence. Each immutable decision saves the reviewed evidence fingerprint, prior version, actor and notes. Reaffirmation requires an opened destination and a current qualifying score, matching positive lot review, approved receiver and matching land identity. Changed evidence or competing decisions cause a conflict; retries with the same request return the original decision without restoring it over a newer one.

Original routing and receiving receipts remain unchanged. The inbox separates the original handoff evidence from the latest reconciliation evidence. Monitoring and owner digests include stale/held handoffs, even after receipt acknowledgement, and reopen the original follow-up task without creating another land record/task. These decisions do not modify land prices, seller contact permissions or certify completed underwriting.

Signed-in acceptance remains required. This is a routing evidence review; downstream valuation completeness and exact offer approval/dispatch still require their own controls.
