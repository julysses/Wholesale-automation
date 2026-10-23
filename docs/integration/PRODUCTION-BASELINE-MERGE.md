# Current production baseline reconciliation — October 22

The integration candidate at `6418d9325c03ffd7c1a12ef34438a12f5bcda2a3` conflicted
with current production `a89815126d9a98ced016167d8e383641d133135f`. A real merge-tree
check confirmed the conflicts; the connector's PR base SHA still reported the older
19c117a snapshot, so local fetched Git and deployed-commit evidence controlled.

The candidate merges the production branch, never the reverse. Conflict decisions:

| File | Resolution |
| --- | --- |
| docs/START-HERE-NEXT-CHAT.md | Current entry point added; full prior integration handoff retained as labeled history; production-side history remains in Git. |
| pipeline/integration/production_schema.py | Preserve the expanded restore, including verified view security and grants. |
| pipeline/integration/run_lead_journeys.py | Preserve production's saved-catalog/Facebook rehearsal and 300-second journey budget. |
| scripts/run_offline_tests.py | Preserve production secret/network isolation plus the expanded upgrade/security modes. |
| tests/test_facebook_sms_handoff.py | Preserve production's two additional competing-insert cases; all earlier intake coverage remains. |
| tools/facebook_inquiry.py | Preserve immutable exact-ID receipt recovery and the tested PostgREST/psycopg uniqueness-code handling. |
| vercel.json | Union both candidate deployment blocks; retain the rest of the configuration. |

Production already carried Facebook receipt/queue uniqueness recovery. Its queue
recovery and additional tests are now aligned in this candidate. The automatic
merge of `tools/retell_form_sms.py` was inspected; only native unique conflicts may
recover by reading and validating the exact committed job. Other errors propagate.

Verification on the combined branch:

- Backend 1,290 passed, 10 skipped, 416 existing warnings.
- Restored current-shaped schema, authorization guards, twelve forward migrations,
  full/injected rollback, historical preservation and role permissions pass.
- Manual import/API/eight-session deduplication and pinned-call/SMS overlap pass.
- Ten connected intake journeys pass in 122.64 seconds with providers stubbed.
- Both `codex/wholesale-integration-review` and `codex/facebook-release-candidate`
  remain explicitly excluded from Vercel deployment. Non-Git Vercel configuration
  matches the pre-merge candidate.
- Frontend remains the source tested at 6418d93: 254 tests, build/typecheck and lint
  gate pass; pipeline code remains the previously verified 231-test source.

Local ignored logs: `logs/friday-production-merge-backend.log` and
`logs/friday-production-merge-upgrade.log`. Current result: `production-upgrade-result.json`.
No production schema, runtime, records, provider settings or schedules changed.
The branch remains a draft candidate with the wider Friday gates still open.
