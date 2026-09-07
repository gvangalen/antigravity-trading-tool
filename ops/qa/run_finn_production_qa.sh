#!/usr/bin/env bash
# Start the protected FINN production-QA workflow without SSH access.
set -euo pipefail

usage() {
  echo "Usage: $0 <release_sha> <qa_profile> <manifest_id|none> <run_label> [encrypted_manifest_bundle]" >&2
  exit 2
}

[[ $# -eq 4 || $# -eq 5 ]] || usage
release_sha="$1"
qa_profile="$2"
manifest_id="$3"
run_label="$4"
manifest_bundle_path="${5:-}"
allow_fixture_actions="${FINN_QA_ALLOW_FIXTURE_ACTIONS:-false}"
allow_safe_fixture_execution="${FINN_QA_ALLOW_FIXTURE_EXECUTION:-false}"

[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] || usage
[[ "$qa_profile" =~ ^(auth_preflight|manifest_key|targeted_regression|runtime_acceptance|full_release_acceptance|safety|latency)$ ]] || usage
[[ "$manifest_id" =~ ^[a-z0-9][a-z0-9._-]{0,80}$ ]] || usage
[[ "$run_label" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] || usage
[[ "$allow_fixture_actions" =~ ^(true|false)$ ]] || usage
[[ "$allow_safe_fixture_execution" =~ ^(true|false)$ ]] || usage
if [[ "$allow_safe_fixture_execution" == "true" && "$allow_fixture_actions" != "true" ]]; then
  usage
fi

args=(
  -f "release_sha=$release_sha" \
  -f "qa_profile=$qa_profile" \
  -f "manifest_id=$manifest_id" \
  -f "run_label=$run_label"
  -f "allow_fixture_actions=$allow_fixture_actions"
  -f "allow_safe_fixture_execution=$allow_safe_fixture_execution"
)
if [[ -n "$manifest_bundle_path" ]]; then
  [[ -r "$manifest_bundle_path" ]] || usage
  args+=(-f "manifest_bundle=$(<"$manifest_bundle_path")")
fi

gh workflow run finn-production-qa.yml "${args[@]}"

echo "Workflow requested. Follow it with: gh run list --workflow finn-production-qa.yml --limit 1"
