"""
Validation probes for the pretraining corpus (train/dapt.py), the chatbot's
progress steps (chatbot/progress.py, answer_turn's on_step) and the labelling
round merge (train/source_round.py), 7 Oct 2026. Synthetic data only: a
temporary database and labels files, fake backends with the intent stubbed;
no model, no network, no data/plp.db.

A test marked xfail(strict=True) is a confirmed gap: remove the marker in the
commit that fixes it.
"""

import sqlite3

import pandas as pd
import pytest

import chatbot.agent as agent
from train.dapt import build_corpus, norm


# ----- pretraining corpus: no test text ---------------------------------------

def _corpus(tmp_path, corpus_rows, labelled_rows):
    db = tmp_path / "plp.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sentences (sentence_id TEXT, text TEXT, source TEXT)")
    conn.executemany("INSERT INTO sentences VALUES (?, ?, ?)", corpus_rows)
    conn.commit()
    conn.close()
    labels = tmp_path / "candidates.csv"
    pd.DataFrame(labelled_rows, columns=["sentence_id", "text", "split"]).to_csv(labels, index=False)
    return build_corpus(str(db), str(labels))


def test_a_corpus_sentence_holding_a_whole_test_sentence_is_left_out(tmp_path):
    test_text = "Local developer secures $300m sustainability-linked loan from DBS"
    kept, _ = _corpus(tmp_path,
                      [("t", test_text, "google_news"),
                       ("c", "Reported this morning by several regional outlets: local developer secures "
                             "$234m sustainability-linked loan from DBS", "yahoo_news")],
                      [("t", test_text, "test")])
    assert not any(norm(test_text) in norm(k) for k in kept)


def test_a_corpus_sentence_that_is_part_of_a_test_sentence_is_left_out(tmp_path):
    first = "Currently, the bank's shareholding in the insurer has risen to 93.72% (July 2024: 93.52%)."
    test_text = first + "The insurer has been given an extension till May 2025 to comply with the free-float rule."
    kept, _ = _corpus(tmp_path,
                      [("t", test_text, "sgx_research"), ("c", first, "earnings")],
                      [("t", test_text, "test")])
    assert first not in kept


def test_test_text_is_dropped_whatever_its_sentence_id(tmp_path):
    # Same text, other id, other case, spacing and figures: dropped (the rule the docstring states).
    test_text = "NPL ratio of 1.0% was unchanged from a quarter ago."
    kept, stats = _corpus(tmp_path,
                          [("t", test_text, "earnings"), ("c", "NPL ratio  of 1.1% was UNCHANGED from a quarter ago.",
                                                          "earnings"), ("k", "Unrelated line about deposits.", "cna")],
                          [("t", test_text, "test")])
    assert kept == ["Unrelated line about deposits."]
    assert stats["dropped_labelled_id"] == 1 and stats["dropped_matching_labelled_text"] == 1


# ----- chatbot: on_step never changes the answer -------------------------------

_CORE = ("answer", "guard", "intent", "evidence_enforced", "citation_unverified", "unverified_numbers")

INVENTED = ("DBS's dividend sentiment is slightly positive, at +0.20 on 120 sentences.\n\n"
            "Supporting evidence:\n"
            '* "DBS raises its payout ratio to 40%." (sentence_id: 12345, URL: https://example.com/dbs)\n\n'
            "Caveats: Reddit skews towards DBS.")


def _backend(monkeypatch, answer, calls, search=None):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    tools = {"get_sentiment": lambda **k: {"bank": k["bank"], "window": "all_time", "score": 0.2, "n": 120,
                                           "reading": "slightly positive", "topic_name": "Dividend Policy"},
             "get_coverage": lambda **k: {"bank": k.get("bank", "ALL"), "n": 24431, "latest": "2026-09-25"},
             "get_trend": lambda **k: (_ for _ in ()).throw(RuntimeError("tool down")),
             "search_evidence": lambda **k: search or {"results": []}}
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", tools)

    class Model:
        name = model = "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            for name, args in calls:
                execute(name, args)
            return answer
    return Model()


def _broken(step):
    raise RuntimeError("display gone")


CASES = [
    (INVENTED, [("get_sentiment", {"bank": "DBS", "aspect": "dividend_policy"})], None),
    ("DBS scored +0.45 on 120 sentences.", [("get_sentiment", {"bank": "DBS"})], None),
    ('Evidence:\n- "Margins held up well this quarter." (https://x.org/1)',
     [("search_evidence", {"query": "q", "bank": "DBS"})],
     {"results": [{"sentence_id": "b" * 24, "url": "https://x.org/1", "source": "arctic_shift",
                   "text": "Margins held up well this quarter."}]}),
    ('DBS is up. "An invented quote nobody wrote." (Reuters)',
     [("get_trend", {"bank": "DBS"}), ("get_coverage", {"bank": "DBS"}), ("search_evidence", {"query": "q"})], None),
    ("", [("get_sentiment", {"bank": "DBS"})], None),
]


@pytest.mark.parametrize("answer,calls,search", CASES)
def test_the_progress_callback_never_changes_a_turn(monkeypatch, answer, calls, search):
    results = []
    for on_step in (None, [].append, _broken):
        model = _backend(monkeypatch, answer, calls, search)
        r = agent.answer_turn("How is DBS on dividends?", backend=model, verbose=False, on_step=on_step)
        results.append(({k: getattr(r, k) for k in _CORE}, [(c["name"], c.get("by")) for c in r.calls]))
    assert results[0] == results[1] == results[2]
    if answer == INVENTED:
        assert "12345" not in results[0][0]["answer"] and results[0][0]["evidence_enforced"] == "strip"


# ----- labelling round merge: every labelled row names its annotator -----------

from tests.test_source_round import _filled as _filled_round   # noqa: E402  (the round fixture)
from train.source_round import merge                           # noqa: E402


@pytest.mark.parametrize("sheet,how", [("candidates", "one_blank"), ("blind", "one_blank"),
                                       ("candidates", "spaces"), ("blind", "no_column"),
                                       ("candidates", "no_column")])
def test_merge_refuses_any_labelled_row_without_an_annotator(tmp_path, sheet, how):
    cand, blind = _filled_round(tmp_path)
    path = cand if sheet == "candidates" else blind
    df = pd.read_csv(path, dtype=str)
    labelled = df.index[df["label"].notna()]
    if how == "one_blank":
        df.loc[labelled[:1], "annotator"] = None
    elif how == "spaces":
        df.loc[labelled[:1], "annotator"] = "   "
    else:
        df = df.drop(columns=["annotator"])
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="without an annotator"):
        merge(str(tmp_path), cand, blind)
