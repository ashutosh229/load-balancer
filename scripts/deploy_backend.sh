#!/usr/bin/env bash
# Deploy / start the messaging backend on a remote system (Sys2 / Sys3 / Sys4).
#
# Usage:
#   ./scripts/deploy_backend.sh <ssh_port> <app_port> [backend_repo_path]
#
# Examples (your allocation):
#   ./scripts/deploy_backend.sh 2206 3206
#   ./scripts/deploy_backend.sh 2207 3207
#   ./scripts/deploy_backend.sh 2208 3208
#
# Notes:
#   - SSH host is fixed to 10.1.75.79 (lab assignment).
#   - Default backend path: ~/lab_assignments/lab4/group-chat-application
#   - Start command matches your lab:  python app.py
#   - Port is passed via PORT environment variable (and --port if supported).

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <ssh_port> <app_port> [backend_repo_path]"
    echo "  e.g. $0 2206 3206"
    echo "  e.g. $0 2206 3206 ~/lab_assignments/lab4/group-chat-application"
    exit 1
fi

SSH_PORT="$1"
APP_PORT="$2"
BACKEND_PATH="${3:-~/lab_assignments/lab4/group-chat-application}"
SSH_HOST="10.1.75.79"
SSH_USER="${SSH_USER:-student}"

echo "=============================================="
echo "  Deploy messaging backend"
echo "  Host: ${SSH_USER}@${SSH_HOST}:${SSH_PORT}"
echo "  App port: ${APP_PORT}"
echo "  Backend path: ${BACKEND_PATH}"
echo "=============================================="

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

# Also stop any previous group-chat process we started
if [[ -f /tmp/messaging-backend-${APP_PORT}.pid ]]; then
    old_pid=\$(cat /tmp/messaging-backend-${APP_PORT}.pid)
    kill "\$old_pid" 2>/dev/null || true
    rm -f /tmp/messaging-backend-${APP_PORT}.pid
fi

# Start the messaging backend the same way you do manually:
#   python app.py
# Port is supplied via PORT env var (common pattern). If your app.py
# ignores PORT and hard-codes a port, edit app.py to read:
#   port = int(os.environ.get("PORT", 5000))
export PORT=${APP_PORT}
nohup python app.py \
    > /tmp/messaging-backend-${APP_PORT}.log 2>&1 &
echo \$! > /tmp/messaging-backend-${APP_PORT}.pid
echo "Backend started on port ${APP_PORT} (PID \$(cat /tmp/messaging-backend-${APP_PORT}.pid))"
echo "Log: /tmp/messaging-backend-${APP_PORT}.log"
EOF

echo "Done. Verify with:"
echo "  curl -s http://${SSH_HOST}:${APP_PORT}/health || curl -s http://${SSH_HOST}:${APP_PORT}/"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} 'tail -20 /tmp/messaging-backend-${APP_PORT}.log'"