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
