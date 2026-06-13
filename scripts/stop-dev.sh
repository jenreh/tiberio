#!/usr/bin/env bash
#
# Stop the background tiberio server and ngrok tunnel started by run-dev.sh.
#
# Sends SIGTERM to each supervisor (which terminates its child process group),
# then escalates to the recorded process group and finally SIGKILL if needed.
#
# Usage:
#   scripts/stop-dev.sh     (typically via `task stop`)

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_one() {
  local name="$1" pid_file="$2" pgid_file="$3"
  local pid pgid

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    pid="$(cat "$pid_file")"
    echo "🛑 Stopping $name (pid $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
  else
    echo "ℹ️  $name not running."
  fi

  # Also signal the child process group so uvicorn/ngrok exit even if the
  # supervisor was orphaned.
  if [[ -f "$pgid_file" ]]; then
    pgid="$(cat "$pgid_file")"
    kill -TERM "-${pgid}" 2>/dev/null || true
  fi

  if [[ -n "${pid:-}" ]]; then
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "   forcing kill..."
      kill -KILL "$pid" 2>/dev/null || true
      [[ -n "${pgid:-}" ]] && kill -KILL "-${pgid}" 2>/dev/null || true
    fi
  fi

  rm -f "$pid_file" "$pgid_file"
}

stop_one "tunnel" "$RUN_DIR/tunnel.pid" "$RUN_DIR/tunnel.pgid"
stop_one "server" "$RUN_DIR/server.pid" "$RUN_DIR/server.pgid"

echo "✅ Stopped."
