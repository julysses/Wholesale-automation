# Initial Facebook launch investigation — October 20, 2026

**Superseded locally:** the owner subsequently authorized repair. See [FACEBOOK-HANDOFF-FIX.md](FACEBOOK-HANDOFF-FIX.md) for the implemented native receipt bridge and passing connected local journeys. The diagnosis below records the pre-fix state; production remains unchanged.

**Decision: not ready to certify paid-ad launch for both destinations.** The owner selected both website forms and Facebook Instant Forms. Local testing is authorized; production changes, real messages, provider activity and schedules remain paused.

## Confirmed blocker: Instant Forms with the Retell stack

The existing native Facebook tests exercised direct Twilio acknowledgment with `RETELL_FORM_SMS_ENABLED` absent. They did not exercise the selected Retell workflow.

With that flag enabled, a valid native Facebook inquiry:

1. Creates one CRM lead, assigns its owner and creates one follow-up task.
2. Saves native SMS/AI consent separately on the intake notification.
3. Sends one mocked owner email.
4. Calls `tools/retell_form_sms.py:enqueue`, which looks exclusively for `lead_form_submissions`.
5. Returns `no_form_receipt`, creates no SMS job and leaves the notification in review.

The queue's `submission_id` is a non-null foreign key to website submissions (`20261015192903_retell_form_sms_production.sql`). Native intake does not create one. This affects both `retell_native` and `app_twilio` selection. It is present in the production baseline; the collection integration did not introduce it.

Two new regression cases in `tests/test_facebook_sms_handoff.py` reproduce the hold through the actual intake and enqueue functions, using a memory database and mocked providers. These tests pass because the hold is correctly preserved; **they do not mean native Facebook automation works**. Replaying the webhook does not create a second lead/task, retry email, fall back to Twilio, or invent consent.

Repair requires an explicit durable native-inquiry receipt and queue relationship. Do not manufacture a website consent record or remove the foreign-key requirement as a shortcut. A source-specific receipt should retain the original Meta lead ID, form ID, submitted time, submitted phone, disclosure/version and independent checkbox evidence. Queue identity, expiry, suppression, callback correlation and replay protection must remain stable. Existing held notifications must not automatically become sendable after repair.

## Executed evidence

All application tests used `scripts/run_offline_tests.py`, which supplies a clean environment, temporary HOME, disables dotenv, and blocks Python/Node network connections. Provider libraries were mocked. No production environment file was copied.

| Check | Result | Limit |
|---|---|---|
| Focused intake/consent/Twilio backend | 179 passed | Mocked providers and database |
| Entire backend suite | 1,256 passed, 413 warnings | Before adding the two native Retell blocker cases; warnings primarily existing datetime deprecations |
| Native Facebook focused rerun | 25 passed, including the two new blocker cases | Confirms fail-closed behavior, not successful Retell delivery |
| Entire UI suite | Initially 239 passed, 1 failed | Collection test expected an obsolete two-part cache key |
| Corrected UI test file | 3 passed | Expectation now retains production actor, pagination and source filters; no app code changed |
| Pipeline / disposable PGlite suite | 230 passed, none skipped | Selected migration fixtures, not a full production-shaped upgrade |
| TypeScript + Vite build | Passed | Existing >500 kB bundle warnings |
| Lint baseline check | No new findings; 144 existing | Not a clean-lint claim |
| Real PostgreSQL SMS contention | Passed, eight workers, zero provider calls | Temporary localhost cluster, synthetic receipts, stubbed scheduler HTTP |
| Offline runner boundary probes | Python and Node both rejected connection attempts before network access | Expected nonzero probe exit |

The PostgreSQL rehearsal confirmed one initial claim, one generation claim, one session binding, one generation receipt, one reply-dispatch claim, and correct carrier/recovery contention. Its synthetic scheduler is inside the disposable database; no real scheduler was enabled. The cluster was shut down and removed by the runner.

Commands are reproducible from the repository root:

```sh
.venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest tests -q
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend test
.venv/bin/python scripts/run_offline_tests.py npm --prefix pipeline test
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend run build
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend run lint:check
.venv/bin/python scripts/run_offline_tests.py --postgres-sms
```

Local raw logs are in ignored `logs/local-*.log`. Python 3.12.14 and Node 24.14.0 were used. `local-test-environment.txt` records resolved Python versions; frontend/pipeline use their committed npm lockfiles. Production runtime equivalence remains a release gate.

## Coverage and outstanding gates

| Journey or invariant | Local evidence | Still required |
|---|---|---|
| Hilltop/Jays website intake | Validation, durable receipt, lost-response retry, exact inquiry linkage and UI outage recovery pass | One continuous browser-to-database journey on the reviewed runtime/schema; actual destination configuration |
| Native Facebook intake | Lead/owner/task/consent and retry tests pass | Durable native receipt/Retell queue bridge; selected Meta form and webhook configuration verification |
| Consent and suppression | Independent channel consent, unknown/stale disclosure, phone mismatch, DNC/STOP and later-reply holds covered | Controlled live STOP acceptance after separate approval |
| Acknowledgment/reply routing | Website queue, app/native ownership, no fallback, expiry and mocked dispatch tests pass | Resolve the previously held production session only through separately reviewed procedure; prove a fresh conversation |
| Provider receipts | Signature, SID/chat binding, duplicate/out-of-order events, callback-before-response and paused receipt processing covered | Actual carrier delivery and handset confirmation for a fresh acknowledgment and reply |
| Owner handling | Owned due tasks, persisted replies, email claims and exact CRM links covered | Operator verifies real inbox/task/CRM handoff for both destinations |
| County integration R9–R11 | Existing feature SQL/API/UI tests pass | Full eleven-migration production-shaped upgrade and ingress/offer/lot/valuation concurrency rehearsal remain outstanding |
| Release | Branch deployment exclusion retained; local build passes | Review exact runtime/schema, release allowlist and rollback before any deployment |

No fully connected browser/API/PostgreSQL/provider-mock journey was added in this pass. The passing layers are useful evidence, not a substitute for that final composition check or live acceptance.

## Next sequence

1. Review these results. Keep PR #21 draft and all production operations paused.
2. Prioritize the native Facebook receipt/queue bridge and a continuous mocked journey for both destinations. Keep county features off the Facebook launch critical path.
3. Validate the bridge in a disposable database: new inquiry only, consent missing/changed, duplicate webhook, lost database acknowledgment, no owner, suppression, expiry, paused sending, signed receipts and no replay. Rehearse schema upgrade without changing historical migrations.
4. Review the exact candidate and remaining full-integration schema checks. Website readiness and collection readiness must have separate decisions.
5. Only after separate release/live-test approval, deploy the reviewed candidate in paused mode and perform bounded owner-controlled acceptance. Verify submission → CRM → task/owner alert → acknowledgment → reply → STOP, with carrier receipts and handset evidence for each supported destination.
6. Decide ad launch and any later schedule activation from that evidence.

There is no defensible unconditional operational date yet. The native receipt bridge, end-to-end composition and reviewed live delivery/STOP acceptance are unresolved. A green local suite alone must not be used to start paid traffic or declare the full system operational.
