#!/usr/bin/env bash
#
# Gather what a teammate needs to run the system, with a checksum list, into
# one folder to upload to the team's shared drive.
#
#   scripts/share_bundle.sh OUT_DIR                 # snapshot, embedding cache, aspect answers
#   scripts/share_bundle.sh OUT_DIR --with-models   # also the fine-tuned models (normally from Hugging Face)
#
# Contents (see "Sharing the data and models" in README.md):
#   plp-<date>.db.gz             the latest database snapshot   -> gunzip to data/plp.db
#   search_embeddings.npz        the evidence search's vectors   -> data/
#   sentence_embeddings.npz      FinBERT's vectors, for aspect discovery -> data/
#   aspect_llm/<model>.<prompt>.jsonl  the LLM's aspect per sentence for the
#                                current prompt (ids and labels, no text) -> data/aspect_llm/
#   models/seed_*/               the served fine-tuned models, without training_args.bin
#                                -> models/experiments-2026-10-11/dapt/
#   README-teams.md              where each file goes; read first
#   SHA256SUMS                   check with: shasum -a 256 -c SHA256SUMS
#
# Never included: .env (API keys), data/cna/ (CNA's articles stay within the
# team's own copies), logs, and caches other than the aspect answers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:?usage: scripts/share_bundle.sh OUT_DIR [--with-models]}"
WITH_MODELS="${2:-}"
MODEL_DIR="$ROOT/models/experiments-2026-10-11/dapt"

snapshot="$(ls -1 "$ROOT"/data/snapshots/plp-*.db.gz 2>/dev/null | sort | tail -1)"
[ -n "$snapshot" ] || { echo "no snapshot in data/snapshots/" >&2; exit 1; }
mkdir -p "$OUT"
cp "$snapshot" "$OUT/"
[ -f "$ROOT/data/search_embeddings.npz" ] && cp "$ROOT/data/search_embeddings.npz" "$OUT/"
[ -f "$ROOT/data/sentence_embeddings.npz" ] && cp "$ROOT/data/sentence_embeddings.npz" "$OUT/"
[ -f "$ROOT/data/README-teams.md" ] && cp "$ROOT/data/README-teams.md" "$OUT/"
# Only the current prompt's answers: an older prompt's file would be ignored by the code anyway.
aspects="$(cd "$ROOT" && .venv-plp/bin/python3 -c \
    "from aspects.llm_classify import answer_cache_path; print(answer_cache_path('llama3.1:8b'))")"
if [ -f "$aspects" ]; then
    mkdir -p "$OUT/aspect_llm"
    cp "$aspects" "$OUT/aspect_llm/"
else
    echo "note: no LLM aspect answers for the current prompt ($aspects)" >&2
fi

if [ "$WITH_MODELS" = "--with-models" ]; then
    for s in seed_42 seed_1 seed_7; do
        [ -d "$MODEL_DIR/$s/final" ] || { echo "missing $MODEL_DIR/$s/final" >&2; exit 1; }
        mkdir -p "$OUT/models/$s"
        for f in config.json model.safetensors tokenizer.json tokenizer_config.json input_format.json; do
            cp "$MODEL_DIR/$s/final/$f" "$OUT/models/$s/"
        done
    done
    cp "$ROOT/docs/model-card.md" "$OUT/models/README.md"
fi

(cd "$OUT" && find . -type f ! -name SHA256SUMS | sort | xargs shasum -a 256 > SHA256SUMS)
echo "bundle in $OUT ($(du -sh "$OUT" | cut -f1)); latest snapshot: $(basename "$snapshot")"
