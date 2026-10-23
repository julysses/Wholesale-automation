# Manual buyer creation — October 22 candidate

Manual buyer creation previously inserted directly from the browser with no stable
request reference. A committed save followed by a lost response could produce a
duplicate on retry. The legacy database defaults also set SMS/email opt-in true
when omitted. The nineteenth migration proposal fixes future defaults only; it
does not change existing buyer records or infer consent.

The new operator API creates the buyer and immutable private receipt in one
transaction. New records explicitly have SMS/email opt-in false, and consent fields
are forbidden in the manual payload. The verified current operator is bound to the
receipt; another operator cannot read/reuse it. Approved-profile status is checked
again in SQL. Only service_role can execute the SECURITY INVOKER RPCs or select/
insert private receipts. RLS, immutable triggers and denied update/delete grants
protect history. There is no buyer/auth-user FK that could erase that receipt.

A stable UUID also identifies the new buyer. Exact retries return the original
creation snapshot and whether the buyer currently exists. They never overwrite
later edits or recreate a deleted buyer. Changed payloads conflict. Existing phone/
email identities and same-name entries without a confirmed contact require review,
not automatic merging. This bounded decision uses the existing buyer-table lock
pattern with a three-second timeout, serializing with CSV and browser writes;
production-volume/lock acceptance remains open.

The browser stores the original request and buyer draft in per-operator,
per-tab session storage before POST, using the app's existing draft convention.
It never stores credentials there. Unavailable/corrupt storage fails closed before
a new write. After an uncertain response, fields remain locked and restore after
reopening the modal. The operator may check the saved result without writing,
retry exactly the original save, or stop the pending request. A cancellation is a
durable negative receipt under the same request lock: it blocks a later original
POST, or recovers a save that already committed. It never deletes a committed buyer.
A pending read or failed cancellation cannot release the reference. A fresh 422
permits correction; a later 422 cannot disprove an earlier uncertain save.

This does not make arbitrary buyer edits/deletes idempotent and does not implement
durable explicit AI classification/rescoring. Those remain separate Friday gates.
No automatic classification, outreach, tracing or message is triggered by creation.
Approved buyer SMS enrollment and reviewed written evidence remain separate.

Local validation: backend1379/10skip, frontend342/63files, build/typecheck,
lint gate142existing, clean API-only cold start and protected manual route pass.
Real PostgreSQL: nineteen-proposal apply/injected/full rollback/history/ACL,
atomic receipt failure rollback, eight concurrent creates, cancellation races,
lost-response recovery, role revocation, immutable/retained history, identity
conflicts and false defaults pass. Ten connected intake journeys pass in123.04s;
Auth/provider boundaries remain stubbed. Thirteen browser recovery tests and two
new modal recovery checks pass. New CI includes dedicated Linux real-PG acceptance
and extended native Vercel bundle smoke; its result is pending observation.

Current sources: manual-buyer-manifest.json. Exact SQL result:
manual-buyer-sql-result.json. All nineteen proposals remain unapplied. No production
schema, data, settings, deployment, provider calls, purchase or activation changed.

CI follow-up: run707's app/Vercel/Docker/frontend/API jobs passed, but the new
Linux PG job stopped before DB tests because the offline wrapper omitted PG_BIN
and the runner selected its macOS default path. The wrapper now passes only this
non-secret path for its owned loopback DB modes. Explicit-PG_BIN local execution
passes. No provider credentials or external database URL are inherited. A new
commit/run must prove the Linux database job before this gate is accepted.

Run709 reached restore and exposed the second environment mismatch: PostgreSQL16
cannot restore the saved catalog's MAINTAIN permission. The dedicated job now
installs PostgreSQL17 from the [official PGDG repository](https://www.postgresql.org/download/linux/ubuntu/)
and uses /usr/lib/postgresql/17/bin. The rehearsal rejects older versions before
restoring; no privileges were stripped and no SQL assertions were relaxed. Local
PG17 remains the same verified target. The next Linux result remains pending.

## Verified Linux result

[Run711](https://github.com/julysses/Wholesale-automation/actions/runs/39866097570)
passed all nine jobs for runtime2a3d28c. Its PR merge37e1281 has the identical tree
610269896e68765196d63dd63d7fc05eae0cdc30 (GitHub commit API checked both).
PostgreSQL17.11 restored the full saved catalog including MAINTAIN grants and
passed all19 apply/rollback/ACL and manual race/recovery checks. The original
failed environment attempts above remain recorded; no assertion was weakened.
Current native Vercel bundle cold-start passed with6539 mapped files, Python3.12.15,
all61 API versions and platform SDK, patched installer/bundle audits0 findings.
CI backend1416/10skip/6subtests; frontend342/63; API-only, Docker, pipeline/edge and
ingestion/SMS PG jobs passed. See manual-buyer-ci-evidence.json for exact identities.
Later documentation does not change this tested runtime. This validates manual
creation only; it does not certify the full launch or arbitrary edit/delete recovery.
