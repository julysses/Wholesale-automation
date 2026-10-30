# CI runtime recovery — October 29, 2026

Run 40935475072 for a8d891e41ea50a68e033caff69c4ba730dc06a88 ended cancelled, not successful. GitHub annotation: “The job has exceeded the maximum execution time of 15m0s.” Four jobs passed. The database job reached the acquisition workspace suite at 18:56:49 UTC and was cancelled at 19:11:41 UTC; its last completed test was test_source_migration_backfills_without_changing_intakes. The log continued showing successful tests through cancellation and does not prove the unexecuted remainder passes.

The workflow's old runtime comment referred to 163 workspace tests. The current test loader collects 217, including inherited storage cases (209 are defined directly). The cancelled log contains 212 completed workspace tests. Increase only this job's timeout from 15 to 25 minutes, preserving all five jobs, every test, existing concurrency policy and failure reporting. No production code, scheduler or database is changed. This corrective push is necessary because the preceding run is terminal and cannot satisfy the release gate. Do not rerun the unchanged 15-minute configuration or cancel an active successor.

## Exact resume

- The feature commit bce25b9 remains on local codex/acquisition-foundation and is not included in this corrective push.
- The repair branch codex/acquisition-ci-runtime starts at a8d891e. Push its repair commit normally to origin/codex/acquisition-foundation (fast-forward, never force).
- Verify the repair commit's exact all-five GitHub CI success. Then switch to local codex/acquisition-foundation, merge codex/acquisition-ci-runtime, and push the retained feature and repair together. Do not use pull --ff-only on the diverged local feature branch; its feature commit must be retained.
- The retained feature passed 728 evidence/API tests and 44 application/database workflows; see that branch's PROGRESS.md. Its transport still needs durable worker recovery and quarantine/clearance approval binding.
- Keep the full PRD goal active and the numbered navy/orange app workflow intact. Production, paused SMS, outreach, spending and fulfillment remain unchanged.

Validation of this correction: inspected the exact job annotation and full cancelled log; diff changes only the finite CI timeout/comment and this handoff. Hosted completion remains unproven until the successor run finishes.

## Local integration follow-up

The repair is pushed as e0885a6; exact CI is 40993385281. It was merged locally into codex/acquisition-foundation as 08c859a without pushing the retained feature. The branch now also has the four-strategy workflow coverage documented in PROGRESS.md (48 workflows passed). The original switch/merge instructions above are historical: on resume inspect current state, wait for exact repair CI success, then push the already-integrated branch. Do not drop the retained local feature or repeat branch reconstruction.
