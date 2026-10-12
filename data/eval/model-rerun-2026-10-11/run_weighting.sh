#!/bin/sh
# The gap named in the model comparison report, 12 Oct 2026: the weighting techniques were only ever
# tested on plain FinBERT with people's labels. This runs them on the adapted encoder with the LLM's labels.
# Run under caffeinate -i, one GPU job at a time. Every step skips what is done.
#
# Rule fixed before the run: a weighted variant replaces the chosen model only if its gain over the
# adapted baseline on the 15 paired cross-validation folds is positive with p < 0.05 AND its test
# macro-F1 over three seeds is higher. Otherwise the chosen model stands.
#
# Order: 1) balanced class weights and source weights together ("everything on"), 15 folds;
#        2) its three final models; 3) balanced class weights alone, 15 folds; 4) source weights alone, 15 folds.
# The baseline for every pair is last night's adapted run on the same seeds and folds
# (data/eval/model-rerun-2026-10-11/cv_results.jsonl, base "dapt").
set -u
cd "$(dirname "$0")/../../.."   # the run itself used the absolute path of the repository
PY=".venv-plp/bin/python3"; export HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1
LABELS=data/labeled/llm_rater/rules-2026-10-10/training_set.csv
DAPT=models/dapt-2026-10-11/classifier; EXP=models/experiments-2026-10-11; R=data/run/rerun-gaps-2026-10-12; CV=$R/cv_results.jsonl
echo "start $(date)" >> $R/progress.log
cv() {   # $1 = variant name, rest = its flags
  name=$1; shift
  for seed in 42 1 7; do for f in 0 1 2 3 4; do
    key="$seed $f $name"
    grep -q "\"key\": \"$key\", .*\"dev_macro_f1\": [0-9]" $CV 2>/dev/null && continue
    log=$R/cv_${seed}_${f}_${name}.log
    $PY -m train.finetune --seed $seed --epochs 8 --aspect-text label --folds 5 --fold $f \
        --labels $LABELS --out-dir $EXP/cv --base-model $DAPT "$@" > $log 2>&1
    score=$(grep -o "dev macro-F1 [0-9.]*" $log | tail -1 | awk '{print $3}')
    echo "{\"key\": \"$key\", \"seed\": $seed, \"fold\": $f, \"variant\": \"$name\", \"dev_macro_f1\": ${score:-null}}" >> $CV
    echo "cv $key ${score:-FAILED} $(date)" >> $R/progress.log
  done; done
}
cv both --class-weights balanced --source-weights
for seed in 42 1 7; do
  d=$EXP/dapt-weighted/seed_$seed/final
  [ -d $d ] || $PY -m train.finetune --seed $seed --epochs 8 --aspect-text label --labels $LABELS \
      --out-dir $EXP/dapt-weighted --base-model $DAPT --class-weights balanced --source-weights > $R/final_both_$seed.log 2>&1
  [ -d $d ] && echo "final both seed $seed $(date)" >> $R/progress.log || echo "final both seed $seed FAILED $(date)" >> $R/progress.log
done
echo "everything-on finished $(date)" >> $R/progress.log; echo done > $R/both_done
cv balanced --class-weights balanced
cv source --source-weights
echo "all finished $(date)" >> $R/progress.log; echo done > $R/done
