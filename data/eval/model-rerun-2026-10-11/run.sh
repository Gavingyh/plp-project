#!/bin/sh
# Model re-run decided on 10 Oct 2026, started 11 Oct. Run under caffeinate -i, one GPU job at a time.
# Labels: Opus's for training, the kept labels for the 299 test rows (training_set.csv).
# 1) pretrain the adapted encoder with the fixed leakage filter;
# 2) 5-fold cross-validation, seeds 42 1 7, from FinBERT and from the adapted encoder, on identical folds;
# 3) three final models from each; 4) score every model set on the test rows, with precision and recall per class.
# Every step skips what is already done, so the script can be started again after an interruption.
set -u
cd "$(dirname "$0")/../../.."   # the run itself used the absolute path of the repository
PY=".venv-plp/bin/python3"; export HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1
LABELS=data/labeled/llm_rater/rules-2026-10-10/training_set.csv
DAPT=models/dapt-2026-10-11; EXP=models/experiments-2026-10-11; R=data/run/rerun-2026-10-11; CV=$R/cv_results.jsonl
echo "start $(date)" >> $R/progress.log
if [ ! -f $DAPT/dapt_stats.json ]; then
  $PY -m train.dapt --out $DAPT > $R/dapt.log 2>&1 || { echo "pretraining FAILED $(date)" >> $R/progress.log; exit 1; }
fi
echo "pretraining done $(date)" >> $R/progress.log
for seed in 42 1 7; do for f in 0 1 2 3 4; do for base in finbert dapt; do
  key="$seed $f $base"
  grep -q "\"key\": \"$key\", .*\"dev_macro_f1\": [0-9]" $CV 2>/dev/null && continue
  extra=""; [ $base = dapt ] && extra="--base-model $DAPT/classifier"
  log=$R/cv_${seed}_${f}_${base}.log
  $PY -m train.finetune --seed $seed --epochs 8 --aspect-text label --folds 5 --fold $f \
      --labels $LABELS --out-dir $EXP/cv $extra > $log 2>&1
  score=$(grep -o "dev macro-F1 [0-9.]*" $log | tail -1 | awk '{print $3}')
  echo "{\"key\": \"$key\", \"seed\": $seed, \"fold\": $f, \"base\": \"$base\", \"dev_macro_f1\": ${score:-null}}" >> $CV
  echo "cv $key ${score:-FAILED} $(date)" >> $R/progress.log
done; done; done
for base in finbert dapt; do for seed in 42 1 7; do
  d=$EXP/$base/seed_$seed/final
  extra=""; [ $base = dapt ] && extra="--base-model $DAPT/classifier"
  [ -d $d ] || $PY -m train.finetune --seed $seed --epochs 8 --aspect-text label \
      --labels $LABELS --out-dir $EXP/$base $extra > $R/final_${base}_$seed.log 2>&1
  [ -d $d ] && echo "final $base seed $seed $(date)" >> $R/progress.log || echo "final $base seed $seed FAILED $(date)" >> $R/progress.log
done; done
$PY $R/score.py > $R/score.log 2>&1 && echo "scored $(date)" >> $R/progress.log || echo "scoring FAILED $(date)" >> $R/progress.log
echo done > $R/done
