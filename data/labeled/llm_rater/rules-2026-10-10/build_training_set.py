"""The label file for the model re-run decided on 10 Oct 2026.

train_dev: every sentence of the four sheets that is not a test row, with
Opus's aspect and sentiment from rater_labels.csv. Rows Opus flagged as not
about the bank are left out (the owner's choice, 11 Oct): a sentence that is
not about the bank has no sentiment toward it to learn.
test: the first round's 299 test rows with the labels they already have. The
broker research round's 100 test rows join once their annotator is recorded.

  .venv-plp/bin/python3 data/labeled/llm_rater/rules-2026-10-10/build_training_set.py
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
from train.labels import LABELS, check_splits, near_test_copies   # noqa: E402

L = os.path.join(ROOT, "data", "labeled")
COLS = ["sentence_id", "text", "bank", "source", "split"]
first = pd.read_csv(f"{L}/candidates.csv")
sheets = pd.concat([first[COLS], pd.read_csv(f"{L}/topup/topup_sheet.csv")[COLS],
                    pd.read_csv(f"{L}/active/active_sheet.csv")[COLS],
                    pd.read_csv(f"{L}/sgx_research/candidates.csv")[COLS]], ignore_index=True)
rater = pd.read_csv(os.path.join(HERE, "rater_labels.csv"))

train = sheets[sheets.split == "train_dev"].merge(rater, on="sentence_id")
flagged = int(train.rater_not_about_bank.sum())
train = train[~train.rater_not_about_bank]
train = train.assign(aspect=train.rater_aspect, label=train.rater_label, annotator=train.rater)
test = first[first.split == "test"].assign(annotator="", sheet="first_round")

copies = near_test_copies(train.text.tolist(), test.text.tolist())
if copies:
    print(f"left out {len(copies)} train rows that are near-copies of a test sentence")
    train = train.drop(train.index[copies])

keep = ["sentence_id", "aspect", "text", "bank", "source", "split", "label", "annotator", "sheet"]
out = pd.concat([train[keep], test[keep]], ignore_index=True)
assert out.label.isin(LABELS).all()
check_splits(out)
out.to_csv(os.path.join(HERE, "training_set.csv"), index=False)
t = out[out.split == "train_dev"]
print(f"training_set.csv: {len(t)} train_dev rows ({flagged} flagged as not about the bank left out), {len(out) - len(t)} test rows")
print("train_dev by sheet:", t.sheet.value_counts().to_dict())
print("train_dev labels:", t.label.value_counts().to_dict(), "| test labels:", out[out.split == "test"].label.value_counts().to_dict())
print("train_dev aspects:", t.aspect.value_counts().to_dict())
print("train_dev sources:", t.source.value_counts().to_dict())
