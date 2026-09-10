#!/usr/bin/env bash
#
# Stop services started by scripts/start.sh.
#
# Stops only what this project started, identified by PID file - never by
# scanning a port and killing whatever answers. Port 8501 on a development
# machine is as likely to be somebody else's Streamlit as it is to be ours,
# and "stop my dashboard" should never take down an unrelated project.
#
# USAGE:
#   scripts/stop.sh              # dashboard + api + ollama (if we started it)
#   scripts/stop.sh dashboard
#   scripts/stop.sh api
#   scripts/stop.sh ollama

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/data/run"
GRACE="${PLP_STOP_GRACE:-10}"   # seconds to wait for SIGTERM before SIGKILL

log()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }

pid_file() { echo "$RUN_DIR/$1.pid"; }

stop_service() {
    local name="$1" f pid
    f="$(pid_file "$name")"

    if [ ! -f "$f" ]; then
        log "$name: not running (no pid file)."
        return 0
    fi
    pid="$(cat "$f" 2>/dev/null)"
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        log "$name: not running (stale pid file removed)."
        rm -f "$f"
        return 0
    fi

    log "Stopping $name (pid $pid)..."
    kill "$pid" 2>/dev/null

    local deadline=$((SECONDS + GRACE))
    while [ $SECONDS -lt $deadline ]; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "  $name ignored SIGTERM after ${GRACE}s; sending SIGKILL."
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi

    if kill -0 "$pid" 2>/dev/null; then
        warn "  $name (pid $pid) is still alive. Investigate before retrying."
        return 1
    fi
    rm -f "$f"
    log "  $name stopped."
}

# Ollama is a machine-wide service. Only stop it if start.sh recorded that it
# was the one to start it; otherwise it was already running for some other
# reason and is not ours to shut down.
stop_ollama() {
    if [ ! -f "$RUN_DIR/ollama.owned" ]; then
        if [ -f "$(pid_file ollama)" ]; then
            log "ollama: pid file present but no ownership marker; leaving it running."
        else
            log "ollama: not started by this project - leaving it running."
        fi
        return 0
    fi
    stop_service ollama && rm -f "$RUN_DIR/ollama.owned"
}

TARGET="${1:-all}"
rc=0
case "$TARGET" in
    dashboard) stop_service dashboard || rc=1 ;;
    api)       stop_service api || rc=1 ;;
    ollama)    stop_ollama || rc=1 ;;
    all)
        stop_service dashboard || rc=1
        stop_service api || rc=1
        stop_ollama || rc=1
        ;;
    *)
        warn "ERROR: unknown target '$TARGET'. Use: all | dashboard | api | ollama"
        exit 1
        ;;
esac
exit $rc
