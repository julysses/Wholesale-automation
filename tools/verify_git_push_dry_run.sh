#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "ERROR: not inside a git repository." >&2
  exit 1
fi
cd "$REPO_ROOT"

if [[ -z "${GITHUB_PAT:-${GH_PAT:-}}" ]]; then
  cat >&2 <<'MSG'
ERROR: Missing PAT secret.
Set one of these environment variables before running:
  - GITHUB_PAT (preferred)
  - GH_PAT
MSG
  exit 1
fi

HELPER="$(git config --local --get credential.helper || true)"
if [[ -z "$HELPER" ]]; then
  cat >&2 <<'MSG'
ERROR: credential.helper is not configured. Run first:
  GITHUB_PAT=*** tools/configure_git_pat_credentials.sh
MSG
  exit 1
fi

export GIT_TERMINAL_PROMPT=0

set +e
OUTPUT="$(git push --dry-run origin HEAD 2>&1)"
STATUS=$?
set -e

printf '%s\n' "$OUTPUT"

if [[ $STATUS -eq 0 ]]; then
  echo "VERIFICATION_RESULT: success (dry-run push authenticated)."
else
  echo "VERIFICATION_RESULT: failed (dry-run push was rejected or could not authenticate)." >&2
fi

exit $STATUS
