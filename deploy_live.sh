#!/bin/bash
set -euo pipefail

COMMIT_MSG=${1:-"Production deploy"}
export SERVER_IP="${SERVER_IP:-143.47.186.148}"

"$(dirname "$0")/ops/deploy/deploy_env.sh" production main "$COMMIT_MSG"
