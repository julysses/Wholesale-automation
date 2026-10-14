# Persistent bulk worker deployment

## Implemented scope

`pipeline/collectors/persistent_worker.py` is a restart-safe **tax collector/delivery worker**, not a completed foreclosure/PropStream integration. It schedules Dallas and Collin tax batches after06:00America/Chicago, preserves collection state in SQLite, and delivers through the existing source-scoped rehearsal Keychain credentials. One process holds an OS lock. It writes a private status file containing counts/states, never raw contacts or credentials.

Accepted jobs are not rerun. An interrupted collection is held rather than silently regenerated; uncertain delivery retries the same saved manifests and durable server receipt identities, at most three attempts with backoff. One county failure does not stop the other. Existing Supabase supervision raises missing/partial-source incidents inside WholesaleOS. Local worker exceptions are saved locally; no claim is made that their detailed reasons are already synchronized to the CRM.

No trace order, reservation, reload, seller outreach, browser session copying or production access exists in this worker. The cumulative$50PropStream cap remains enforced by the existing database functions and is unaffected.

## Deployment decision pending

The owner was asked to choose this Mac versus a separate Railway worker. Do not deploy before that answer: the existing Railway `Wholesale-automation` service is production, connected to `claude/ai-wholesaling-agency-KkDF1`, with no variables, persistent volume or public domain. It must not be replaced or treated as a configured rehearsal worker. Cloud deployment needs separate storage and source-scoped credentials; current Keychain delivery is local-Mac only.

Local invocation, after selecting the Mac and confirming its always-awake operation:

```
python3 pipeline/collectors/persistent_worker.py --state /absolute/private/worker-state
```

Use `--once` for a bounded acceptance run. A persistent supervisor must restart the command after process failure. Keep the state directory outside Git on persistent storage. Do not delete/reinitialize it to retry uncertain jobs. Do not claim that a background process alone survives reboot; install and verify the selected platform's service supervision first.

## PropStream connection evidence — October14

Signed-in Account shows Legacy plan, $50 prepaid, PropStream Connect **Start Free Trial**, and a single displayed integration: **BatchDialer / Connect**. No WholesaleOS/API integration is displayed. Official [BatchDialer integration documentation](https://www.propstream.com/news/push-to-batchdialer-seamless-api-sync-from-propstream-to-batchdialer-for-high-volume-calling) describes pushing selected contacts to BatchDialer; it does not document a general inbound skip-trace API for WholesaleOS. This does not prove private partner APIs do not exist. The owner was asked whether approved partner/API access already exists or whether to prepare an access request.

Do not confuse PropStream with Prostream, Propstreet or PropSpace search results. No provider API endpoint or authentication scheme should be invented. Do not extract signed-in cookies/tokens, start a trial, add a subscription or repurchase the75completed traces.

## Acceptance still required

- Choose and deploy the persistent host, storage and scoped credentials.
- Verify a real county collection/delivery, crash recovery and the next scheduled run.
- Connect local worker exceptions/heartbeat to the existing CRM incident mechanism.
- Implement unattended foreclosure capture and structured verification.
- Obtain/document supported PropStream transport and verify quote, single submission, receipt and billing reconciliation under the existing total cap.
- Verify new eligible-only selection and no orders for completed/no-result/uncertain receipts.
- Keep contact availability distinct from channel clearance and outreach authorization.
