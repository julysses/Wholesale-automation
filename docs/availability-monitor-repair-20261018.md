# Availability alerts — October 18, 2026

## Investigation

The latest 100 GitHub workflow runs were reviewed. The screenshot corresponds to run 39156821119 (October 18, 19:01 UTC). That run and 39077341645 failed Hilltop only; 39046990761 failed Jays only. CRM readiness was true in all three. October 15 run 38822308574 also failed Hilltop only. These are public HTTP availability probes, not SMS sends or lead submissions.

The old script made one GET with a ten-second socket timeout and swallowed all errors into false. Three recent failures took about ten seconds. This supports transient connection/response delays, but the original exception/status was discarded, so the precise historical cause cannot be proven. All three endpoints passed the current local live check.

Other sampled CI failures were development checks: 38981078990 had an incomplete isolated SQL fixture (contact_attempts missing); 38956170060 had an Edge dependency lock mismatch. Both are superseded by passing CI on the current SMS branch. Collector PR20 had a stale assertion for Export dialer preparation after the button was renamed Export dialer and SMS preparation. Commit 8bec6d8 corrects the selector while preserving download and API assertions; three local tests and all four PR CI jobs pass. This does not authorize merging the older collector application into production.

## Repair

- At most three read-only GET attempts per target, with 2/5-second backoff, only for network/timeout/DNS and selected transient HTTP errors. TLS, permanent HTTP and invalid readiness responses still fail immediately. Persistent transient failures still fail after the third attempt.
- Every attempt records reason, HTTP status and elapsed milliseconds. GitHub summary and annotations distinguish recovery from failure. No response bodies, raw exception messages, credentials, or lead data are logged.
- Checkout and Python setup use pinned official Node 24 action commits, removing the monitor's deprecated runtime warnings.
- Original schedule remains enabled. No notification preferences changed, no workers invoked, no SMS or collection enabled.

## Deployment protection

GitHub schedules the default branch claude/ai-wholesaling-agency-KkDF1. Its application code is older than the live manually promoted e41e4a3 release. Vercel's live dashboard still names that default branch as its production source. A monitor-only push must not roll the CRM back.

The patch therefore sets vercel.json git.deploymentEnabled to false for that exact older branch only, per https://vercel.com/docs/project-configuration/git-configuration#git.deploymentenabled. Other branch previews and manual reviewed deployments remain available. Preserve this guard until the default branch contains the reconciled current application and its release is verified. Do not remove it as routine cleanup or deploy the old default branch manually.

## Progress

- [x] Inspect failed logs and current public endpoints.
- [x] Prepare bounded retries, diagnostic output and regression coverage.
- [x] 31 focused monitor/readiness tests passed.
- [x] Push isolated patch and verify CI.
- [x] Fast-forward scheduled default branch with deployment guard present.
- [x] Run updated GitHub monitor and verify production still serves e41e4a3.
- [x] Bring fix into current SMS branch and save final checkpoint.

Historical app launch gates remain open: owner SMS/reply/STOP acceptance, Retell cost bound, both-site intake acceptance and county current-sale review. Availability success alone does not close those gates.

## Verified outcome — October 18, 2026, 2:49 PM Central

Monitor fix ad70c7c is pushed to the actual scheduled default branch. Both its CI (39160229620) and a manual invocation of that exact workflow on that branch (39160229457) passed. All three endpoints returned HTTP 200 on the first attempt: CRM readiness 487 ms, Hilltop 193 ms, Jays 385 ms. This verifies the repaired workflow now; it does not prove every prior failure was a false alarm or promise no future outage alerts. The scheduled cadence itself was not changed.

The fix is merged into current app branch codex/retell-sms-production as e3837ec. All four CI jobs passed (39160243874). The collector test correction 8bec6d8 is pushed to codex/dallas-collin-launch-prep; PR20 CI39160192718 passed all four jobs. Earlier failures remain in GitHub history; they have not been deleted or relabeled.

Vercel primary alias still resolves to READY deployment dpl_7cfMq9vkEz85jBhexsTDfhSjPB6q, runtime e41e4a38ec07da19320427be8a9474d8dc1ff886. The monitor commit created only a feature-branch preview on Vercel, not a production deployment. The exact default-branch auto-deployment guard is retained.

Three existing Railway integrations also automatically rebuilt on the default-branch push. Their previous commit was 5c138f1, so application runtime code is unchanged; all three reported SUCCESS. This is an external action caused by the push, not a claim of no deployments. Services: mellow-luck/Wholesale-automation (no public domain), pure-recreation/web (web-production-35e52.up.railway.app), practical-youthfulness/web (web-production-713e4.up.railway.app). The last has unrelated staged changes, which were not applied or altered. Recommendation: reconcile these older hosts and their auto-deploy links as part of release cleanup after confirming their remaining dependencies. Do not delete services or promote old code casually.

Retell ticket65825 checked live again: Open/On Retell AI; the latest entry is still our October16 9:53:49PM Central billing question. No new support message sent. No collection, trace purchase, intake submission, provider test or SMS worker was invoked for this repair; no launch gates were enabled.

Resume: current app branch contains this fix and the prior onboarding/SMS work. Read docs/START-HERE-NEXT-CHAT.md. Next operational gates remain Retell cost bound, the already-approved fresh-owner daytime website/ack/reply/STOP test, both-site intake acceptance, and county property/current-sale review. Full go-live is not yet verified.

Evidence:
- https://github.com/julysses/Wholesale-automation/actions/runs/39160229457 (updated monitor)
- https://github.com/julysses/Wholesale-automation/actions/runs/39160229620 (default branch CI)
- https://github.com/julysses/Wholesale-automation/actions/runs/39160243874 (current app branch CI)
- https://github.com/julysses/Wholesale-automation/actions/runs/39160192718 (collector PR20 CI)
