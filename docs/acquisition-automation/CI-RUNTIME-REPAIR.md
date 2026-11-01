# CI runtime repair — October 31, 2026

Isolated repair candidate based on f793a05 (includes deterministic bot challenge test fix). No acquisition feature commits are included.

Run 41252309134 job 124688164617 completed cancelled at 23:48:26 UTC after the 25-minute job limit. Its log stopped in apt update while fetching packages from http://azure.archive.ubuntu.com/ubuntu; no database acceptance test ran. This job was not manually cancelled or restarted.

The PostgreSQL-16 setup step now replaces that specific Azure mirror with Ubuntu's HTTPS archive on the disposable runner, preserves repository signature validation, uses two retries and 30-second HTTP/HTTPS timeouts, and has a five-minute setup budget. Package versions and all acceptance steps remain intact. No production configuration changes.

APT option references: [apt.conf](https://manpages.debian.org/trixie/apt/apt.conf.5.en.html) and [HTTP transport timeouts](https://manpages.debian.org/trixie/apt/apt-transport-http.1.en.html). Local validation checks workflow parsing and shell syntax. Real Linux package install and all six jobs must pass in the successor run before any feature publication.

## Follow-up: acquisition dependency setup

Run 41255050827 on c3b91a7 cancelled acquisition job 124696328452 at its ten-minute limit. Its log shows Azure Ubuntu package fetches stalled from 00:04:09 UTC until cancellation at 00:13:40; acquisition tests never started. The previous repair covered only the contention job. Apply the same signed HTTPS archive replacement, bounded retries/timeouts and five-minute setup limit to both remaining PostgreSQL installation steps. Keep every test, package version and overall job budget intact.

Prepared on the published c3b91a7 baseline, excluding unpublished interface and human-review work. Local validation passed: workflow parsed and all 28 inline shell steps passed bash syntax checks; git diff whitespace checks passed. Publication waits for the predecessor's remaining live job to finish; no manual cancellation or restart. Successor CI remains required before another feature push. No production changes.

## Review-candidate clock fixture repair

Published checkpoint 2a5690e successor 41257089916 failed backend job 124702445359 in test_candidate_rejects_invalid_approval_choice[change4]. The test computed max_expires_at at collection; more than ten seconds passed before candidate.checked_at was created, turning a supposedly >24-hour expiry into a valid <24-hour expiry. The application correctly accepted that now-valid interval. Generate relative timestamps inside each parameterized test instead. Apply the same execution-time rule to future/stale checked_at and expiry parameters in this review API test module. Production validation rules are unchanged.

This isolated repair excludes the unpublished form and visual QA changes. Validate focused and full offline backend suites. Wait for all predecessor jobs to finish before pushing the isolated repair, then require all six successor jobs before more feature publication.

The same run's full-upgrade job124702445313 timed out in the combined five-minute setup step. PostgreSQL installation completed around 00:36:05 UTC; pip began with less than twenty seconds remaining, then the step expired at 00:36:23. Split system-package and Python-package installation into separately bounded five-minute steps in both acquisition jobs. Retain original overall job timeouts, every test, package signatures and versions. Pip network attempts use two retries and a thirty-second socket timeout. No production setting changes.

Validation: full offline backend passed 3,565 tests, 10 skipped and six subtests in 28.81s (/tmp/contract-review-clock-repair-backend-final.log). An initial local edit also deferred a non-parameterized request timestamp, producing a JSON serialization error; corrected that request to evaluate immediately, then reran the suite successfully. Workflow parsing and all 30 inline shell syntax checks passed. Real Linux installation and successor CI remain unverified until publication.
