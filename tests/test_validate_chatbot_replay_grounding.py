"""
Validation of the grounded chatbot claim on recorded answers: replays the
gold-set runs with CHATBOT_ENFORCE_EVIDENCE=strip (chatbot.replay.replay,
no model) and checks, independently of the tracker's own check, that no
answer keeps evidence no search_evidence call returned:

- every quote of three or more words is a substring of a text a
  search_evidence call returned (only search results count, not other tools);
- every link and every 24-character sentence id was returned by a search;
- an answer with no search mentions no sentence id.

Figures are a separate half of the claim ("flagged"): a figure still in the
answer must be one replay's number check reports, so the live path warns.
"""

import os
import re

import pytest

from chatbot.agent import _BLOCKQUOTE, _QUOTE_PATTERN, _URL_PATTERN, _norm_text, _norm_url
from chatbot.guards import unverified_numbers
from chatbot.judge import load_results
from chatbot.replay import replay

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = ["data/eval/chatbot_eval_results_llama8b_v2_idle.jsonl",
        "data/eval/chatbot_eval_results_llama3b_v2.jsonl"]
_ID = re.compile(r"\b[0-9a-f]{24}\b")


def _searched(calls):
    texts, urls, ids = [], set(), set()
    for c in calls:
        if c.get("name") == "search_evidence" and isinstance(c.get("result"), dict):
            for item in c["result"].get("results") or []:
                texts.append(_norm_text(item.get("text") or ""))
                if item.get("url"):
                    urls.add(_norm_url(item["url"]))
                if item.get("sentence_id"):
                    ids.add(item["sentence_id"])
    return texts, urls, ids


def _unsearched_evidence(answer, calls):
    texts, urls, ids = _searched(calls)
    bad = []
    quotes = [m.group(0)[1:-1] for m in _QUOTE_PATTERN.finditer(answer)]
    quotes += [m.group(1) for m in _BLOCKQUOTE.finditer(answer)]
    for q in quotes:
        pieces = [p for p in re.split(r"\.{3}|…", _norm_text(q)) if len(p.split()) >= 3]
        if pieces and not all(any(p in t for t in texts) for p in pieces):
            bad.append(("quote", q))
    bad += [("url", u) for u in _URL_PATTERN.findall(answer) if _norm_url(u) not in urls]
    bad += [("id", i) for i in _ID.findall(answer) if i not in ids]
    if not ids and re.search(r"sentence[_\s]?id", answer, re.IGNORECASE):
        bad.append(("id mention", "sentence id without a search"))
    return bad


def _load(run):
    path = os.path.join(ROOT, run)
    if not os.path.exists(path):
        pytest.skip(f"{run} not present")
    return load_results(path)


@pytest.mark.parametrize("run", RUNS)
def test_strip_replay_keeps_no_unsearched_evidence(run):
    results = _load(run)
    calls = {r["id"]: r.get("tool_calls", []) for r in results}
    rows = replay(results, "strip")
    assert rows, "nothing replayed"
    found = {r["id"]: _unsearched_evidence(r["answer_after"], calls[r["id"]]) for r in rows}
    found = {k: v for k, v in found.items() if v}
    print(f"\n{run}: {len(rows)} replayed, {sum(r['changed'] for r in rows)} changed, "
          f"citation flags {sum(r['citation_flag_before'] for r in rows)} -> "
          f"{sum(r['citation_flag_after'] for r in rows)}, answers with unverified figures "
          f"{sum(bool(r['figures_before']) for r in rows)} -> {sum(bool(r['figures_after']) for r in rows)}")
    assert not found, found
    assert not any(r["citation_flag_after"] for r in rows)


@pytest.mark.parametrize("run", RUNS)
def test_figures_left_after_strip_are_the_flagged_ones(run):
    """Every figure the model's tools didn't return is still reported by the
    number check after stripping, so the live answer carries the warning."""
    results = _load(run)
    by_id = {r["id"]: r for r in results}
    for row in replay(results, "strip"):
        r = by_id[row["id"]]
        model_results = [c.get("result") for c in r.get("tool_calls", []) if c.get("by") != "harness"]
        assert row["figures_after"] == unverified_numbers(row["answer_after"], model_results, r["question"])
