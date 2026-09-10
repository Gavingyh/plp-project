#!/usr/bin/env bash
# Runs the chatbot gold set against several local models to see whether
# citation fabrication is specific to llama3.2:3b or general to small local
# models. Baseline (llama3.2:3b, 48% fabrication) is already recorded.
set -u
cd "$(dirname "$0")/.."
PY=.venv-plp/bin/python3

ollama pull llama3.1:8b 2>&1 | tail -2

for MODEL in gemma3:4b phi4-mini:latest llama3.1:8b llama3.2:3b; do
  TAG=$(echo "$MODEL" | tr ':/' '__')
  echo "=== $MODEL ==="
  CHATBOT_BACKEND=ollama OLLAMA_MODEL="$MODEL" HF_HUB_OFFLINE=1 \
    "$PY" -m chatbot.run_eval --tag "$TAG" 2>&1 | tail -3
done
echo "=== ALL DONE ==="
