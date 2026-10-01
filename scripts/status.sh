#!/usr/bin/env bash
#
# One line per service: whether it is running, its pid, its port, and the last
# line of its log. Read-only - starts and stops nothing.
#
# USAGE:
#   scripts/status.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/data/run"
LOG_DIR="$ROOT/data/logs"
DASHBOARD_PORT="${PLP_DASHBOARD_PORT:-8501}"
API_PORT="${PLP_API_PORT:-8000}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

running_pid() {
    local f="$RUN_DIR/$1.pid" pid
    [ -f "$f" ] || return 1
    pid="$(cat "$f" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo "$pid"
}

last_log() {
    local f="$LOG_DIR/$1.log"
    [ -f "$f" ] || { echo "(no log)"; return; }
    # Trim to keep the status table readable; the full log is on disk.
    tail -n 1 "$f" 2>/dev/null | cut -c1-70 | tr -d '\r' || echo "(empty)"
}

report() {
    local name="$1" port="$2" health="$3" pid state
    if pid="$(running_pid "$name")"; then
        if curl -fsS -o /dev/null -m 3 "$health" 2>/dev/null; then
            state="running   healthy"
        else
            state="running   NOT healthy"
        fi
    else
        pid="-"
        # A port held while we have no pid file means somebody else's process.
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
            state="stopped   port $port held by another process"
        else
            state="stopped"
        fi
    fi
    printf '%-10s %-8s %-8s %s\n' "$name" "$pid" "$port" "$state"
    printf '           last log: %s\n' "$(last_log "$name")"
}

printf '%-10s %-8s %-8s %s\n' SERVICE PID PORT STATE
printf '%s\n' "-------------------------------------------------------------------"
report dashboard "$DASHBOARD_PORT" "http://localhost:$DASHBOARD_PORT/_stcore/health"
report api       "$API_PORT"       "http://localhost:$API_PORT/health"

# Ollama is reported by reachability rather than pid, because it is usually
# machine-wide and not started by this project.
if curl -fsS -o /dev/null -m 3 "$OLLAMA_URL/api/tags" 2>/dev/null; then
    owned="(not started by this project)"
    [ -f "$RUN_DIR/ollama.owned" ] && owned="(started by scripts/start.sh)"
    printf '%-10s %-8s %-8s %s\n' ollama "$(running_pid ollama || echo -)" 11434 \
        "reachable $owned"
else
    printf '%-10s %-8s %-8s %s\n' ollama - 11434 "not reachable at $OLLAMA_URL"
fi
