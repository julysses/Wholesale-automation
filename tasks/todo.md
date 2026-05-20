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
