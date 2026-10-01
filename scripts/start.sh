#!/usr/bin/env bash
#
# Start the dashboard, the REST API, and (if needed) Ollama.
#
# WHY THIS EXISTS: the manual commands in docs/RUNBOOK.md are the reference
# for what these services are, and they are easy to get subtly wrong - the
# wrong interpreter fails every import with a Python 3.9 syntax error, and a
# missing HF_HUB_OFFLINE=1 makes FinBERT steps appear to hang on a network
# wait. This script encodes both, refuses to start on a port somebody else is
# using, and waits for a real health check rather than reporting success the
# moment a process exists.
#
# USAGE:
#   scripts/start.sh              # dashboard + api + ollama if needed
#   scripts/start.sh dashboard    # just one service
#   scripts/start.sh api
#   scripts/start.sh ollama
#
#   PLP_DASHBOARD_PORT=8502 scripts/start.sh dashboard
#   PLP_API_PORT=8100 scripts/start.sh api
#
# Stop what this starts with scripts/stop.sh; see scripts/status.sh for state.

set -uo pipefail

# Resolve the project root from this script's own location so the script works
# from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv-plp/bin/python3"
RUN_DIR="$ROOT/data/run"
LOG_DIR="$ROOT/data/logs"
DASHBOARD_PORT="${PLP_DASHBOARD_PORT:-8501}"
API_PORT="${PLP_API_PORT:-8000}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
HEALTH_TIMEOUT="${PLP_HEALTH_TIMEOUT:-90}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# FinBERT steps stall on a HuggingFace metadata check even when the model is
# cached; see docs/RUNBOOK.md.
export HF_HUB_OFFLINE=1

# .env carries API keys and logging config, exported so child processes see it.
#
# Parsed line by line rather than sourced. `. .env` executes the file as shell,
# so an unquoted value containing spaces becomes a command: .env.example ships
# with `REDDIT_USER_AGENT=plp-practice-module/0.1 by u/your_username`, which
# sourcing turns into an attempt to run `by`. Python's dotenv (which the rest
# of the codebase uses) accepts that line happily, so the file is not
# malformed - shell is simply the wrong parser for it.
load_dotenv() {
    local file="$1" line key value
    [ -f "$file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip a trailing CR so a file saved on Windows still parses.
        line="${line%$'\r'}"
        case "$line" in
            ''|'#'*) continue ;;
            *'='*) ;;
            *) continue ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        key="${key#"${key%%[![:space:]]*}"}"   # ltrim
        key="${key%"${key##*[![:space:]]}"}"   # rtrim
        # `export FOO=bar` in a .env is common enough to tolerate.
        key="${key#export }"
        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
        # Drop one layer of matching surrounding quotes, if present.
        if [[ "$value" == \"*\" && ${#value} -ge 2 ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "$value" == \'*\' && ${#value} -ge 2 ]]; then
            value="${value:1:${#value}-2}"
        fi
        export "$key=$value"
    done < "$file"
}
load_dotenv "$ROOT/.env"

log()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- Environment guard -------------------------------------------------------
# A conda/miniforge Python 3.9 on PATH shadows the venv and fails every import
# with `TypeError: unsupported operand type(s) for |`, because this codebase
# uses PEP 604 syntax throughout. One overnight run was already lost this way,
# so fail loudly here rather than in the middle of a service.
check_environment() {
    [ -x "$PY" ] || die "no interpreter at $PY - create it with:
  python3 -m venv .venv-plp && .venv-plp/bin/python3 -m pip install -r requirements.txt"

    "$PY" - <<'EOF' || die "the interpreter at .venv-plp/bin/python3 is not usable (see above)"
import sys
if sys.version_info < (3, 10):
    sys.exit(f"FATAL: Python {sys.version.split()[0]} at {sys.executable}; this codebase "
             "needs 3.10+ (it uses `X | None` syntax throughout).")
try:
    import torch  # noqa: F401
except ImportError:
    sys.exit(f"FATAL: torch is not importable under {sys.executable} - dependencies are "
             "missing. Run: .venv-plp/bin/python3 -m pip install -r requirements.txt")
EOF
}

# --- Process helpers ---------------------------------------------------------
pid_file()  { echo "$RUN_DIR/$1.pid"; }
log_file()  { echo "$LOG_DIR/$1.log"; }

# PID from our pidfile, only if that process is actually alive. Empty otherwise,
# so a stale pidfile from a killed process never blocks a restart.
running_pid() {
    local f; f="$(pid_file "$1")"
    [ -f "$f" ] || return 1
    local pid; pid="$(cat "$f" 2>/dev/null)"
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    echo "$pid"
}

port_pids() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null; }

# Refuse to touch a port we do not own. Ports 8000 and 8501 on this machine are
# routinely held by an unrelated project, and killing it would be an
# unpleasant surprise; say who owns it and let the user decide.
assert_port_free_or_ours() {
    local service="$1" port="$2"
    local pids; pids="$(port_pids "$port")"
    [ -n "$pids" ] || return 0

    local ours; ours="$(running_pid "$service" || true)"
    for pid in $pids; do
        if [ -n "$ours" ] && [ "$pid" = "$ours" ]; then continue; fi
        warn "Port $port is already in use by a process this script did not start:"
        ps -p "$pid" -o pid=,command= >&2 || true
        die "refusing to start $service. Stop that process, or choose another port:
  PLP_$(echo "$service" | tr '[:lower:]' '[:upper:]')_PORT=<port> scripts/start.sh $service"
    done
}

# Poll a URL until it answers 200, or give up. Reporting success on process
# existence alone is how you get a green start message and a broken service.
wait_for_http() {
    local url="$1" name="$2" pid="$3" deadline=$((SECONDS + HEALTH_TIMEOUT))
    while [ $SECONDS -lt $deadline ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            warn "$name exited during startup. Last lines of its log:"
            tail -n 15 "$(log_file "$name")" >&2 || true
            return 1
        fi
        if curl -fsS -o /dev/null -m 3 "$url" 2>/dev/null; then return 0; fi
        sleep 1
    done
    warn "$name did not become healthy within ${HEALTH_TIMEOUT}s ($url). Last lines:"
    tail -n 15 "$(log_file "$name")" >&2 || true
    return 1
}

start_service() {
    local name="$1" port="$2" health_url="$3"; shift 3
    local pid
    if pid="$(running_pid "$name")"; then
        log "$name already running (pid $pid, port $port) - leaving it alone."
        return 0
    fi
    assert_port_free_or_ours "$name" "$port"

    log "Starting $name on port $port..."
    nohup "$@" >>"$(log_file "$name")" 2>&1 &
    pid=$!
    echo "$pid" > "$(pid_file "$name")"

    if wait_for_http "$health_url" "$name" "$pid"; then
        log "  $name ready: pid $pid, log $(log_file "$name")"
        return 0
    fi
    rm -f "$(pid_file "$name")"
    return 1
}

# --- Services ----------------------------------------------------------------
start_dashboard() {
    start_service dashboard "$DASHBOARD_PORT" \
        "http://localhost:$DASHBOARD_PORT/_stcore/health" \
        "$PY" -m streamlit run dashboard/app.py \
            --server.port "$DASHBOARD_PORT" --server.headless true \
    && log "  Dashboard: http://localhost:$DASHBOARD_PORT"
}

start_api() {
    start_service api "$API_PORT" \
        "http://localhost:$API_PORT/health" \
        "$PY" -m uvicorn api.main:app --port "$API_PORT" \
    && log "  API: http://localhost:$API_PORT  (docs at /docs)"
}

# Ollama is shared machine-wide, not owned by this project. If it is already
# answering, leave it completely alone. If we start it, record that so stop.sh
# knows it may shut it down - and knows not to when somebody else's session
# started it.
start_ollama() {
    if curl -fsS -o /dev/null -m 3 "$OLLAMA_URL/api/tags" 2>/dev/null; then
        log "Ollama already running at $OLLAMA_URL - leaving it alone."
        return 0
    fi
    if ! command -v ollama >/dev/null 2>&1; then
        warn "Ollama is not installed, so the local chatbot backend will not work."
        warn "Install it from https://ollama.com, or set an API key in .env for a hosted backend."
        return 0
    fi
    log "Starting Ollama..."
    nohup ollama serve >>"$(log_file ollama)" 2>&1 &
    local pid=$!
    echo "$pid" > "$(pid_file ollama)"
    touch "$RUN_DIR/ollama.owned"

    if wait_for_http "$OLLAMA_URL/api/tags" ollama "$pid"; then
        log "  Ollama ready: pid $pid"
        return 0
    fi
    rm -f "$(pid_file ollama)" "$RUN_DIR/ollama.owned"
    return 1
}

# --- Main --------------------------------------------------------------------
TARGET="${1:-all}"

# Validate the target BEFORE check_environment. The environment check imports
# torch, which costs several seconds; making a typo'd service name wait for
# that before being told it is a typo is pure annoyance.
case "$TARGET" in
    all|dashboard|api|ollama) ;;
    *) die "unknown target '$TARGET'. Use: all | dashboard | api | ollama" ;;
esac

# Ollama needs neither the venv nor torch, so do not gate it on them.
[ "$TARGET" = "ollama" ] || check_environment

rc=0
case "$TARGET" in
    dashboard) start_dashboard || rc=1 ;;
    api)       start_api || rc=1 ;;
    ollama)    start_ollama || rc=1 ;;
    all)
        # Ollama first: the dashboard's Chat tab needs it, and it is the
        # slowest to become ready.
        start_ollama || rc=1
        start_api || rc=1
        start_dashboard || rc=1
        ;;
esac

[ $rc -eq 0 ] && log "" && log "Run scripts/status.sh to check, scripts/stop.sh to stop."
exit $rc
