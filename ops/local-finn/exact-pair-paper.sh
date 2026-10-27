#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend/trading-tool-backend"
ENV_FILE="$ROOT/ops/local-finn/finn-local.env"
LOG_DIR="$ROOT/.local-finn"

test -r "$ENV_FILE"
set -a
. "$ENV_FILE"
set +a
test "$APP_ENV" = local_finn
test "$DB_HOST" = 127.0.0.1
test "$DB_PORT" = 55432
test "$DB_NAME" = finn_local
test "$CELERY_BROKER_URL" = redis://127.0.0.1:56379/0

"$ROOT/ops/local-finn/finn-local.sh" health >/dev/null
mkdir -p "$LOG_DIR"

(
  cd "$BACKEND"
  TRADAMIND_BUILD_SERVICE=score2-positive-paper TRADAMIND_CELERY_PROFILE=full \
    celery -A backend.celery_task.celery_app worker --pool=solo \
      --concurrency=1 --loglevel=warning -Q local-finn-score2-positive-paper \
      -n "local-score2-positive-paper-$$@%h"
) >"$LOG_DIR/exact-pair-paper-worker.log" 2>&1 &
worker_pid=$!
cleanup() {
  kill "$worker_pid" 2>/dev/null || true
  wait "$worker_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND"
  TRADAMIND_CELERY_PROFILE=api PYTHONPATH=. \
    python3 backend/scripts/probe_local_exact_pair_paper.py
)
