#!/bin/bash
set -euo pipefail

echo "❌ deploy.sh is deprecated and intentionally blocked."
echo "Use one of the supported environment-specific entry points instead:"
echo "  ./deploy_live.sh \"Production deploy\""
echo "  ./deploy_staging.sh \"Staging deploy\""
echo
echo "Shared implementation lives in:"
echo "  ./ops/deploy/deploy_env.sh <environment> <branch> [commit message]"
exit 1
