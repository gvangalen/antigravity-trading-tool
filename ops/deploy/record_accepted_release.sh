#!/bin/bash
set -euo pipefail

# This is the sole writer for the production rollback marker. It is invoked
# only after independent QA has explicitly accepted the release.
ENVIRONMENT="${1:-}"
CANDIDATE_COMMIT="${2:-}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/antigravity-trading-tool}"
CANONICAL_DEPLOY_STATE_DIR="${CANONICAL_DEPLOY_STATE_DIR:-/home/ubuntu/ops/deploy}"

if [ "$ENVIRONMENT" != "production" ] || [ -z "$CANDIDATE_COMMIT" ]; then
  echo "Usage: QA_ACCEPTED_RELEASE=true $0 production <full-commit-sha>" >&2
  exit 1
fi
if [ "${QA_ACCEPTED_RELEASE:-false}" != "true" ]; then
  echo "❌ Explicit independent QA acceptance is required." >&2
  exit 1
fi
if ! [[ "$CANDIDATE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "❌ Candidate must be a full 40-character commit SHA." >&2
  exit 1
fi

cd "$REMOTE_DIR"
RESOLVED_COMMIT="$(git rev-parse --verify "${CANDIDATE_COMMIT}^{commit}")"
LIVE_COMMIT="$(git rev-parse HEAD)"
if [ "$RESOLVED_COMMIT" != "$LIVE_COMMIT" ]; then
  echo "❌ Candidate is not the currently deployed commit." >&2
  exit 1
fi

sudo mkdir -p "$CANONICAL_DEPLOY_STATE_DIR"
sudo sh -c '
  set -eu
  target="$1/LAST_GOOD_COMMIT"
  temporary="$(mktemp "$1/.LAST_GOOD_COMMIT.XXXXXX")"
  printf "%s\n" "$2" > "$temporary"
  mv -f "$temporary" "$target"
' sh "$CANONICAL_DEPLOY_STATE_DIR" "$RESOLVED_COMMIT"

echo "✅ Independent-QA accepted release recorded: ${RESOLVED_COMMIT}"
