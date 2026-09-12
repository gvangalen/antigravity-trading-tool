#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker-compose.finn-parity.yml")
SECRET_FILE="$HOME/tradamind-local-secrets/finn-development.env"
ARTIFACT_DIR="$ROOT/.local-finn-parity-artifacts"

load_secret() {
  test -r "$SECRET_FILE"
  set -a
  # shellcheck disable=SC1090
  . "$SECRET_FILE"
  set +a
  test -n "${OPENAI_API_KEY:-}"
}

assert_prefork_topology() {
  local id state process_lines
  id="$("${COMPOSE[@]}" ps -q runtime)"
  if [ -z "$id" ]; then
    echo 'missing shared parity runtime' >&2
    return 1
  fi
  state="$(docker inspect --format '{{.State.Status}}/{{.State.OOMKilled}}' "$id")"
  if [ "$state" != "running/false" ]; then
    echo "invalid parity runtime state: $state" >&2
    return 1
  fi
  process_lines="$(docker top "$id" -eo pid,args | tail -n +2)"
  for queue in parity-finn_interactive parity-market_data; do
    if ! printf '%s\n' "$process_lines" | grep -q -- "$queue"; then
      echo "missing required queue process: $queue" >&2
      return 1
    fi
  done
  if [ "$(printf '%s\n' "$process_lines" | grep -c -- '--concurrency=1')" -lt 4 ]; then
    echo 'parity runtime is missing prefork worker children' >&2
    return 1
  fi
  echo 'FINN parity topology: bounded shared runtime with interactive and background prefork workers ready.'
}

case "${1:-}" in
  up)
    load_secret
    mkdir -p "$ARTIFACT_DIR"
    "${COMPOSE[@]}" up --build --detach --wait
    ;;
  down)
    load_secret
    "${COMPOSE[@]}" down --volumes --remove-orphans
    ;;
  matrix)
    load_secret
    assert_prefork_topology
    output="/artifacts/${2:-parity-matrix.json}"
    "${COMPOSE[@]}" exec -T -e FINN_PARITY_TOPOLOGY_ASSERTED=true runtime python backend/scripts/run_finn_v2_nonsealed_parity_matrix.py \
      --base-url http://127.0.0.1:8000 --output "$output" --production-parity
    ;;
  topology)
    load_secret
    assert_prefork_topology
    ;;
  endurance)
    load_secret
    assert_prefork_topology
    output="/artifacts/${2:-runtime-endurance.json}"
    "${COMPOSE[@]}" exec -T -e FINN_PARITY_TOPOLOGY_ASSERTED=true runtime python backend/scripts/run_finn_v2_runtime_endurance.py \
      --base-url http://127.0.0.1:8000 --output "$output"
    ;;
  stats)
    load_secret
    "${COMPOSE[@]}" ps
    docker stats --no-stream $("${COMPOSE[@]}" ps -q)
    ;;
  *)
    echo "usage: $0 {up|down|matrix [artifact-name]|endurance [artifact-name]|topology|stats}" >&2
    exit 2
    ;;
esac
