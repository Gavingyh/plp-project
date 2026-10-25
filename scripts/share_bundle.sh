#!/usr/bin/env bash
#
# Build the project's dataset, data.zip, as the Docker setup expects it
# (docker/bootstrap.py, RUNTIME_FILES), with a checksum list and the teammates'
# note beside it. Put data.zip at data/data.zip: Docker restores it on first
# start, and natively `.venv-plp/bin/python3 -m docker.bootstrap --data-only`
# does the same (README, "Getting the database").
#
#   scripts/share_bundle.sh OUT_DIR
#
# data.zip holds, under data/:
#   plp.db                       the latest snapshot in data/snapshots/, decompressed
#   sentence_embeddings.npz      FinBERT's vectors, for aspect discovery
#   search_embeddings.npz        the evidence search's vectors (setup rebuilds them if absent)
#   cna/articles.jsonl, cna/candidates.json   the CNA cache
#   aspect_llm/<model>.<prompt>.jsonl  the aspect model's answer per sentence for the
#                                current prompt (ids and labels, no text)
# Beside it: README-teams.md (read first) and SHA256SUMS (shasum -a 256 -c SHA256SUMS).
#
# The models are not in it: setup downloads them from Hugging Face. Never in it:
# .env (API keys), logs, other caches. data.zip holds CNA articles and Reddit
# text: give it to the team and the assessors only, never publish it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:?usage: scripts/share_bundle.sh OUT_DIR}"
PY="$ROOT/.venv-plp/bin/python3"

snapshot="$(ls -1 "$ROOT"/data/snapshots/plp-*.db.gz 2>/dev/null | sort | tail -1)"
[ -n "$snapshot" ] || { echo "no snapshot in data/snapshots/" >&2; exit 1; }
for f in sentence_embeddings.npz cna/articles.jsonl cna/candidates.json; do
    [ -f "$ROOT/data/$f" ] || { echo "missing data/$f" >&2; exit 1; }
done
# Only the current prompt's answers: an older prompt's file would be ignored by the code anyway.
aspects="$(cd "$ROOT" && "$PY" -c "from aspects.llm_classify import answer_cache_path; print(answer_cache_path('llama3.1:8b'))")"
[ -f "$aspects" ] || echo "note: no aspect answers for the current prompt ($aspects); data.zip goes without them" >&2

mkdir -p "$OUT"
rm -f "$OUT/data.zip"
"$PY" - "$ROOT" "$snapshot" "$aspects" "$OUT/data.zip" <<'PYTHON'
import gzip, os, shutil, sys, tempfile, zipfile
root, snapshot, aspects, out = sys.argv[1:5]
entries = [("data/sentence_embeddings.npz", f"{root}/data/sentence_embeddings.npz"),
           ("data/search_embeddings.npz", f"{root}/data/search_embeddings.npz"),
           ("data/cna/articles.jsonl", f"{root}/data/cna/articles.jsonl"),
           ("data/cna/candidates.json", f"{root}/data/cna/candidates.json"),
           (f"data/aspect_llm/{os.path.basename(aspects)}", aspects)]
with tempfile.TemporaryDirectory() as tmp:
    db = os.path.join(tmp, "plp.db")
    with gzip.open(snapshot, "rb") as src, open(db, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(db, "data/plp.db")
        for name, path in entries:
            if os.path.isfile(path):
                z.write(path, name)
PYTHON
[ -f "$ROOT/data/README-teams.md" ] && cp "$ROOT/data/README-teams.md" "$OUT/"
(cd "$OUT" && shasum -a 256 data.zip > SHA256SUMS && [ -f README-teams.md ] && shasum -a 256 README-teams.md >> SHA256SUMS || true)
echo "data.zip in $OUT ($(du -h "$OUT/data.zip" | cut -f1)), database from $(basename "$snapshot")"
echo "sha256 (for PLP_DATA_SHA256): $(cut -d' ' -f1 "$OUT/SHA256SUMS" | head -1)"
