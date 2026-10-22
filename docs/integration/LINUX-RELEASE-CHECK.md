# Linux release artifact check — October 22

The production Dockerfile now has a test-only CI job on Ubuntu 24.04. It builds
both frontend and Python 3.12 release stages, installs hash-pinned dependencies,
checks dependencies inside the image and starts the actual Uvicorn process as the
non-root release user. Runtime containers have `--network none`, receive no
provider credentials, and expose no host port. Images are not pushed or deployed.
The checkout does not persist Git credentials. The image label and job log record
the checked-out source SHA and resulting image ID.

The HTTP check verifies health, protected buyer routes (401), unavailable public
enrollment with default-off settings, the complete built static asset contents,
and direct React navigation to buyers and buyer form/privacy/terms. It rejects
missing assets/API/webhook paths. This is release packaging evidence, not database,
carrier approval, delivery, live configuration or signed-in operator acceptance.

The new check reproduced a real defect before repair: `/` returned 200 while
`/buyers`, `/buyer-sms`, `/buyer-sms/privacy` and `/buyer-sms/terms` returned 404.
Starlette StaticFiles(html=True) serves directory indexes, not arbitrary SPA routes.
`web/spa.py` now supplies the React entry page for extensionless browser routes;
reserved API/webhook/v1/assets paths, missing files and unsupported methods retain
errors. Four focused local tests pass. The complete offline backend suite passes:
1,371 passed / 10 skipped (413 existing warnings). The actual built local app
now returns 200 for all five navigation paths and 404 for missing API/assets.
Remote execution is now observed successful: [CI run 703](https://github.com/julysses/Wholesale-automation/actions/runs/39858996754),
all seven jobs passed. Candidate `93e27a4dd5de1b374f1bb92ebb2c7044a9c4c371` was
checked out as PR merge `07d6b93eb8a8a0417817525fd074e1ccd81c1e81`; the GitHub
commit API confirms both have identical tree `105a261b9e3f786f0f42988e0f269fa69ca8b708`.
Docker image ID: `sha256:206cbb0027ca357cb832991994577a36b462d82288610e620aed8b11eb5b87fc`.
Actual runtime: Linux x86_64, Python 3.12.15, pip 26.2.2, Twilio 9.11.2, UID 1001;
82 frontend assets matched their built contents. The image itself was not published.

CI backend discovery additionally includes collector tests: **1,408 passed / 10
skipped / 6 subtests passed** (413 existing warnings); this differs from the local
`tests/`-only count of 1,371. Frontend **327 tests / 62 files**, lint/build/audit,
API-only dependency smoke, three locked Python security audits, pipeline/edge and
isolated PostgreSQL jobs all succeeded. See linux-release-evidence.json for exact
run, image, source and job identities. This closes Linux execution only; actual
Vercel artifact/configuration, production DB and operator/handset acceptance remain
open. Later documentation-only commits do not change the tested runtime files.

The existing backend CI step now uses the offline guard, matching local acceptance.
The branch deployment exclusion in vercel.json is unchanged. An ordinary push
runs repository CI without deploying this candidate. Docker/Podman are unavailable
locally, and local GitHub CLI credentials are invalid; Git push and connector
workflow observation avoid needing those credentials.

References: [GitHub skip behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs),
[Docker runtime networking](https://docs.docker.com/engine/network/drivers/none/).
