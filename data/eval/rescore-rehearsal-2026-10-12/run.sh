#!/bin/zsh
# The re-score rehearsal, on a copy only. Waits for the aspect and scoring
# jobs, then: dry run, apply on the copy, rebuild the copy's index with the
# windows counted back from the moment the stored index was computed.
cd "$(dirname "$0")/../../.." || exit 1
D=data/run/rescore-2026-10-12
COPY=$D/plp_rescored.db
AS_OF=2026-09-30T07:34:44.594551+00:00
MODELS=(models/experiments-2026-10-11/dapt/seed_42/final models/experiments-2026-10-11/dapt/seed_1/final models/experiments-2026-10-11/dapt/seed_7/final)
VERSION=finbert-adapted-finetuned-2026-10-11-3seed-m0
export HF_HUB_OFFLINE=1

for f in aspects prescore; do
  pid=$(grep -o '[0-9]*' $D/$f.pid | head -1)
  while kill -0 $pid 2>/dev/null; do sleep 30; done
  echo "$(date '+%F %T') $f job ended"
done
tail -3 $D/aspects.log; tail -1 $D/prescore.log

echo "== dry run =="
.venv-plp/bin/python3 scripts/rescore.py --db $COPY --fresh-copy --aspects llm --finetuned \
  --models $MODELS --margin 0 --version $VERSION --cpu || exit 1
echo "== apply on the copy =="
.venv-plp/bin/python3 scripts/rescore.py --db $COPY --aspects llm --finetuned \
  --models $MODELS --margin 0 --version $VERSION --cpu --apply || exit 1
echo "== index with held windows =="
PLP_DB_PATH=$COPY .venv-plp/bin/python3 data/run/merge-2026-10-11/rebuild_index_as_of.py $AS_OF || exit 1
shasum -a 256 data/plp.db
echo "$(date '+%F %T') rehearsal finished"
