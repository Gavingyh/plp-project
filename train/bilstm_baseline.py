"""
A second neural architecture for the sentiment classifier: a BiLSTM and a
text CNN trained from scratch, optionally on GloVe vectors (Text Analytics and
Text Processing using ML: word embeddings, RNN/CNN for text).

Why: the deep-learning requirement is currently met by FinBERT alone. Training a
second, different network on the same labels shows whether the transformer's
pretraining is what matters, and it is the standard small-data comparison.

Protocol (same labels and splits as train.finetune and train.baselines_classical):
  - check_splits first; train_dev is split 85/15 by seed into train and dev;
  - the epoch with the best dev macro-F1 is kept (patience 5, max 30 epochs);
  - the test split is scored once per seed, after the epoch is chosen;
  - three seeds; report mean and standard deviation, plus the interval from
    train.baselines_classical.macro_f1_interval on the seed-averaged vote.
  - the input is the aspect key as a first token, then the sentence.

torch is imported inside the functions, so the module can be imported (and the
tokeniser tested) on a machine without it.

USAGE (a machine with torch; a GPU is used if present):
  python -m train.bilstm_baseline --arch bilstm
  python -m train.bilstm_baseline --arch cnn --seeds 42 43 44
  python -m train.bilstm_baseline --arch bilstm --glove C:/path/glove.6B.100d.txt
GloVe is a separate download (nlp.stanford.edu); without --glove, embeddings
are learned from the training sentences only.
"""

import argparse
import json
import os
import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

from train.baselines_classical import DEFAULT_LABELS, load_split, macro_f1_interval, model_input
from train.labels import LABELS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "eval", "baselines")
PAD, UNK = 0, 1
TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?%?|[^\sa-z\d]", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text)]


def build_vocab(texts: list[str], min_count: int = 2, max_size: int = 20000) -> dict[str, int]:
    counts = Counter(t for x in texts for t in tokenize(x))
    vocab = {"<pad>": PAD, "<unk>": UNK}
    for tok, c in counts.most_common(max_size):
        if c >= min_count:
            vocab[tok] = len(vocab)
    return vocab


def encode(texts: list[str], vocab: dict[str, int], max_len: int = 80) -> np.ndarray:
    out = np.zeros((len(texts), max_len), dtype=np.int64)
    for i, x in enumerate(texts):
        ids = [vocab.get(t, UNK) for t in tokenize(x)][:max_len]
        out[i, :len(ids)] = ids
    return out


def load_glove(path: str, vocab: dict[str, int], dim: int | None = None) -> np.ndarray:
    """Embedding matrix for `vocab` from a GloVe text file; words missing from it stay small random."""
    vectors = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip().split(" ")
            if parts[0] in vocab:
                vectors[parts[0]] = np.asarray(parts[1:], dtype=np.float32)
    dim = dim or len(next(iter(vectors.values())))
    rng = np.random.default_rng(0)
    matrix = rng.normal(0, 0.1, (len(vocab), dim)).astype(np.float32)
    matrix[PAD] = 0
    for tok, i in vocab.items():
        if tok in vectors:
            matrix[i] = vectors[tok]
    print(f"GloVe covers {len(vectors)} of {len(vocab)} vocabulary words")
    return matrix


def make_model(arch: str, vocab_size: int, n_classes: int, emb_matrix=None, emb_dim: int = 100,
               hidden: int = 128, dropout: float = 0.4):
    import torch
    from torch import nn

    class BiLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=PAD)
            if emb_matrix is not None:
                self.emb.weight.data.copy_(torch.from_numpy(emb_matrix))
            self.rnn = nn.LSTM(emb_dim, hidden, batch_first=True, bidirectional=True)
            self.drop = nn.Dropout(dropout)
            self.out = nn.Linear(2 * hidden, n_classes)

        def forward(self, x):
            mask = (x != PAD).unsqueeze(-1)
            h, _ = self.rnn(self.drop(self.emb(x)))
            h = h.masked_fill(~mask, -1e9).max(dim=1).values        # max-pool over real tokens
            return self.out(self.drop(h))

    class TextCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=PAD)
            if emb_matrix is not None:
                self.emb.weight.data.copy_(torch.from_numpy(emb_matrix))
            self.convs = nn.ModuleList([nn.Conv1d(emb_dim, hidden, k, padding=k // 2) for k in (2, 3, 4)])
            self.drop = nn.Dropout(dropout)
            self.out = nn.Linear(3 * hidden, n_classes)

        def forward(self, x):
            e = self.drop(self.emb(x)).transpose(1, 2)
            pooled = [torch.relu(c(e)).max(dim=2).values for c in self.convs]
            return self.out(self.drop(torch.cat(pooled, dim=1)))

    return BiLSTM() if arch == "bilstm" else TextCNN()


def train_one(arch: str, seed: int, train_df: pd.DataFrame, test_df: pd.DataFrame, glove: str | None,
              epochs: int = 30, patience: int = 5, batch: int = 32, lr: float = 2e-3) -> dict:
    import torch
    from torch import nn

    torch.manual_seed(seed)
    np.random.seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    shuffled = train_df.sample(frac=1, random_state=seed).reset_index(drop=True)
    cut = int(len(shuffled) * 0.85)
    tr, dv = shuffled[:cut], shuffled[cut:]
    vocab = build_vocab(model_input(tr))
    emb = load_glove(glove, vocab) if glove else None
    l2i = {l: i for i, l in enumerate(LABELS)}

    def tensors(df):
        x = torch.from_numpy(encode(model_input(df), vocab)).to(device)
        y = torch.tensor([l2i[l] for l in df["label"]], device=device)
        return x, y
    (xtr, ytr), (xdv, ydv), (xte, yte) = tensors(tr), tensors(dv), tensors(test_df)

    model = make_model(arch, len(vocab), len(LABELS), emb, emb.shape[1] if emb is not None else 100).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    loss_fn = nn.CrossEntropyLoss()

    def predict(x):
        model.eval()
        with torch.no_grad():
            return torch.cat([model(x[i:i + 256]).argmax(1) for i in range(0, len(x), 256)]).cpu().numpy()

    best, best_state, wait = -1.0, None, 0
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(xtr), device=device)
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            opt.zero_grad()
            loss_fn(model(xtr[idx]), ytr[idx]).backward()
            opt.step()
        dev_f1 = f1_score(ydv.cpu().numpy(), predict(xdv), average="macro", labels=list(range(len(LABELS))))
        if dev_f1 > best:
            best, wait = dev_f1, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(best_state)
    pred = predict(xte)                        # the test split is touched once, here
    true = yte.cpu().numpy()
    return {"seed": seed, "dev_macro_f1": best, "epochs_run": epoch + 1,
            "test_macro_f1": f1_score(true, pred, average="macro", labels=list(range(len(LABELS)))),
            "test_accuracy": accuracy_score(true, pred), "pred": pred.tolist()}


def run(arch: str, labels_path: str, seeds: list[int], glove: str | None, out_dir: str = OUT_DIR) -> dict:
    train, test = load_split(labels_path)
    runs = [train_one(arch, s, train, test, glove) for s in seeds]
    for r in runs:
        print(f"seed {r['seed']}: dev {r['dev_macro_f1']:.3f}  test macro-F1 {r['test_macro_f1']:.3f}  "
              f"({r['epochs_run']} epochs)")
    f1s = [r["test_macro_f1"] for r in runs]
    votes = np.array([r["pred"] for r in runs])
    majority = [int(np.bincount(votes[:, j], minlength=len(LABELS)).argmax()) for j in range(votes.shape[1])]
    f1, lo, hi = macro_f1_interval(list(test["label"]), [LABELS[i] for i in majority])
    summary = {"arch": arch, "glove": bool(glove), "seeds": seeds,
               "test_macro_f1_mean": float(np.mean(f1s)),
               "test_macro_f1_sd": float(np.std(f1s, ddof=1)) if len(f1s) > 1 else None,
               "vote_macro_f1": f1, "vote_ci": [lo, hi], "n_train": len(train), "n_test": len(test)}
    os.makedirs(out_dir, exist_ok=True)
    tag = f"{arch}{'_glove' if glove else ''}"
    with open(os.path.join(out_dir, f"{tag}.json"), "w") as f:
        json.dump({"summary": summary, "runs": [{k: v for k, v in r.items() if k != "pred"} for r in runs]}, f, indent=1)
    pd.DataFrame({"sentence_id": test["sentence_id"], "label": test["label"],
                  tag: [LABELS[i] for i in majority]}).to_csv(
        os.path.join(out_dir, f"{tag}_test_predictions.csv"), index=False)
    print(json.dumps(summary, indent=1))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", choices=["bilstm", "cnn"], default="bilstm")
    ap.add_argument("--labels", default=DEFAULT_LABELS)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    ap.add_argument("--glove", default=None, help="path to a GloVe .txt file (optional)")
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()
    run(a.arch, a.labels, a.seeds, a.glove, a.out)


if __name__ == "__main__":
    main()
