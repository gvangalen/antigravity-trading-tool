#!/bin/bash
set -euo pipefail

ROLLBACK_COMMIT="${1:-}"
"$(dirname "$0")/ops/deploy/rollback_env.sh" staging "$ROLLBACK_COMMIT"
