#!/usr/bin/env bash
# Separate data/model folders, project-scoped caches and ports. Never resets the real DB.
# macOS/Linux: bash scripts/docker-clean-test.sh [project-name] [--resume]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="${1:-plp-clean-$(date +%Y%m%d%H%M%S)}"
if [[ ! "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
    echo "Use a project name containing lowercase letters, digits, dashes or underscores." >&2
    exit 1
fi
TEST_ROOT="$ROOT/.docker-test/$PROJECT"
if [[ -e "$TEST_ROOT" && "${2:-}" != "--resume" ]]; then
    echo "Test directory already exists. Choose a new project name for a fresh test, or add --resume." >&2
    exit 1
fi
if [[ ! -e "$TEST_ROOT" && ! -f "$ROOT/data/data.zip" ]]; then
    echo "Place the supplied bundle at data/data.zip before running the clean-install test." >&2
    exit 1
fi
if [[ ! -e "$TEST_ROOT" ]]; then
    mkdir -p "$TEST_ROOT/data" "$TEST_ROOT/models"
    cp "$ROOT/data/data.zip" "$TEST_ROOT/data/data.zip"
    for folder in earnings_pdfs sgx_research glossary; do
        if [[ -d "$ROOT/data/$folder" ]]; then
            cp -R "$ROOT/data/$folder" "$TEST_ROOT/data/$folder"
        fi
    done
fi
export PLP_DATA_DIR="$TEST_ROOT/data"
export PLP_MODELS_DIR="$TEST_ROOT/models"
export PLP_API_PORT="${PLP_TEST_API_PORT:-8100}"
export PLP_DASHBOARD_PORT="${PLP_TEST_DASHBOARD_PORT:-8502}"
# The base file intentionally uses containerised Ollama and new project-scoped caches.
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/compose.yaml")
echo "Clean install: $PROJECT"
echo "Data/model files: $TEST_ROOT"
echo "Dashboard: http://localhost:$PLP_DASHBOARD_PORT"
echo "API docs: http://localhost:$PLP_API_PORT/docs"
echo "First startup downloads models into separate storage and may take several minutes."
echo "The normal .env supplies API keys, but existing databases, venvs and model caches are not mounted."
echo "Do not start the same project with different data-directory settings."
"${COMPOSE[@]}" up -d --build --wait --wait-timeout 3600
"${COMPOSE[@]}" exec -T api python -m docker.smoke
echo "Clean-install checks passed. Test containers remain running for review."
echo "Restart test: run this command from the project root:"
printf 'PLP_DATA_DIR=%q PLP_MODELS_DIR=%q PLP_API_PORT=%q PLP_DASHBOARD_PORT=%q docker compose -p %q -f compose.yaml up -d --wait\n' "$PLP_DATA_DIR" "$PLP_MODELS_DIR" "$PLP_API_PORT" "$PLP_DASHBOARD_PORT" "$PROJECT"
echo "Stop test containers (retains files/models): docker compose -p $PROJECT -f compose.yaml down"
