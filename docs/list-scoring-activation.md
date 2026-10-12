# Scoring worker activation and acceptance

Status: implemented and tested in the launch-preparation branch and rehearsal database only. Disabled by default. No scheduler installed and no live Claude request accepted yet.

## Execution contract

- GET `/webhooks/_worker/list-scoring` requires `Authorization: Bearer <CRON_SECRET>`. Missing server secret returns 503; incorrect authorization returns 401 before processing.
- `LIST_SCORING_ENABLED=false` is the default. `LIST_SCORING_BATCH_SIZE` defaults to 5 and accepts only 1–10.
- Server requires service-role database access and the configured Anthropic key/model for new model requests. Received responses can finish without an Anthropic key.
- Selection prioritizes saved responses, reuses queued identities, excludes submitted/review holds, and skips evaluations matching current evidence. Concurrent selection returns the same job; the database claim permits only one dispatch.
- Obsolete attempts remain immutable history. A new current attempt may be created after an obsolete job, including when evidence returns to an earlier value. Submitted or review holds are never reset automatically.
- Each worker stops starting additional jobs after a soft 40-second processing window measured after selection. New Anthropic clients use a 15-second request timeout and zero SDK retries. These limits do not bound total database/network latency or candidate scanning. The shared Supabase client currently uses library defaults.
- Per-job unconfirmed outcomes retain durable state. Inspect `outcomes`, not only HTTP 200. A failed whole batch returns 503. Neither response authorizes a new model request for an uncertain submitted job.
- Scoring does not grant outreach permission, send seller messages, generate offer prices, or acknowledge lot underwriting. The separate list monitor/digest must run to create stalled-job alerts.

## Required before activation

1. Approve deployment scope and reconcile migration contents/history against the target database. Do not replay historical migrations wholesale.
2. Verify actual Vercel project plan, function duration configuration, scheduler capabilities and deployed route protection. Root configuration currently uses legacy builds and has no explicit maximum duration for this worker. Supabase Pro does not establish Vercel capacity.
3. Confirm the actual Claude model identifier, structured-response compatibility, cost expectations and scoring rubric using controlled synthetic evidence. Verify unknown equity/ODN handling and evidence-backed reasons.
4. Measure full invocation duration, candidate selection query performance and backlog drain with representative volume. Prove the collection-to-ready target of 60 minutes; the batch cap alone is insufficient. Configure database timeouts and runtime headroom based on the measured deployment.
5. Install an authenticated scheduler only after these checks. Verify overlapping invocations, saved-response recovery, uncertain-call holds and actual operator incident visibility. Configure an independent missing-worker alert.
6. Confirm administrator threshold editing, saved-response completion, evidence review and escalation in the signed-in UI. Daily Lists now offers read-only inspection of submitted/review jobs with original inputs, saved responses, validation reasons and changed-input sections. This does not reconcile an uncertain provider outcome. Complete compliance, tracing, lot handoff and all other launch acceptance separately.

## Disable / recover

Set `LIST_SCORING_ENABLED=false` and disable the scheduler to stop new worker invocations. In-flight work may already be submitted; inspect durable job state before intervening. Never delete/reset submitted jobs or change IDs to bypass a hold. Saved received responses may be completed through audited administrator controls without a new model request. There is no automatic uncertain-request reconciliation.

## Verification evidence

- Full backend: 784 tests passed. Full pipeline: 62 tests passed.
- Real localhost PostgreSQL/TLS contention: two waiting sessions selected one shared job, then exactly one acquired dispatch permission. Receipt recovery completed without a model call.
- Rehearsal SQL rollback test: selection replay, unknown exclusion, prior-model saved response, current-score skip and denied browser execution passed.
- These are database/code proofs, not production scheduling, live model delivery, runtime capacity or unattended acceptance.
