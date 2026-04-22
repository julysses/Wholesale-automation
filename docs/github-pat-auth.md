# GitHub PAT Authentication for Agent Push Access

This project uses PAT-based HTTPS authentication for non-interactive git push operations in agent runtime.

## Security model

- Token is injected from runtime secret storage (`GITHUB_PAT` or `GH_PAT`).
- Token is not written to repository files.
- Token is not embedded in git remote URL.
- Git uses a repo-local env-backed credential helper that reads token at runtime.

## One-time setup per checkout

```bash
GITHUB_PAT=*** tools/configure_git_pat_credentials.sh
```

`tools/configure_git_pat_credentials.sh` now runs the dry-run push verification immediately after credential setup by default.

The script sets repository-local git config keys:

- `credential.helper` = shell helper that emits username/password from env vars
- `credential.useHttpPath` = `true`
- `credential.interactive` = `never`

## Verification (safe)

```bash
GITHUB_PAT=*** tools/verify_git_push_dry_run.sh
```

This runs `git push --dry-run origin HEAD` with non-interactive auth (`GIT_TERMINAL_PROMPT=0`).

If you need to configure without verification in a constrained environment, set:

```bash
SKIP_GIT_PAT_DRY_RUN=1 GITHUB_PAT=*** tools/configure_git_pat_credentials.sh
```

## Rotation

1. Create a new fine-grained PAT in GitHub for the target repo with `Contents: Read and write`.
2. Update runtime secret value for `GITHUB_PAT`.
3. Re-run:

```bash
GITHUB_PAT=*** tools/configure_git_pat_credentials.sh
GITHUB_PAT=*** tools/verify_git_push_dry_run.sh
```

4. Revoke the old token after verification succeeds.

## Revocation response

If compromise is suspected:

1. Revoke the PAT immediately in GitHub.
2. Remove/replace runtime `GITHUB_PAT` secret.
3. Re-run dry-run verification with a newly issued token.
4. Audit recent pushes and repository activity.
