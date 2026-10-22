# Python dependency security and reproducible release inputs

October 22, 2026. Candidate only; no deployment or production settings changed.
Commit containing this checkpoint follows `684c5a4` on the existing draft PR #21.

## Latest Vercel follow-up

The later Linux release job passed; see LINUX-RELEASE-CHECK.md. Actual production
metadata now proves Python3.12 and a 300-second function timeout at a898151.
Its observed uv0.10.11 build installer has three known advisory IDs. The candidate
now adds API-local version selection and a native uv lock matching all61 API
versions/hashes, a pinned Python builder, and a separately hash-pinned uv0.13.5
build installer with no known findings. Native bundle CI now passed in run39861484224: all8 jobs, mapped function
cold start and complete platform-added dependency audit. See vercel-artifact-evidence.json. See VERCEL-RELEASE-ARTIFACT.md; older counts below are historical.

## Changes

The root and production API requirements previously used open-ended lower bounds.
A new build could resolve different SDK/framework versions from those tested.
`requirements.in` and `api/requirements.in` retain the dependency declarations;
`requirements.txt` and `api/requirements.txt` now pin every transitive package and
its SHA256 distribution hashes. All 84 root package versions match the prior
successful test environment; the 61 API versions match their root counterparts.
No application dependency version was upgraded in this checkpoint.

`requirements-security.in` and its hashed `.txt` isolate 29 CI audit-tool packages
from application environments. The tool is pip-audit 2.10.1; the resolver used was
uv 0.13.5. The checked package installer is pip 26.2.2. CI and Docker explicitly use
that version, hash-checked application installs and `pip check`. New CI jobs check
lock structure/shared API versions, audit all three complete dependency sets and
verify the API-only import/health/access boundary. Existing CI jobs are retained.
The existing Twilio bundle test now parses hashed requirements instead of assuming
a requirement occupies one physical line; its exact version assertion is unchanged.

## Python target

The legacy runtime.txt, CI and Docker previously declared Python 3.11 while the
local successful runtime was Python 3.12.14. Vercel's current documentation supports
3.12 and reads `.python-version`; runtime.txt is not its documented selector.
The candidate now explicitly selects 3.12 using `.python-version`, aligns CI and
Docker to 3.12, and updates the legacy runtime.txt record to 3.12.14. This does not
prove which interpreter the already-deployed production artifact uses.

## Evidence and limits

- Initial inventory: 85 installed distributions. The 84 application/test packages
  had no known vulnerabilities. Historical pip 25.0.1 produced six distinct advisory
  IDs (12 feed entries including duplicates). The shared old environment was not
  mutated. Fresh root/API/tool environments use pip 26.2.2; the tool lock audit
  includes that version and has no findings.
- Candidate PyPI audits: root 84 packages, API 61, isolated tools 29, zero known
  vulnerabilities and zero skipped dependencies. No vulnerability IDs were ignored.
  Exact results, version lists and source hashes: `python-dependency-audit-2026-10-22.json`.
- Separate fresh Python 3.12.14 root/API environments installed only binary wheels
  with `--require-hashes`; `pip check` reports no broken dependencies in either.
  The isolated audit-tool environment also installs with hashes and passes check.
- Fresh root environment: 1,345 tests passed, 10 skipped, 416 existing warnings.
- API-only environment: real serverless app loads, `/api/health` returns 200,
  protected buyer GET/import routes return 401 without credentials, and Twilio
  9.11.2 is installed. Fallback cold-start service would fail this check. Network
  access, inherited secrets and dotenv loading are disabled by the offline runner.
- All 84 root package wheels were also downloaded for CPython 3.12 Linux x86 with
  verified hashes. This proves artifact availability, not execution on Linux.
- Workflow YAML parses, existing jobs remain, and the lock verifier passes. The
  new remote CI jobs have not run: checkpoint uses skip-CI and candidate Vercel
  deployment exclusions remain. No Docker image was built and no Vercel artifact
  was produced/deployed in this checkpoint.
- Frontend/pipeline application sources and fourteen proposed migrations are
  unchanged. Earlier evidence remains frontend 295/59 files, pipeline 231 and the
  fourteen-migration rehearsal/ten journeys; they were not re-run solely for docs
  or lock formatting. The fresh root suite covers the exact same package versions.

Known-vulnerability scanning is a point-in-time dependency check, not a full app
security audit. Production JWT/tenancy and advisor findings, real platform build/
interpreter/installer verification, deployment artifact/rollback, operator acceptance,
volume/locks, buyer APN/history and live consent/delivery/reply/STOP remain open.
No production schema, data, runtime flags, provider activity or schedules changed.

Ignored logs: `logs/friday-python-*`. Clean environments and downloaded wheels are
under `/private/tmp/wholesaleos-python-*`, disposable and not release artifacts.

## Reproduce deliberately

Use uv 0.13.5 and Python 3.12. Review inputs before compiling; keep API dependencies
constrained to the root lock. Existing lock preferences preserve versions unless
an upgrade is explicitly requested. Regenerate and review hashes for any update.

```sh
uv pip compile requirements.in --python-version 3.12 --python-platform linux --generate-hashes --no-header -o requirements.txt
uv pip compile api/requirements.in -c requirements.txt --python-version 3.12 --python-platform linux --generate-hashes --no-header -o api/requirements.txt
uv pip compile requirements-security.in --python-version 3.12 --python-platform linux --generate-hashes --no-header -o requirements-security.txt
python scripts/release/check_python_locks.py
```

Install each lock separately with `python -m pip install --require-hashes -r FILE`
and run `python -m pip check`. Use the isolated audit environment for
`pip-audit --strict --no-deps --disable-pip -r FILE` against each complete lock.
Run the full root backend suite offline and API smoke script in its API-only
virtual environment; never validate the API boundary using the larger root set.

Primary references: [pip-audit](https://github.com/pypa/pip-audit),
[Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python),
[hash-checked requirements](https://pip.pypa.io/en/stable/topics/secure-installs/),
and [uv pip compile](https://docs.astral.sh/uv/pip/compile/).
