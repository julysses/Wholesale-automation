# Availability alerts — October 18, 2026

## Investigation

The latest 100 GitHub workflow runs were reviewed. The screenshot corresponds to run 39156821119 (October 18, 19:01 UTC). That run and 39077341645 failed Hilltop only; 39046990761 failed Jays only. CRM readiness was true in all three. October 15 run 38822308574 also failed Hilltop only. These are public HTTP availability probes, not SMS sends or lead submissions.

The old script made one GET with a ten-second socket timeout and swallowed all errors into false. Three recent failures took about ten seconds. This supports transient connection/response delays, but the original exception/status was discarded, so the precise historical cause cannot be proven. All three endpoints passed the current local live check.

Other sampled CI failures were development checks: 38981078990 had an incomplete isolated SQL fixture (contact_attempts missing); 38956170060 had an Edge dependency lock mismatch. Both are superseded by passing CI on the current SMS branch. Collector PR20's old branch still has a frontend test expecting the removed Export dialer preparation button; do not call that PR ready merely because the current deployed app CI passes.

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
- [ ] Push isolated patch and verify CI.
- [ ] Fast-forward scheduled default branch with deployment guard present.
- [ ] Run updated GitHub monitor and verify production still serves e41e4a3.
- [ ] Bring fix into current SMS branch and save final checkpoint.

Historical app launch gates remain open: owner SMS/reply/STOP acceptance, Retell cost bound, both-site intake acceptance and county current-sale review. Availability success alone does not close those gates.
