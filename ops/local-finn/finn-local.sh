#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend/trading-tool-backend"
ENV_FILE="$ROOT/ops/local-finn/finn-local.env"
SECRET_FILE="$HOME/tradamind-local-secrets/finn-development.env"
PID_DIR="$ROOT/.local-finn"
load_env() { set -a; . "$ENV_FILE"; . "$SECRET_FILE"; set +a; }
require_env() { test -r "$ENV_FILE" && test -r "$SECRET_FILE"; }
migrate() { for file in "$BACKEND"/backend/scripts/migrations/*.py; do python3 "$BACKEND/backend/scripts/run_sql_migration.py" "$file"; done; }
case "${1:-}" in
  start)
    require_env; load_env; docker compose -f "$ROOT/docker-compose.finn-local.yml" up -d --wait
    migrate; mkdir -p "$PID_DIR"
    (cd "$BACKEND" && python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 18000) >"$PID_DIR/backend.log" 2>&1 & echo $! >"$PID_DIR/backend.pid"
    (cd "$BACKEND" && celery -A backend.celery_task.celery_app worker --loglevel=info -Ofair --concurrency=1 -Q local-finn-finn_interactive -n local-finn-interactive@%h) >"$PID_DIR/finn-worker.log" 2>&1 & echo $! >"$PID_DIR/finn-worker.pid"
    "$0" health ;;
  health)
    curl -fsS http://127.0.0.1:18000/api/health >/dev/null; docker compose -f "$ROOT/docker-compose.finn-local.yml" ps ;;
  logs) tail -n 100 "$PID_DIR"/*.log ;;
  stop) for f in "$PID_DIR"/*.pid; do test -f "$f" && kill "$(cat "$f")" 2>/dev/null || true; done; docker compose -f "$ROOT/docker-compose.finn-local.yml" down ;;
  reset) "$0" stop; docker compose -f "$ROOT/docker-compose.finn-local.yml" down -v; rm -rf "$PID_DIR" ;;
  *) echo "usage: $0 {start|health|logs|stop|reset}" >&2; exit 2 ;;
esac
