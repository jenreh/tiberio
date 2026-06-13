#!/usr/bin/env bash
#
# Start the tiberio FastAPI server and the ngrok tunnel in the background.
#
# Each process is wrapped by scripts/dev_supervisor.py, which streams its
# combined output into a log file that rotates at 5 MB. PIDs and process-group
# ids are recorded under .run/ so that `task stop` can terminate them.
#
# Usage:
#   scripts/run-dev.sh      (typically via `task run`)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/.run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

MAX_BYTES=$((5 * 1024 * 1024))
SUPERVISOR=("uv" "run" "python" "$ROOT_DIR/scripts/dev_supervisor.py")

SERVER_PID_FILE="$RUN_DIR/server.pid"
SERVER_PGID_FILE="$RUN_DIR/server.pgid"
TUNNEL_PID_FILE="$RUN_DIR/tunnel.pid"
TUNNEL_PGID_FILE="$RUN_DIR/tunnel.pgid"

running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

if running "$SERVER_PID_FILE" || running "$TUNNEL_PID_FILE"; then
  echo "⚠️  Already running. Run 'task stop' first." >&2
  exit 1
fi

echo "🚀 Starting FastAPI server on :3040 (logs → logs/server.log)..."
nohup "${SUPERVISOR[@]}" \
  --log-file "$LOG_DIR/server.log" \
  --max-bytes "$MAX_BYTES" \
  --pgid-file "$SERVER_PGID_FILE" \
  -- uv run uvicorn tiberio.api.app:create_app --reload --factory \
  --host 0.0.0.0 --port 3040 \
  >/dev/null 2>&1 &
echo $! >"$SERVER_PID_FILE"

echo "🌐 Starting ngrok tunnel (logs → logs/tunnel.log)..."
nohup "${SUPERVISOR[@]}" \
  --log-file "$LOG_DIR/tunnel.log" \
  --max-bytes "$MAX_BYTES" \
  --pgid-file "$TUNNEL_PGID_FILE" \
  -- task tunnel \
  >/dev/null 2>&1 &
echo $! >"$TUNNEL_PID_FILE"

echo "✅ Started — server pid $(cat "$SERVER_PID_FILE"), tunnel pid $(cat "$TUNNEL_PID_FILE")."
echo "   Tail logs: tail -f logs/server.log logs/tunnel.log"
echo "   Stop:      task stop"
