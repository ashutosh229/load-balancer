#!/usr/bin/env bash
# Run the two required load experiments and print a comparison summary.
#
# Experiment A – single backend (Sys2 only)
# Experiment B – all three backends (Sys2 + Sys3 + Sys4)
#
# Prerequisites:
#   - Load balancer already running (./scripts/start_lb.sh)
#   - Backends reachable as configured in config/backends.json
#   - Python deps installed (httpx, etc.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# ---------- knobs (override via env) ----------
LB_URL="${LB_URL:-http://10.1.75.79:3205}"
CONCURRENCY="${CONCURRENCY:-50}"
DURATION="${DURATION:-30}"
RESULTS_DIR="${RESULTS_DIR:-${PROJECT_ROOT}/results}"
CONFIG="${PROJECT_ROOT}/config/backends.json"

mkdir -p "${RESULTS_DIR}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=============================================="
echo "  Load-balancer experiments"
echo "  Target LB : ${LB_URL}"
echo "  Concurrency: ${CONCURRENCY}"
echo "  Duration   : ${DURATION}s"
echo "=============================================="

# Helper: temporarily rewrite backends.json to only Sys2
backup_config() {
    cp "${CONFIG}" "${CONFIG}.bak"
}
restore_config() {
    if [[ -f "${CONFIG}.bak" ]]; then
        mv "${CONFIG}.bak" "${CONFIG}"
    fi
}
trap restore_config EXIT

run_one() {
    local label="$1"
    local outfile="${RESULTS_DIR}/${label}_${TIMESTAMP}.json"
    echo ""
    echo ">>> Running experiment: ${label}"
    python3 - <<PY
import asyncio, json, sys
sys.path.insert(0, "${PROJECT_ROOT}")
from load_generator.generator import run_load

summary = asyncio.run(run_load(
    target="${LB_URL}/",          # hit any path; LB proxies it
    concurrency=${CONCURRENCY},
    duration=${DURATION},
))
summary["experiment"] = "${label}"
print(json.dumps(summary, indent=2))
with open("${outfile}", "w") as f:
    json.dump(summary, f, indent=2)
print("Saved → ${outfile}")
PY
}

# ---------- Experiment A: Sys2 only ----------
backup_config
python3 - <<'PY'
import json
from pathlib import Path
cfg_path = Path("config/backends.json")
cfg = json.loads(cfg_path.read_text())
# keep only sys2
cfg["backends"] = [b for b in cfg["backends"] if b["id"] == "sys2"]
cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
print("Backends restricted to Sys2 only. Restart LB if it does not hot-reload config.")
PY

echo ""
echo ">>> IMPORTANT: Restart the load balancer now so it picks up the single-backend config,"
echo "    then press ENTER to continue..."
read -r

run_one "single_backend_sys2"

# ---------- Experiment B: all three backends ----------
restore_config
python3 - <<'PY'
import json
from pathlib import Path
cfg_path = Path("config/backends.json")
# restore already happened via trap, but re-write canonical three-backend config
cfg = {
    "backends": [
        {"id": "sys2", "url": "http://10.1.75.79:3206", "weight": 1},
        {"id": "sys3", "url": "http://10.1.75.79:3207", "weight": 1},
        {"id": "sys4", "url": "http://10.1.75.79:3208", "weight": 1},
    ],
    "health_check_path": "/health",
    "health_check_interval": 5,
    "algorithm": "round_robin",
}
cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
print("Backends restored to Sys2+Sys3+Sys4.")
PY

echo ""
echo ">>> IMPORTANT: Restart the load balancer now so it picks up the three-backend config,"
echo "    then press ENTER to continue..."
read -r

run_one "three_backends"

echo ""
echo "=============================================="
echo "  Experiments finished. Results in ${RESULTS_DIR}"
echo "  Compare the two JSON files and fill the"
echo "  comparison table in your report."
echo "=============================================="