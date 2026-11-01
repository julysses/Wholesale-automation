# Purchase-path CI timestamp repair — November 1, 2026

Run41286088592 on published1e83e4f57287d0a042762d677783b95d2d7df790 failed Backend (pytest) at `test_inconsistent_state_is_unavailable[change11]`. The log is retained in `evidence/2026-11-01-purchase-path-ci-failure.txt`.

The future checked_at value was computed during test collection. The slower GitHub run reached the test approximately two minutes later, making that value current under the existing five-second future tolerance. The endpoint correctly returned200; the fixture incorrectly expected503. This is a test-clock defect, not relaxed app validation or production contact behavior.

The repair generates stale/future timestamps during each test execution and adds fixed-request-clock coverage for -31/-30/+5/+6 seconds, verifying both permitted boundary values and rejection immediately outside the window. No app code, database schema, credentials, provider settings or live controls change.

Focused55 API tests passed2.95s. Full backend4466 tests passed,10 skipped,6 subtests62.12s; session94271 terminal0, log `/tmp/disposition-ci-clock-backend.log`. This repair is isolated on `codex/ci-disposition-clock`, checkout `/tmp/acquisition-ci-fix-41286088592`, based on the exact failed published head. Pending disposition storage/source features remain separate in the main checkout.

Allow all currently running jobs in41286088592 to reach a terminal state. Then push only this verified repair to the existing acquisition branch; a failed predecessor cannot become green without a repair. This is the repair exception to the feature publication gate, not permission to publish pending features or cancel live checks. Wait for all six checks on the repair successor before publishing further feature work. Merge the repair into the main acquisition checkout without losing local candidate106/107 work.
