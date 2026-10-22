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
Remote build execution remains pending observation and is not assumed from push.

The existing backend CI step now uses the offline guard, matching local acceptance.
The branch deployment exclusion in vercel.json is unchanged. An ordinary push
runs repository CI without deploying this candidate. Docker/Podman are unavailable
locally, and local GitHub CLI credentials are invalid; Git push and connector
workflow observation avoid needing those credentials.

References: [GitHub skip behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs),
[Docker runtime networking](https://docs.docker.com/engine/network/drivers/none/).
