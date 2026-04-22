#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_SCRIPT="${SCRIPT_DIR}/verify_git_push_dry_run.sh"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "ERROR: not inside a git repository." >&2
  exit 1
fi

cd "$REPO_ROOT"

REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE_URL" ]]; then
  echo "ERROR: git remote 'origin' is not configured." >&2
  exit 1
fi

if [[ "$REMOTE_URL" != https://github.com/* ]]; then
  echo "ERROR: origin must use https://github.com/... for PAT auth. Current: $REMOTE_URL" >&2
  exit 1
fi

if [[ -z "${GITHUB_PAT:-${GH_PAT:-}}" ]]; then
  cat >&2 <<'MSG'
ERROR: Missing PAT secret.
Set one of these environment variables before running:
  - GITHUB_PAT (preferred)
  - GH_PAT
MSG
  exit 1
fi

# Keep credentials non-interactive and avoid on-disk token stores.
# The helper stores only variable references, not token values.
git config --local credential.helper \
  '!f() { if [ "$1" = get ]; then echo username=${GITHUB_USERNAME:-x-access-token}; echo password=${GITHUB_PAT:-${GH_PAT:-}}; fi; }; f'
git config --local --unset-all core.askPass >/dev/null 2>&1 || true
git config --local credential.useHttpPath true
git config --local credential.interactive never

cat <<MSG
Configured repo-local PAT auth for non-interactive git operations.

Repository: $REPO_ROOT
Remote:     $REMOTE_URL
Helper:     credential.helper (env-backed shell helper)

Token was read from environment only and was not written to git config.
MSG

if [[ "${SKIP_GIT_PAT_DRY_RUN:-0}" == "1" ]]; then
  echo
  echo "Skipped dry-run push verification because SKIP_GIT_PAT_DRY_RUN=1."
  exit 0
fi

if [[ ! -x "$VERIFY_SCRIPT" ]]; then
  echo "ERROR: expected executable verify script at $VERIFY_SCRIPT" >&2
  exit 1
fi

echo
echo "Running immediate dry-run push verification..."
"$VERIFY_SCRIPT"
