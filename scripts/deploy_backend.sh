#!/usr/bin/env bash
# Deploy / start the messaging backend on a remote system (Sys2 / Sys3 / Sys4).
#
# Usage:
#   ./scripts/deploy_backend.sh <ssh_port> <app_port> [backend_repo_path]
#
# Example (Sys2):
#   ./scripts/deploy_backend.sh 2206 3206 ~/messaging-backend
#
# Notes:
#   - SSH host is fixed to 10.1.75.79 (lab assignment).
#   - Application port = SSH port + 1000 * AppNumber (App1 → +1000).
#   - The backend itself is the messaging app from the previous lab;
#     this script only starts it on the correct port.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <ssh_port> <app_port> [backend_repo_path]"
    echo "  e.g. $0 2206 3206 ~/messaging-backend"
    exit 1
fi

SSH_PORT="$1"
APP_PORT="$2"
BACKEND_PATH="${3:-~/messaging-backend}"
SSH_HOST="10.1.75.79"
SSH_USER="${SSH_USER:-student}"   # override if your lab username differs

echo "=============================================="
echo "  Deploy messaging backend"
echo "  Host: ${SSH_USER}@${SSH_HOST}:${SSH_PORT}"
echo "  App port: ${APP_PORT}"
echo "  Backend path: ${BACKEND_PATH}"
echo "=============================================="

# Start (or restart) the FastAPI messaging backend on the remote container.
# Adjust the start command to match your previous-lab backend entrypoint.
ssh -p "${SSH_PORT}" "${SSH_USER}@${SSH_HOST}" bash -s <<EOF
set -euo pipefail
cd ${BACKEND_PATH}

# Prefer a virtualenv if present
if [[ -d .venv ]]; then
    source .venv/bin/activate
elif [[ -d venv ]]; then
    source venv/bin/activate
fi

# Kill any previous instance listening on the target port
if command -v fuser &>/dev/null; then
    fuser -k ${APP_PORT}/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
    pid=\$(lsof -t -i:${APP_PORT} 2>/dev/null || true)
    [[ -n "\$pid" ]] && kill \$pid 2>/dev/null || true
fi

# Start the messaging backend (adjust module path if needed)
nohup uvicorn main:app --host 0.0.0.0 --port ${APP_PORT} \
    > /tmp/messaging-backend-${APP_PORT}.log 2>&1 &
echo \$! > /tmp/messaging-backend-${APP_PORT}.pid
echo "Backend started on port ${APP_PORT} (PID \$(cat /tmp/messaging-backend-${APP_PORT}.pid))"
EOF

echo "Done. Health check (from this machine):"
echo "  curl -s http://${SSH_HOST}:${APP_PORT}/health || true"