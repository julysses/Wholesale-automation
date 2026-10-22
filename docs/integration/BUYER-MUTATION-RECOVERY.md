# Buyer edit/delete recovery candidate — October 22, 2026

Scope: single-buyer editing and deletion from the Buyers screen. Candidate only;
no production buyer was changed or deleted. This is not a rewrite of import cleanup
or every legacy land-preference editor. Signed-in operator acceptance remains open.

Previously the edit hook used a direct browser UPDATE with no retained request.
The delete hook checked only an error, so an empty successful response could be
reported as deletion. A response lost after commit had no durable operation receipt.
The source inspection establishes those acknowledgment gaps; it does not claim a
production incident or that an import deletion stops after1000 rows (it loops).

The new service-only transaction binds a UUID to the verified operator, target,
original complete buyer record, action and editable fields. It rechecks current
profile approval, serializes exact retries and compares the locked current buyer
with the original snapshot. Stale/missing outcomes are retained without changing
the buyer. Saved retries return historical evidence and never overwrite later edits,
repeat a deletion or resurrect a record. A retained stop blocks a late original
request; it recovers a completed result rather than undoing it.

Editable fields are restricted to the existing form's20 profile/preferences fields.
All20 must be explicit; omitted edit fields are refused instead of reset to defaults.
The server computes consent revocation if a normalized phone or email changes.
Formatting-only changes preserve the existing choice; new contact presence never
grants consent. Classification, scoring, suppression and custom tags are outside
the patch. Conflicting recipient identities require review. Short buyer write locks
serialize identity decisions with manual creates/CSV, with3-second lock timeout;
production-volume lock impact still needs review. No provider call occurs in SQL.

Deletion retains the original buyer snapshot and an observed purchase-history count
in an immutable private receipt; purchase history is removed by the existing cascade.
The count is observed before deletion, not a claim of exact affected-row accounting
under unrelated concurrent history deletions. Consent/outreach/other private receipts
keep their existing independent retention. The UI names the buyer and warns that all
purchase history is deleted and the action cannot be undone before its first request.
This work does not execute a real production deletion or add an undo feature.

The browser persists the original record/action/updates before POST in per-operator,
per-tab storage. Storage failure prevents the request. One in-flight mutation per tab
prevents competing requests from replacing the draft. Different details/targets are
refused while uncertain. Read-only recovery, exact retry and durable stop remain
available after closing a modal or reloading; pending reads do not release the draft.
The API helper binds the expected actor to the very session used for its JWT header,
rather than relying only on an earlier UI identity check. Stale/conflict/missing
outcomes cannot produce an updated/deleted success toast. Later direct database
writers remain possible under existing grants; this protocol does not claim to
force every approved client through the new UI.

Verification: real disposable PostgreSQL/API checks cover stale and altered requests,
contact revocation/formatting,1003 purchase rows, deletion/cascade and retained replay,
ledger-failure rollback, eight independent deletion contenders, lost responses,
stop-before-submit, private roles, foreign ownership, current approval and immutable
receipts. A fixture initially used a colliding recipient in the combined rehearsal;
it now allocates unused synthetic contacts instead of weakening the identity check.
The local adapter also uses PostgreSQL JSON snapshots so timestamp representation
matches PostgREST. Browser tests cover persisted drafts, unchanged retries, unavailable
storage, bad receipts, concurrent submissions, named confirmation, pending reads and
failed stops. Exact full/CI outcomes are recorded in the corresponding evidence.

The twenty-first proposal is20261022231552_integration_buyer_mutation_receipts.sql,
created with Supabase CLI. It remains UNAPPLIED with the other twenty proposals.
Schema must precede matching runtime. Preserve mutation receipts and stop tombstones
on rollback; do not return the operator to an old unguarded write while uncertain
requests exist. Carrier approval, policy publication, production flags/backup and
fresh delivery/reply/STOP/source/operator acceptance remain separate launch gates.
