# Vercel release artifact — October 22 candidate

## Actual production observation

Authenticated connector and CLI metadata agree: production is still READY at
`a89815126d9a98ced016167d8e383641d133135f`, deployment
`dpl_Dwjn7sjLUB5C9X2JsoezbSKjJ6go`. The Python function `api/index.py` has
runtime **python3.12**, memory **2048 MB**, timeout **300 seconds**, region **iad1**.
The retained build log reports Vercel CLI **64.5.0**, **uv 0.10.11** and default
Python 3.12 selection (no selector in that released source). The packaged function
digest/size are in vercel-production-observation-2026-10-22.json. This closes the
previously unknown timeout for this deployed artifact, not every future build.

Public health/config/setup returned HTTP 200. Config fields were present; their
values were not printed or saved. The existing browser session eventually rendered
the signed-in PropStream setup step; no setup settings were saved. A recent 30-minute
error/fatal grouped log query returned no groups; this limited window is not proof
of all-time health or full workflow acceptance. Sending flags are still unverified:
the dashboard explicitly requires email verification to reveal their values.
The prompt is left ready for the user. No authentication code was requested/read.

## Reproduced native packaging gaps and candidate fix

A tracked-source-only copy was built with Vercel CLI 64.5.0, empty HOME and empty
production env file, no authentication token and no environment pull/deployment.
The builder is @vercel/python 25.1.3. Its Python-package discovery returns no
version constraint for a root `.python-version` when it selects `api/requirements.txt`.
Adding `api/.python-version` makes that constraint visible. A small disposable
package fixture reproduced both outcomes through the installed discovery library.

The builder converts requirements into a generated pyproject and lock. To avoid
relying on conversion of hashed requirements, the candidate supplies an explicit
API pyproject and uv.lock. All **61** registry package versions and all retained
artifact hashes match api/requirements.txt; no application version changed. The
native lock targets Linux x86_64 and Python 3.12. The root/API pip locks remain for
Docker/API install tests. The Python builder itself is pinned to 25.1.3.
The release checker rejects divergent selectors, versions, hashes, registries,
unreviewed package sources or builder changes; eight focused checks pass.

The disposable macOS build emitted a Python 3.12/x86_64 function after a discoverable
managed Python 3.12 interpreter became available. A prior local attempt selected
3.11 while uv synced 3.12 dependencies; that output was rejected, not accepted.
The artifact gate checks the emitted runtime rather than trusting build success.
Local cross-compilation cannot prove Linux extension imports. The Linux CI job now passed in [run705](https://github.com/julysses/Wholesale-automation/actions/runs/39861484224).
It materialized all **6,529** mapped function files and cold-started that isolated
bundle with Python3.12.15. Auth/default-off enrollment, all61 API versions, pinned
platform runtime0.23.3 and complete bundled dependency audit passed. The build
log confirms API-local Python3.12, uv0.13.5 and installation from uv.lock. The emitted
function is python3.12/x86_64. The static entry digest matches the earlier Docker
release build. Both patched installer and complete bundle audit report no known
findings. All eight jobs succeeded: CI backend1416/10skip/6subtests, frontend327/62,
lint/build/audit, API-only dependency test, Docker, pipeline/edge and isolated PG.

Candidate1b6288ec950748b8cf08c067f6f63b7fa466dfdf was checked out as PR merge
d432c5ff246e45b2d886e534fdbab6152145d3ca. The GitHub commit API verifies both have
tree b865d8ade365a9e31ca1a715ffac9cad97312755. Exact job/result/limit evidence is
vercel-artifact-evidence.json. No deployment exists for that candidate SHA; this
remains a disposable build check rather than a staged/retained production artifact.

## Installer security and proposed release method

Auditing the observed uv 0.10.11 installer returned three advisory IDs:
PYSEC-2026-4321, GHSA-pjjw-68hj-v9mw and GHSA-4gg8-gxpx-9rph. Maintainer references:
[RECORD traversal](https://github.com/astral-sh/uv/security/advisories/GHSA-pjjw-68hj-v9mw),
[entry-point traversal](https://github.com/astral-sh/uv/security/advisories/GHSA-4gg8-gxpx-9rph),
[root certificate removal](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62).
This is a build-tool finding, not evidence of exploitation or an application-package
vulnerability. The API bundle inventory (including vercel-runtime 0.23.3 and pip
26.2.2) had no known findings at observation.

The new build check uses hash-pinned patched **uv 0.13.5**; its separate audit has
no known findings. The lock gate rejects reverting that tool to the observed old
installer. It does not change the already-deployed platform tooling.

For eventual authorized release, build in a reviewed Linux environment with patched
installer and the approved production context, retain/test that output, stage it
with `vercel deploy --prebuilt --prod --skip-domain`, verify the staged artifact's
actual runtime/configuration and then promote that same production artifact. Do
not silently use a hosted rebuild that reinstalls the observed vulnerable builder
tool. Staging/promotion, runtime secrets/configuration and system build environment
still require the release review. This disposable build/check is not the retained
production artifact and no staged deployment exists from this work.

[Python runtime](https://vercel.com/docs/functions/runtimes/python),
[uv target environments](https://docs.astral.sh/uv/reference/settings/#environments),
[build/promotion workflow](https://vercel.com/docs/deployments/promoting-a-deployment).
All eighteen schema proposals remain unapplied. Policy publication, carrier proof,
paid registration, approved buyer route, handset tests and operator acceptance
remain separate gates; successful packaging does not activate them.
