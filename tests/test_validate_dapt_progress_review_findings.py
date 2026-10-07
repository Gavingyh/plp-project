"""
Tests for the reviewer's findings on the pretraining corpus (train/dapt.py),
the fine-tuning base model (train/finetune.py --base-model), copying a
source's rows between databases (scripts/source_rows.py) and the chatbot's
progress steps (chatbot/progress.py), 7 Oct 2026. Synthetic data only: temp
databases, labels files and a tiny BERT built in tmp_path; no training, no
network, no data/plp.db.

A test marked xfail(strict=True) is a confirmed finding: remove the marker in
the commit that fixes it.
"""

import importlib.util
import json
import os
import sqlite3

import pandas as pd
import pytest

import chatbot.agent as agent
import train.dapt as dapt
import train.finetune as finetune
from train.dapt import build_corpus, norm

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _corpus(tmp_path, corpus_rows, labelled_rows, labels=True):
    db = tmp_path / "corpus.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sentences (sentence_id TEXT, text TEXT, source TEXT)")
    conn.executemany("INSERT INTO sentences VALUES (?, ?, ?)", corpus_rows)
    conn.commit()
    conn.close()
    path = tmp_path / "labels.csv"
    pd.DataFrame(labelled_rows, columns=["sentence_id", "text", "split"]).to_csv(path, index=False)
    return build_corpus(str(db), str(path)) if labels else str(db)


# ----- Split test sentence reaches pretraining ----------------------------------

def test_a_test_sentence_split_in_two_does_not_reach_pretraining(tmp_path):
    first = "Other non-interest income include non-recurring gain from asset divestments, otherwise treasury non-customer and"
    second = ("NPA coverage decline to 88% on back of new NPA (1 Greater China real estate account under watch), "
              "GP loan coverage decline from 1.0% to 0.9%.")
    test_text = first + " • " + second
    kept, _ = _corpus(tmp_path, [("p", first, "sgx_research"), ("q", second, "sgx_research")],
                      [("t", test_text, "test")])
    assert first not in kept and second not in kept


# ----- Dropping common words lowers overlap -------------------------------------

def test_a_near_copy_made_mostly_of_common_words_is_left_out(tmp_path):
    common = "the bank loan ratio was from a"
    filler = [(f"f{i}", f"{common} filler{i} word{i}", "train_dev") for i in range(60)]   # common words: >50 rows
    test_text = f"{common} npl unchanged improved"
    corpus = f"{common} npl unchanged below previous"
    words = lambda t: set(t.split())
    assert len(words(test_text) & words(corpus)) / len(words(test_text) | words(corpus)) >= 0.6
    kept, _ = _corpus(tmp_path, [("c", corpus, "earnings")], filler + [("t", test_text, "test")])
    assert corpus not in kept


# ----- Default labels leave broker tests in -------------------------------------

def test_the_default_labels_cover_every_test_row(tmp_path):
    combined = pd.read_csv(os.path.join(REPO, "data", "labeled", "combined", "candidates.csv"))
    tests = combined[combined["split"] == "test"]
    db = _corpus(tmp_path, [(r.sentence_id, r.text, "sgx_research") for r in tests.itertuples()],
                 [("z", "unrelated", "train_dev")], labels=False)
    kept, _ = build_corpus(db)            # the default labels file
    assert kept == []


# ----- Import doubles a rebuilt source ------------------------------------------

def _source_rows():
    spec = importlib.util.spec_from_file_location("source_rows", os.path.join(REPO, "scripts", "source_rows.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(path, rows):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE documents (doc_id TEXT PRIMARY KEY, source TEXT);
        CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, doc_id TEXT, source TEXT, text TEXT);
        CREATE TABLE sentence_aspects (sentence_id TEXT, aspect TEXT, PRIMARY KEY (sentence_id, aspect));
        CREATE TABLE aspect_sentiment (sentence_id TEXT, aspect TEXT, label TEXT, PRIMARY KEY (sentence_id, aspect));
    """)
    for sid, doc, source, text in rows:
        conn.execute("INSERT OR IGNORE INTO documents VALUES (?, ?)", (doc, source))
        conn.execute("INSERT INTO sentences VALUES (?, ?, ?, ?)", (sid, doc, source, text))
    conn.commit()
    conn.close()


def test_importing_a_source_the_database_already_rebuilt_does_not_double_it(tmp_path):
    rows = _source_rows()
    pc, mac, out = str(tmp_path / "pc.db"), str(tmp_path / "mac.db"), str(tmp_path / "rows.db")
    _db(pc, [("pc1", "dpc", "sgx_research", "Loans grew 5%."), ("pc2", "dpc", "sgx_research", "NIM fell. •")])
    _db(mac, [("mac1", "dmac", "sgx_research", "Loans grew 5%."), ("mac2", "dmac", "sgx_research", "NIM fell.")])
    rows.export(pc, "sgx_research", out)
    try:
        rows.import_rows(out, mac)
    except SystemExit:
        return                                       # refusing is a fix too
    conn = sqlite3.connect(mac)
    assert conn.execute("SELECT COUNT(*) FROM sentences WHERE source = 'sgx_research'").fetchone()[0] == 2


# ----- Step description runs unguarded ------------------------------------------

def test_an_odd_tool_result_never_breaks_a_turn_without_a_display(monkeypatch):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {"get_sentiment": lambda **k: {"bank": "DBS", "score": "0.2", "n": 5}})

    class Model:
        name = model = "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("get_sentiment", {"bank": "DBS"})
            return "DBS reads slightly positive."
    r = agent.answer_turn("How is DBS?", backend=Model(), verbose=False)
    assert r.answer.startswith("DBS reads slightly positive")


# ----- Base model not recorded --------------------------------------------------

def _tiny(tmp_path, kind):
    """A tiny BERT with its tokenizer: 'mlm' (no sentiment head) or 'clf' (FinBERT's label order)."""
    from transformers import BertConfig, BertForMaskedLM, BertForSequenceClassification, BertTokenizer
    d = tmp_path / kind
    d.mkdir()
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"] + [chr(c) for c in range(97, 123)]
    (d / "vocab.txt").write_text("\n".join(vocab))
    cfg = BertConfig(vocab_size=len(vocab), hidden_size=8, num_hidden_layers=1, num_attention_heads=2,
                     intermediate_size=8, max_position_embeddings=64)
    if kind == "clf":
        cfg.num_labels, cfg.id2label = 3, {0: "positive", 1: "negative", 2: "neutral"}
        cfg.label2id = {v: k for k, v in cfg.id2label.items()}
        BertForSequenceClassification(cfg).save_pretrained(d)
    else:
        BertForMaskedLM(cfg).save_pretrained(d)
    BertTokenizer(str(d / "vocab.txt")).save_pretrained(d)
    return str(d)


def _labels(tmp_path, monkeypatch):
    rows = [{"sentence_id": f"s{i}", "text": f"text {i}", "aspect": "other", "split": "train_dev",
             "label": ["positive", "negative", "neutral"][i % 3], "source": "cna"} for i in range(30)]
    path = tmp_path / "labels.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(finetune, "CANDIDATES_PATH", str(path))


class _NoTraining:
    def __init__(self, model=None, **kw):
        self.model = model

    def train(self):
        pass

    def save_model(self, path):
        self.model.save_pretrained(path)

    def evaluate(self):
        return {}


def test_a_fine_tuned_model_records_its_base_model(tmp_path, monkeypatch):
    _labels(tmp_path, monkeypatch)
    monkeypatch.setattr(finetune, "WeightedTrainer", _NoTraining)
    base = _tiny(tmp_path, "clf")
    finetune.run(seed=1, epochs=1, out_dir=str(tmp_path / "out"), base_model=base)
    final = tmp_path / "out" / "seed_1" / "final"
    saved = " ".join(p.read_text() for p in final.glob("*.json"))
    assert base in saved


def test_a_base_model_without_a_sentiment_head_is_refused(tmp_path, monkeypatch):
    _labels(tmp_path, monkeypatch)
    monkeypatch.setattr(finetune, "WeightedTrainer", _NoTraining)
    with pytest.raises(ValueError, match="no sentiment head"):   # refused, not trained on a random head
        finetune.run(seed=1, epochs=1, out_dir=str(tmp_path / "out"), base_model=_tiny(tmp_path, "mlm"))
