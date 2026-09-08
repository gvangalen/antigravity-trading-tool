#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend/trading-tool-backend"
ENV_FILE="$ROOT/ops/local-finn/finn-local.env"
SECRET_FILE="$HOME/tradamind-local-secrets/finn-development.env"
PID_DIR="$ROOT/.local-finn"
load_env() { set -a; . "$ENV_FILE"; . "$SECRET_FILE"; set +a; }
require_env() { test -r "$ENV_FILE" && test -r "$SECRET_FILE"; }
migrate() { (cd "$BACKEND" && PYTHONPATH=. python3 backend/scripts/bootstrap_local_finn_schema.py); for file in "$BACKEND"/backend/scripts/migrations/*.py; do PYTHONPATH="$BACKEND" python3 "$BACKEND/backend/scripts/run_sql_migration.py" "$file"; done; }
spawn_detached() {
  local log_file="$1" pid_file="$2"; shift 2
  (cd "$BACKEND" && nohup python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' "$@") >"$log_file" 2>&1 &
  echo $! >"$pid_file"
}
case "${1:-}" in
  start)
    require_env; load_env; docker compose -f "$ROOT/docker-compose.finn-local.yml" up -d --wait
    migrate; mkdir -p "$PID_DIR"
    spawn_detached "$PID_DIR/backend.log" "$PID_DIR/backend.pid" python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 18000
    # macOS Python 3.13 extension modules are not fork-safe. Keep the production
    # Celery app and queue path, but use its supported single-process pool locally.
    spawn_detached "$PID_DIR/finn-worker.log" "$PID_DIR/finn-worker.pid" celery -A backend.celery_task.celery_app worker --pool=solo --loglevel=info -Ofair --concurrency=1 -Q local-finn-finn_interactive -n local-finn-interactive@%h
    for _ in $(seq 1 30); do
      if curl -fsS http://127.0.0.1:18000/api/health >/dev/null; then "$0" health; exit 0; fi
      sleep 1
    done
    echo "local_finn_backend_start_timeout" >&2; exit 1 ;;
  health)
    curl -fsS http://127.0.0.1:18000/api/health >/dev/null; docker compose -f "$ROOT/docker-compose.finn-local.yml" ps ;;
  logs) tail -n 100 "$PID_DIR"/*.log ;;
  stop) for f in "$PID_DIR"/*.pid; do test -f "$f" && kill "$(cat "$f")" 2>/dev/null || true; done; docker compose -f "$ROOT/docker-compose.finn-local.yml" down ;;
  reset) "$0" stop; docker compose -f "$ROOT/docker-compose.finn-local.yml" down -v; rm -rf "$PID_DIR" ;;
  *) echo "usage: $0 {start|health|logs|stop|reset}" >&2; exit 2 ;;
esac
