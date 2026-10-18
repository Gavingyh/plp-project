"""Tests for the added analyses: term analysis, topic-model scoring, bootstrap
uncertainty, price check statistics, opinion summarisation checks, term-extraction
validation and the classical baselines. No database, model or network needed."""

from collections import Counter

import numpy as np
import pandas as pd
import pytest

from aggregate import price_check as pc
from aggregate import uncertainty as unc
from aspects import extract_terms as et
from aspects import topic_model as tm
from chatbot import summarise as sm
from scripts import term_analysis as ta
from train import baselines_classical as bc
from train import bilstm_baseline as bl


# --- term analysis -------------------------------------------------------------------

def test_log_odds_finds_the_group_word_and_signs():
    a = Counter({"card": 40, "bank": 10})
    b = Counter({"income": 40, "bank": 10})
    prior = a + b
    res = {w: z for w, z, _, _ in ta.log_odds(a, b, prior, min_count=5)}
    assert res["card"] > 2 and res["income"] < -2
    assert abs(res["bank"]) < abs(res["card"])


def test_log_odds_drops_rare_words():
    res = ta.log_odds(Counter({"x": 2}), Counter({"y": 1}), Counter({"x": 2, "y": 1}), min_count=5)
    assert res == []


# --- topic model scoring -------------------------------------------------------------

def test_purity_and_nmi_perfect_and_chance():
    topics = [0, 0, 1, 1, 2, 2]
    aspects = ["a", "a", "b", "b", "c", "c"]
    assert tm.purity(tm.contingency(topics, aspects)) == 1.0
    nmi, ari = tm.nmi_ari(topics, aspects)
    assert nmi == pytest.approx(1.0) and ari == pytest.approx(1.0)
    mixed = ["a", "b", "a", "b", "a", "b"]
    assert tm.nmi_ari(topics, mixed)[0] < 0.5


# --- uncertainty ---------------------------------------------------------------------

ITEMS = [(f"d{i // 3}", -1 if (i * 7) % 5 < 2 else 1, 0.8) for i in range(60)]


def test_bootstrap_is_deterministic_and_brackets_the_point():
    a = unc.bootstrap_scores(ITEMS, "document", boot=400, seed=1)
    b = unc.bootstrap_scores(ITEMS, "document", boot=400, seed=1)
    assert np.array_equal(a, b)
    lo, hi = unc.percentile_interval(a)
    assert lo <= unc.point_score(ITEMS) <= hi


def test_document_bootstrap_is_wider_than_sentence_bootstrap_for_clustered_data():
    clustered = [(f"d{i // 10}", 1 if (i // 10) % 2 else -1, 1.0) for i in range(100)]
    w_doc = np.subtract(*unc.percentile_interval(unc.bootstrap_scores(clustered, "document", 600, 3))[::-1])
    w_sen = np.subtract(*unc.percentile_interval(unc.bootstrap_scores(clustered, "sentence", 600, 3))[::-1])
    assert w_doc > w_sen


def test_bootstrap_rejects_unknown_unit():
    with pytest.raises(ValueError):
        unc.bootstrap_scores(ITEMS, "paragraph")


# --- price check statistics ----------------------------------------------------------

def test_spearman_known_values_and_degenerate_input():
    assert pc.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert pc.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert np.isnan(pc.spearman([1, 1, 1], [1, 2, 3]))


def test_permutation_p_small_for_perfect_and_large_for_noise():
    x = list(range(20))
    assert pc.permutation_p(x, x, rounds=500) < 0.01
    rng = np.random.default_rng(0)
    assert pc.permutation_p(x, rng.normal(size=20), rounds=500) > 0.05


# --- summarisation checks ------------------------------------------------------------

GIVEN = {
    "E1": {"evidence_id": "E1", "text": "Dividend rose 12% to 0.60 a share.", "sentiment": "positive"},
    "E2": {"evidence_id": "E2", "text": "Margins keep shrinking.", "sentiment": "negative"},
}


@pytest.mark.parametrize("point, side, reason", [
    ({"claim": "Dividend rose 12%.", "evidence_ids": ["E1"]}, "positive_points", None),
    ({"claim": "Dividend rose.", "evidence_ids": []}, "positive_points", "no citation"),
    ({"claim": "Dividend rose.", "evidence_ids": ["E9"]}, "positive_points", "cites an id it was not given"),
    ({"claim": "Margins fine.", "evidence_ids": ["E2"]}, "positive_points", "cites a sentence of the other polarity"),
    ({"claim": "Dividend rose 15%.", "evidence_ids": ["E1"]}, "positive_points", "number not in cited sentences"),
    ({"claim": " ".join(["word"] * 40), "evidence_ids": ["E1"]}, "positive_points", "too long"),
    ({"claim": "", "evidence_ids": ["E1"]}, "positive_points", "empty"),
])
def test_summary_point_checks(point, side, reason):
    assert sm.check_point(point, side, GIVEN) == reason


def test_validate_separates_kept_from_dropped():
    parsed = {"positive_points": [{"claim": "Dividend rose 12%.", "evidence_ids": ["E1"]},
                                  {"claim": "Invented.", "evidence_ids": ["E7"]}],
              "negative_points": [{"claim": "Margins keep shrinking.", "evidence_ids": ["E2"]}]}
    kept, dropped = sm.validate(parsed, list(GIVEN.values()))
    assert len(kept["positive_points"]) == 1 and len(kept["negative_points"]) == 1
    assert [d["reason"] for d in dropped] == ["cites an id it was not given"]


def test_parse_survives_garbage():
    assert sm.parse("not json") == {"positive_points": [], "negative_points": []}


def test_summarise_one_with_stub_model(monkeypatch):
    def ev(side, n=3):
        return [{"evidence_id": f"E{i}", "source": "reddit", "date": "2026-09-01",
                 "text": f"{side} sentence {i} with 5%", "sentiment": side} for i in range(1, n + 1)]
    monkeypatch.setattr(sm, "gather", lambda bank, aspect, k: (ev("positive"), ev("negative")))
    answer = '{"positive_points":[{"claim":"Good 5%.","evidence_ids":["E1"]}],' \
             '"negative_points":[{"claim":"Bad 5%.","evidence_ids":["E4"]}]}'
    r = sm.summarise_one("DBS", "dividends_capital_returns", 3, "stub", chat=lambda m, msgs: answer)
    assert len(r["positive_points"]) == 1 and len(r["negative_points"]) == 1 and not r["dropped"]


def test_summarise_one_skips_a_side_with_too_little_evidence(monkeypatch):
    pos = [{"evidence_id": "E1", "source": "reddit", "date": "d", "text": "good", "sentiment": "positive"}]
    monkeypatch.setattr(sm, "gather", lambda bank, aspect, k: (pos, []))
    r = sm.summarise_one("DBS", None, 3, "stub", chat=lambda m, msgs: pytest.fail("model must not be called"))
    assert r["positive_points"] == [] and r["evidence"] == []


# --- term extraction -----------------------------------------------------------------

SENT = "DBS raised its dividend but the payout ratio looks thin."


def test_extraction_keeps_only_spans_in_the_sentence():
    raw = ('{"pairs":[{"aspect_term":"payout ratio","opinion_term":"looks thin","polarity":"negative"},'
           '{"aspect_term":"share buyback","opinion_term":"generous","polarity":"positive"},'
           '{"aspect_term":"dividend","opinion_term":"raised","polarity":"great"}]}')
    kept, dropped = et.validate_pairs(raw, SENT)
    assert kept == [{"aspect_term": "payout ratio", "opinion_term": "looks thin", "polarity": "negative"}]
    assert dropped == 2


def test_extraction_bad_json_counts_as_dropped():
    assert et.validate_pairs("oops", SENT) == ([], 1)


def test_gold_parsing_and_scoring():
    assert et.parse_gold("payout ratio => looks thin ; dividend => raised") == [
        ("payout ratio", "looks thin"), ("dividend", "raised")]
    assert et.match_counts([("payout ratio", "looks thin")], [("payout ratio", "looks thin")], False) == (1, 1, 1)
    assert et.match_counts([("ratio", "thin")], [("payout ratio", "looks thin")], False)[0] == 0
    assert et.match_counts([("ratio", "thin")], [("payout ratio", "looks thin")], True)[0] == 1
    assert et.prf(1, 2, 4)["f1"] == pytest.approx(2 * 0.5 * 0.25 / 0.75)


def test_evaluate_ignores_unannotated_rows():
    ex = pd.DataFrame([{"sentence_id": "a", "pairs": [{"aspect_term": "dividend", "opinion_term": "raised",
                                                        "polarity": "positive"}]}])
    gold = pd.DataFrame([{"sentence_id": "a", "gold_pairs": "dividend => raised", "annotator": "e"},
                         {"sentence_id": "b", "gold_pairs": "", "annotator": ""}])
    out = et.evaluate(ex, gold)
    assert out["n_sentences"] == 1 and out["exact"]["f1"] == 1.0


# --- baselines -----------------------------------------------------------------------

def test_baseline_input_has_aspect_token():
    df = pd.DataFrame({"aspect": ["dividends"], "text": ["Payout up."]})
    assert bc.model_input(df) == ["aspect_dividends Payout up."]
    assert bc.model_input(df, with_aspect=False) == ["Payout up."]


def test_macro_f1_interval_contains_estimate_and_paired_diff_of_equals_is_zero():
    y = ["positive", "negative", "neutral"] * 30
    p = [y[i] if i % 5 else "neutral" for i in range(len(y))]
    f1, lo, hi = bc.macro_f1_interval(y, p, boot=300)
    assert lo <= f1 <= hi
    d = bc.paired_bootstrap(y, p, p, boot=200)
    assert d["diff"] == 0 and not d["excludes_zero"]


def test_classical_models_fit_a_tiny_set():
    X = ["aspect_a profit rose strongly", "aspect_a profit surged"] * 6 + ["aspect_a loss widened badly", "aspect_a loss deepened"] * 6
    y = ["positive"] * 12 + ["negative"] * 12
    for name, pipe in bc.models().items():
        assert set(pipe.fit(X, y).predict(["aspect_a profit surged strongly"])) == {"positive"}, name


def test_neural_tokenizer_and_vocab():
    assert bl.tokenize("NIM fell 5.2% in Q3.") == ["nim", "fell", "5.2%", "in", "q", "3", "."]
    vocab = bl.build_vocab(["profit rose", "profit fell", "loss"], min_count=2)
    assert "profit" in vocab and "loss" not in vocab
    enc = bl.encode(["profit unknownword"], vocab, max_len=4)
    assert enc[0, 0] == vocab["profit"] and enc[0, 1] == bl.UNK and enc[0, 2] == bl.PAD
