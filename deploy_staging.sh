#!/bin/bash
set -euo pipefail

COMMIT_MSG=${1:-"Staging deploy"}
export SERVER_IP="${SERVER_IP:-${STAGING_SERVER_IP:-}}"

"$(dirname "$0")/ops/deploy/deploy_env.sh" staging develop "$COMMIT_MSG"
