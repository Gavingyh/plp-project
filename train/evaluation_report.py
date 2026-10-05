"""Every metric train.evaluate computes, plus the error breakdown of the 1 Oct report, for the
old (1 Oct, Hugging Face) and new (SGX retrain) models on the original, SGX and combined test scopes.

USAGE:
  python -m train.evaluation_report <output.md>
"""
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score

import train.evaluate as ev
from train.labels import LABELS

COMB = "data/labeled/combined/candidates.csv"
df = pd.read_csv(COMB)
ev.check_splits(df)
test_all = df[(df.split == "test") & df.label.isin(LABELS)].reset_index(drop=True)
train_all = df[df.split == "train_dev"]
scopes = {
    "original 299": (test_all[test_all.source != "sgx_research"].reset_index(drop=True),
                     train_all[train_all.source != "sgx_research"]),
    "SGX 100": (test_all[test_all.source == "sgx_research"].reset_index(drop=True), train_all),
    "combined 399": (test_all, train_all),
}
OLD = [f"models/plp-finbert-absa/seed_{s}/final" for s in (42, 1, 7)]
NEW = [f"models/sgx-retrain/label/seed_{s}/final" for s in (42, 1, 7)]

# probabilities once per model on the whole combined test set, sliced per scope
probs = {d: ev.finetuned_probs(d, test_all) for d in OLD + NEW}


def argmax_labels(p):
    return [LABELS[i] for i in p.argmax(axis=1)]


with contextlib.redirect_stdout(io.StringIO()):          # evaluate prints a lot; only the numbers matter
    from sentiment.score import classify_sentences
    base_all = [l for l, _ in classify_sentences(test_all["text"].tolist())]
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    an = SentimentIntensityAnalyzer()
    vader_all = ["positive" if (c := an.polarity_scores(t)["compound"]) > 0.05 else "negative" if c < -0.05 else "neutral"
                 for t in test_all["text"]]
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


def tfidf_preds(train, test):
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(vec.fit_transform(train["text"]), train["label"])
    return list(clf.predict(vec.transform(test["text"])))


def predictors(scope, idx, train):
    sub = test_all.loc[idx]
    out = {"base FinBERT (zero-shot)": [base_all[i] for i in idx],
           "VADER": [vader_all[i] for i in idx],
           "TF-IDF + logistic regression": tfidf_preds(train, sub)}
    for tag, dirs in (("old", OLD), ("new", NEW)):
        for s, d in zip(("42", "1", "7"), dirs):
            out[f"{tag} seed {s}"] = argmax_labels(probs[d][idx])
        out[f"{tag}, 3 averaged"] = argmax_labels(np.mean([probs[d][idx] for d in dirs], axis=0))
    return out


def metrics(y, p):
    rep = classification_report(y, p, labels=LABELS, output_dict=True, zero_division=0)
    row = {"acc": rep["accuracy"], "mP": rep["macro avg"]["precision"], "mR": rep["macro avg"]["recall"],
           "mF1": rep["macro avg"]["f1-score"], "wF1": rep["weighted avg"]["f1-score"]}
    for l in LABELS:
        row[l] = (rep[l]["precision"], rep[l]["recall"], rep[l]["f1-score"])
    yt, pp = np.array(y), np.array(p)
    row["errors"] = int((yt != pp).sum())
    row["neu_to_polar"] = int(((yt == "neutral") & (pp != "neutral")).sum())
    row["polar_to_neu"] = int(((yt != "neutral") & (pp == "neutral")).sum())
    row["pos_neg"] = int((((yt == "positive") & (pp == "negative")) | ((yt == "negative") & (pp == "positive"))).sum())
    return row


md = []
all_rows = {}
for scope, (test, train) in scopes.items():
    idx = test_all.index[test_all.sentence_id.isin(test.sentence_id)].tolist()
    y = test_all.loc[idx, "label"].tolist()
    support = pd.Series(y).value_counts()
    preds = predictors(scope, idx, train)
    rows = {name: metrics(y, p) for name, p in preds.items()}
    all_rows[scope] = (rows, idx, preds, y)
    md.append(f"### {scope} (n={len(y)}: {support['negative']} negative, {support['neutral']} neutral, {support['positive']} positive)\n")
    md.append("| model | accuracy | macro-F1 | macro precision | macro recall | weighted F1 | negative P / R / F1 | neutral P / R / F1 | positive P / R / F1 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for name, r in rows.items():
        cell = lambda l: " / ".join(f"{v:.2f}" for v in r[l])
        md.append(f"| {name} | {r['acc']:.3f} | {r['mF1']:.3f} | {r['mP']:.3f} | {r['mR']:.3f} | {r['wF1']:.3f} | "
                  f"{cell('negative')} | {cell('neutral')} | {cell('positive')} |")
    md.append("")
    md.append(f"Errors of {len(y)} (neutral called polar, polar called neutral, positive and negative swapped):\n")
    md.append("| model | errors | neutral called polar | polar called neutral | positive <-> negative |")
    md.append("|---|---|---|---|---|")
    for name, r in rows.items():
        md.append(f"| {name} | {r['errors']} | {r['neu_to_polar']} | {r['polar_to_neu']} | {r['pos_neg']} |")
    md.append("")

# accuracy by source on the combined set
rows, idx, preds, y = all_rows["combined 399"]
src = test_all.loc[idx, "source"].tolist()
order = pd.Series(src).value_counts().index.tolist()
md.append("### Accuracy by source (combined 399)\n")
md.append("| model | " + " | ".join(f"{s} (n={src.count(s)})" for s in order) + " |")
md.append("|---|" + "---|" * len(order))
for name, p in preds.items():
    cells = []
    for s in order:
        m = [i for i, x in enumerate(src) if x == s]
        cells.append(f"{np.mean([y[i] == p[i] for i in m]):.2f}")
    md.append(f"| {name} | " + " | ".join(cells) + " |")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(md) + "\n")
print("written", sys.argv[1])
