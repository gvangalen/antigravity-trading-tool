#!/bin/bash
set -euo pipefail

# This is the sole atomic writer for the production release marker. Deployment
# calls it after all health gates pass; independent QA may record the same live
# release again, but never a different checkout.
ENVIRONMENT="${1:-}"
CANDIDATE_COMMIT="${2:-}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/antigravity-trading-tool}"
CANONICAL_DEPLOY_STATE_DIR="${CANONICAL_DEPLOY_STATE_DIR:-/home/ubuntu/ops/deploy}"

if [ "$ENVIRONMENT" != "production" ] || [ -z "$CANDIDATE_COMMIT" ]; then
  echo "Usage: QA_ACCEPTED_RELEASE=true $0 production <full-commit-sha>" >&2
  exit 1
fi
RELEASE_MARKER_REASON="${RELEASE_MARKER_REASON:-qa_accepted}"
case "$RELEASE_MARKER_REASON" in
  deployed)
    if [ "${DEPLOYMENT_VALIDATED_RELEASE:-false}" != "true" ]; then
      echo "❌ Explicit successful deployment validation is required." >&2
      exit 1
    fi
    ;;
  qa_accepted)
    if [ "${QA_ACCEPTED_RELEASE:-false}" != "true" ]; then
      echo "❌ Explicit independent QA acceptance is required." >&2
      exit 1
    fi
    ;;
  *)
    echo "❌ Unknown release-marker reason: $RELEASE_MARKER_REASON" >&2
    exit 1
    ;;
esac
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

echo "✅ Production release marker recorded (${RELEASE_MARKER_REASON}): ${RESOLVED_COMMIT}"
