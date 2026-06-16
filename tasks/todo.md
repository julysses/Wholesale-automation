# Wholesale Automation Compliance Fixes

## Checklist
- [x] Pull latest default branch from GitHub before editing.
- [x] Persist opt-out and suppression records through `CRMStore`.
- [x] Pass selected contact identifiers into orchestrated outreach compliance checks.
- [x] Require SMS opt-out instructions on first-touch and follow-up drafts.
- [x] Add focused tests for persistence, orchestration suppression, and SMS opt-out enforcement.
- [x] Add/confirm local test setup documentation.
- [x] Run compile and test verification.
- [x] Review diff, commit, and push.

## Review Notes
- The latest pull brought in the frontend and deployment docs, so the earlier RealtyAPI/PR assessment is now partially stale and should be revisited separately.
- Verification passed with `.venv/bin/python -m compileall -q agents config orchestrator schemas tools web main.py`.
- Verification passed with `.venv/bin/python -m pytest -q`: 108 passed, 1 existing warning from `web/api/fb_ads_api.py`.
- Fixed additional post-pull test drift around distress signal weights, BatchData mocks, and tests accidentally targeting the real `.env` database.

---

# Retell Webhook Signature Verification

## Checklist
- [x] Pull latest default branch from GitHub before editing.
- [x] Identify Retell webhook entrypoints and existing signature helpers.
- [x] Enforce fail-closed HMAC verification for `/webhooks/retell`.
- [x] Enforce fail-closed HMAC verification for `/webhooks/retell/call`.
- [x] Reject legacy static-secret Retell requests.
- [x] Add regression tests for missing config, missing signature, bad signature, valid HMAC, and legacy static-secret rejection.
- [x] Run focused and full test verification.
- [x] Review diff, commit, and push.

## Review Notes
- Focused verification passed with `.venv/bin/python -m pytest -q tests/test_retell_webhook_security.py`: 6 passed.
- Full verification passed with `.venv/bin/python -m pytest -q`: 115 passed.

---

# HOT Lead Automation Backgrounding

## Checklist
- [x] Pull latest default branch from GitHub before editing.
- [x] Inspect Retell, legacy Retell, VAPI, and generic AI call-result HOT automation paths.
- [x] Replace inline HOT automation awaits with a scheduler helper.
- [x] Add regression coverage proving the scheduler does not await slow HOT automation work.
- [x] Run focused and full test verification.
- [x] Review diff, commit, and push.

## Review Notes
- Focused verification passed with `.venv/bin/python -m pytest -q tests/test_hot_lead_automation_backgrounding.py tests/test_retell_webhook_security.py`: 7 passed.
- Full verification passed with `.venv/bin/python -m pytest -q`: 116 passed.

---

# Retell Transcript Chunk Ordering

## Checklist
- [x] Pull latest default branch from GitHub before editing.
- [x] Inspect Retell transcript ingestion and storage paths.
- [x] Persist realtime transcript chunks in deterministic sequence/timestamp order.
- [x] Fall back to ordered realtime chunks when final Retell completion lacks a transcript.
- [x] Add regression tests for out-of-order chunks and completion fallback.
- [x] Update known issues and lessons.
- [x] Run focused and full verification.
- [x] Review diff, commit, and push.

## Review Notes
- Focused verification passed with `.venv/bin/python -m pytest -q tests/test_retell_transcript_ordering.py`: 3 passed.
- Full verification passed with `.venv/bin/python -m pytest -q`: 119 passed.

---

# ARV Fallback Improvements

## Checklist
- [x] Pull latest default branch from GitHub before editing.
- [x] Inspect the deal analyzer ARV source order and current fallback behavior.
- [x] Keep BatchData comps/AVM as the primary real-data path.
- [x] Replace the final flat sqft fallback with a market-aware fallback using city/state/ZIP signals.
- [x] Add tests for market-aware fallback behavior and tax-assessment blending.
- [x] Update known issues and lessons.
- [x] Run focused and full verification.
- [x] Review diff, commit, and push.

## Review Notes
- Focused verification passed with `.venv/bin/python -m pytest -q tests/test_deal_analyzer_arv_fallback.py tests/test_precision_improvements.py`: 7 passed.
- Full verification passed with `.venv/bin/python -m pytest -q`: 122 passed.

---

# Production Sign-In Load Failure

## Checklist
- [x] Pull latest tracked branch from GitHub before editing.
- [x] Reproduce or inspect the production login/config failure path.
- [x] Identify the root cause in the frontend/API auth bootstrap.
- [x] Implement the smallest production-safe fix.
- [x] Add focused regression coverage where practical.
- [x] Run build/test verification.
- [x] Review diff, commit, and push.

## Review Notes
- User confirmed `https://github.com/julysses/Wholesale-automation` is the correct repo.
- Screenshot shows the React sign-in page at `wholesale-automation.vercel.app` with a `Load failed` toast after sign-in.
- Production `/api/config` returns Supabase project ref `dvzhzlipbwzzcliujzyz`; `/api/health` is healthy.
- Direct auth call to `https://dvzhzlipbwzzcliujzyz.supabase.co` fails DNS resolution, while `https://supabase.com` resolves. This points to a wrong, paused, deleted, or otherwise inactive Supabase project ref in Vercel env.
- Vercel CLI is installed but not authenticated in this shell, so deployed env vars could not be changed directly.
- Code fix: `/api/config` now falls back to `SUPABASE_URL` / `SUPABASE_ANON_KEY`, trims env values, and the login page shows a specific Supabase Auth connectivity error instead of raw `Load failed`.
- Verification passed with `.venv/bin/python -m pytest -q tests/test_frontend_config.py`: 2 passed.
- Verification passed with `npm run build` in `frontend`.
- Verification passed with `.venv/bin/python -m pytest -q`: 130 passed.
