# Acquisition automation — progress and resume checkpoint

Checkpoint date: October 25, 2026 (America/Chicago).
Status: planning captured; implementation and activation not started.

## Verified this session

- Original workspace was empty and not a Git repository.
- Located existing WholesaleOS checkouts and verified their origin: `https://github.com/julysses/Wholesale-automation.git`.
- Cloned origin into this workspace's `app/` directory and ran `git pull --ff-only`: already up to date.
- Clone default branch: `claude/ai-wholesaling-agency-KkDF1`.
- Planning base: `ad70c7c29d618efe3aad848a386ca1779f0e7b8f` — Handle transient availability failures and preserve current production release.
- Created documentation branch: `codex/acquisition-prd-v1-plan`.
- No repository AGENTS.md was found by file inventory. User-supplied instructions govern: Codex pulls/pushes updates; GPT Work maintains a resumable planning/progress file.
- Captured all PRD requirement groups, logical entities, ordered activation gates and acceptance expectations in `IMPLEMENTATION-PLAN.md`.

## Checklist

- [x] Locate source repository and pull current default branch.
- [x] Save implementation plan and durable progress record.
- [ ] Verify deployed production code/schema and paused operations against current evidence.
- [ ] Inventory existing schema, migration history, RLS, roles and equivalent entities.
- [ ] Complete `SCHEMA-MAPPING.md` before writing SQL.
- [ ] Build/test shared foundation on a disposable database.
- [ ] Implement and pass Facebook acceptance with approved test leads.
- [ ] Obtain any required production migration/activation approvals.
- [ ] Pass inbound calling/mail gate.
- [ ] Pass portal/proposed-batch gate.
- [ ] Pass human-caller gate.
- [ ] Pass agency controlled-pilot gate.

## Repository context — not production verification

Earlier local checkouts have different heads:

- `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app`: `codex/facebook-release-candidate`, `8e08409`, clean at inspection.
- `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/integration`: `codex/wholesale-integration-review`, `c63f7d5`, two untracked duplicate-named schema files. Left untouched.
- `/Users/juliodominguez/Documents/Codex/2026-10-20/a-review-of-the-wholesaleos-github/facebook-release`: `codex/facebook-release-candidate`, `4480112`, clean at inspection.

Their relationship to the deployed baseline has not been verified. Do not reconstruct or merge an unpublished candidate from these references. Historical memory suggested prior paused Facebook work; current provider, schedule and deployment state was not queried.

## Exact resume steps

1. Enter `/Users/juliodominguez/Documents/Codex/2026-10-25/wholesaleos-acquisition-automation-prd-version-1/app`.
2. Check branch/status; pull its upstream with `git pull --ff-only` before changes. Preserve unrelated work.
3. Read this file and `IMPLEMENTATION-PLAN.md`, then inspect existing release/handoff documentation and establish the authoritative production baseline read-only.
4. Inventory schema and application interfaces. Load applicable Supabase skill before database work. Read current official provider docs when implementing APIs.
5. Write the evidence-backed entity mapping, conflict list, migration plan and disposable-test matrix before SQL.
6. Update this checkpoint with concrete evidence, changes, remaining blockers and next action; commit and push each completed update.

## Validation and external effects

Documentation-only change: verify requirement coverage and `git diff --check`; runtime tests are not applicable. No SQL, app code, provider configuration, scheduling, advertising, outreach, mail, offer transmission or contract execution changed. No production rollout is claimed. Git commit/push completion is reported separately after verification; inspect branch upstream and latest log when resuming.
