#!/bin/bash
set -euo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"
STATE_DIR="${REPO_ROOT}/ops/deploy/.runtime-deps"
BACKEND_REQUIREMENTS="${REPO_ROOT}/backend/trading-tool-backend/backend/requirements.txt"
FRONTEND_DIR="${REPO_ROOT}/frontend/trading-tool-frontend"
FRONTEND_LOCKFILE="${FRONTEND_DIR}/package-lock.json"

mkdir -p "${STATE_DIR}"

backend_hash_file="${STATE_DIR}/backend-requirements.sha256"
frontend_hash_file="${STATE_DIR}/frontend-package-lock.sha256"
playwright_hash_file="${STATE_DIR}/playwright-chromium.sha256"

file_hash() {
  sha256sum "$1" | awk '{print $1}'
}

python_modules_ok() {
  python3 - <<'PY'
import importlib.util
import sys

required = ("email_validator", "playwright")
missing = [name for name in required if importlib.util.find_spec(name) is None]
sys.exit(1 if missing else 0)
PY
}

backend_hash="$(file_hash "${BACKEND_REQUIREMENTS}")"
frontend_hash="$(file_hash "${FRONTEND_LOCKFILE}")"

backend_needs_install=false
if [ ! -f "${backend_hash_file}" ] || [ "$(cat "${backend_hash_file}")" != "${backend_hash}" ]; then
  backend_needs_install=true
elif ! python_modules_ok; then
  backend_needs_install=true
fi

if [ "${backend_needs_install}" = "true" ]; then
  echo "📦 Installing backend Python dependencies..."
  python3 -m pip install -r "${BACKEND_REQUIREMENTS}"
  printf '%s\n' "${backend_hash}" > "${backend_hash_file}"
fi

frontend_needs_install=false
if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
  frontend_needs_install=true
elif [ ! -f "${frontend_hash_file}" ] || [ "$(cat "${frontend_hash_file}")" != "${frontend_hash}" ]; then
  frontend_needs_install=true
fi

if [ "${frontend_needs_install}" = "true" ]; then
  echo "📦 Installing frontend Node dependencies..."
  (
    cd "${FRONTEND_DIR}"
    npm ci --no-audit --no-fund
  )
  printf '%s\n' "${frontend_hash}" > "${frontend_hash_file}"
fi

playwright_needs_install=false
if [ ! -f "${playwright_hash_file}" ] || [ "$(cat "${playwright_hash_file}")" != "${backend_hash}" ]; then
  playwright_needs_install=true
fi

if [ "${playwright_needs_install}" = "true" ]; then
  echo "🎭 Ensuring Playwright Chromium runtime is installed..."
  python3 -m playwright install chromium
  printf '%s\n' "${backend_hash}" > "${playwright_hash_file}"
fi

