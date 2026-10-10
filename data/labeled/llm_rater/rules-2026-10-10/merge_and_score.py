"""Merge the round's answers into rater_labels.csv and compare them with the
earlier labels. Reads only; changes no other labelling file.

  .venv-plp/bin/python3 data/labeled/llm_rater/rules-2026-10-10/merge_and_score.py
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
from config import aspect_taxonomy                      # noqa: E402
from train.rater_labels import agreement, batch_pairs, merge   # noqa: E402

keys = list(aspect_taxonomy.labels()) + ["other"]
out = merge(batch_pairs(HERE), keys).merge(pd.read_csv(os.path.join(HERE, "sheets.csv")), on="sentence_id")
out.to_csv(os.path.join(HERE, "rater_labels.csv"), index=False)
print(f"rater_labels.csv: {len(out)} rows;", out.groupby("sheet").size().to_dict())
print("not about the bank:", int(out.rater_not_about_bank.sum()))
print("aspects:", out.rater_aspect.value_counts().to_dict())
print("sentiment:", out.rater_label.value_counts().to_dict())
print("sentiment by sheet:", {k: v.value_counts().to_dict() for k, v in out.groupby("sheet").rater_label})

L = os.path.join(ROOT, "data", "labeled")
cand = pd.read_csv(f"{L}/candidates.csv")[["sentence_id", "split", "source", "aspect", "label"]]
old = pd.read_csv(f"{L}/llm_rater/rater_labels.csv")[["sentence_id", "rater_aspect", "rater_label"]].rename(
    columns={"rater_aspect": "old_aspect", "rater_label": "old_label"})
d = out.merge(cand, on="sentence_id").merge(old, on="sentence_id")
fmt = lambda m: f"{m['agreement']:.3f} (n={m['n']}), kappa {m['kappa']:.3f}"
print(f"\nfirst round, {len(d)} rows")
print("  aspect,    new Opus against people:    ", fmt(agreement(d.aspect, d.rater_aspect)))
print("  aspect,    1 Oct Opus against people:  ", fmt(agreement(d.aspect, d.old_aspect)))
print("  aspect,    new Opus against 1 Oct Opus:", fmt(agreement(d.old_aspect, d.rater_aspect)))
print("  sentiment, new Opus against people:    ", fmt(agreement(d.label, d.rater_label)))
print("  sentiment, 1 Oct Opus against people:  ", fmt(agreement(d.label, d.old_label)))
print("  sentiment, new Opus against 1 Oct Opus:", fmt(agreement(d.old_label, d.rater_label)))
for split, g in d.groupby("split"):
    print(f"  {split}: rows {len(g)}; aspect differs from people {int((g.aspect != g.rater_aspect).sum())}; "
          f"sentiment differs from people {int((g.label != g.rater_label).sum())}")
w = d[(d.old_aspect == "wealth_business") | (d.rater_aspect == "wealth_business") | (d.aspect == "wealth_business")]
print(f"\nwealth: people {int((d.aspect == 'wealth_business').sum())} rows, 1 Oct Opus {int((d.old_aspect == 'wealth_business').sum())}, "
      f"new Opus {int((d.rater_aspect == 'wealth_business').sum())}")
print("  people's wealth rows now:", d[d.aspect == "wealth_business"].rater_aspect.value_counts().to_dict())
r = d[(d.rater_aspect == "retail_banking_sentiment") & (d.old_aspect == "retail_banking_sentiment")]
print(f"\nretail rows under both Opus runs: {len(r)}")
print("  1 Oct sentiment:", r.old_label.value_counts().to_dict())
print("  new sentiment:  ", r.rater_label.value_counts().to_dict())
print("  moved:", pd.crosstab(r.old_label, r.rater_label).to_dict())
rp = d[(d.aspect == "retail_banking_sentiment")]
print(f"  people's retail rows ({len(rp)}): people {rp.label.value_counts().to_dict()}; new Opus {rp.rater_label.value_counts().to_dict()}")

sg = pd.read_csv(f"{L}/sgx_research/candidates.csv")[["sentence_id", "split", "aspect", "label"]]
s = out.merge(sg, on="sentence_id")
s = s[s.label.notna()]
print(f"\nbroker research, {len(s)} rows with a label on the sheet")
print("  aspect, new Opus against the sheet:   ", fmt(agreement(s.aspect, s.rater_aspect)))
print("  sentiment, new Opus against the sheet:", fmt(agreement(s.label, s.rater_label)))
