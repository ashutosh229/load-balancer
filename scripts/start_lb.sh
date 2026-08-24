#!/usr/bin/env bash
# Start the Messaging Load Balancer on Sys1.
#
# Usage:
#   ./scripts/start_lb.sh [HOST] [PORT]
#
# Defaults:
#   HOST = 0.0.0.0
#   PORT = 3205   (App1 port derived from SSH 2205 → 2205 + 1000)
#
# Prerequisites:
#   - Python 3.10+
#   - Virtualenv with requirements installed (see README)
#   - config/backends.json configured with reachable backend URLs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

HOST="${1:-0.0.0.0}"
PORT="${2:-3205}"

export PYTHONPATH="${PROJECT_ROOT}/load_balancer:${PYTHONPATH:-}"

echo "=============================================="
echo "  Messaging Load Balancer"
echo "  Listening on ${HOST}:${PORT}"
echo "  Config: config/backends.json"
echo "=============================================="

exec uvicorn main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --app-dir "${PROJECT_ROOT}/load_balancer" \
    --log-level info \
    --access-log