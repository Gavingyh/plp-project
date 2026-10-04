"""
Fifth validation of fix/chatbot-answers (commits 04af72a and 6e8298b): quotes
found by pairing quote marks in order, and the score and data date that
chat_search_evidence now returns. Each test asserts what the grounded chatbot
claim needs; a test that fails because the claim is broken carries
xfail(strict=True). Synthetic data only: no model, no network, no data/plp.db.
"""

import json

import pytest

import chatbot.tools as tools
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.backends.base import withheld_tool_result
from chatbot.guards import unverified_numbers

SID = "a" * 24
REAL = "the dbs app keeps crashing whenever i try to pay my rent"
INVENTED = "ocbc has the worst customer service in singapore by far"


def _tracker():
    item = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
            "text": REAL, "url": "https://news.example/x", "cite_as": f"[DBS, 2026-09-01, sentence_id {SID}]"}
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [item]}}])


def _grounded(answer: str) -> tuple[str, bool]:
    """The answer after strip enforcement, and whether it is still flagged."""
    return enforce_evidence(answer, _tracker(), "q", "strip")


# --- A stray mark before an invented quote ---------------------------------------------

STRAY_MARK = ("Stray quote mark shifts the pairing: an inch or ditto mark before an invented "
              "quote leaves the quote in the answer, unflagged")


@pytest.mark.parametrize("answer", [
    f'The screen is 6" wide. One user said "{INVENTED}".',
    f'Branch had a 55" TV. A user wrote "{INVENTED}"',
    f'Fees: 2" | "{INVENTED}" end',
    f'"{REAL}". The 6" phone. "{INVENTED}"',
])
def test_an_invented_quote_after_a_stray_mark_is_removed_or_flagged(answer):
    out, flagged = _grounded(answer)
    assert "worst customer service" not in out or flagged


# --- Shapes the pairing handles --------------------------------------------------------

@pytest.mark.parametrize("answer", [
    f'"{REAL}" and then "{INVENTED}" and a stray " here',                 # odd number of marks
    f'Users said "{INVENTED}',                                              # left open at the end
    f'A user said "ocbc has the worst customer\nservice in singapore by far".',   # wraps a line
    f'| Bank | Quote |\n|---|---|\n| DBS | "{REAL}" |\n| OCBC | "{INVENTED}" |',
    f'- DBS: "{REAL}"\n- OCBC: "{INVENTED}"',
    f'- OCBC: "{INVENTED}"\n- DBS: "{REAL}"',
    f"«{INVENTED}»",
    f"> {INVENTED}",
])
def test_an_invented_quote_is_removed_and_a_real_one_kept(answer):
    out, flagged = _grounded(answer)
    assert "worst customer" not in out and not flagged
    if REAL in answer:
        assert REAL in out


def test_a_real_quote_wrapping_a_line_is_kept_unflagged():
    answer = f'A user said "the dbs app keeps crashing whenever\ni try to pay my rent" [DBS, 2026-09-01, sentence_id {SID}]'
    out, flagged = _grounded(answer)
    assert out == answer and not flagged


def test_a_three_word_invented_quote_is_removed():
    out, flagged = _grounded('People call it "a total scam".')
    assert "total scam" not in out and not flagged


# --- The score and data date a search now returns ---------------------------------------

def _fake_search(monkeypatch):
    hits = [{"sentence_id": c * 24, "bank": "DBS", "source": s, "published_at": "2026-09-0%dT00:00:00" % i,
             "text": t, "url": u, "score": 0.9 - i / 10}
            for i, (c, s, t, u) in enumerate([
                ("a", "arctic_shift", "reddit secret words about the app", "https://www.reddit.com/r/x"),
                ("b", "cna", "cna secret words about the app", "https://cna.example/x"),
                ("c", "google_news", "news words about the app", "https://news.example/x")], 1)]
    monkeypatch.setattr(tools, "_search_evidence", lambda q, **kw: [dict(h) for h in hits])
    monkeypatch.setattr(tools, "get_sentiment", lambda bank, aspect=None, window="all_time": {
        "bank": bank, "aspect": aspect, "window": window, "score": 0.12, "n": 300, "positive_n": 90,
        "neutral_n": 180, "negative_n": 30, "insufficient_data": False})
    monkeypatch.setattr(tools, "_data_runs_to", lambda bank=None: "2026-09-25")


@pytest.mark.parametrize("aspect, key", [(None, "bank_overall_score"), ("dividend_policy", "topic_score")])
def test_the_score_reaches_gemini_and_reddit_and_cna_text_do_not(monkeypatch, aspect, key):
    _fake_search(monkeypatch)
    raw = _tracker().execute("search_evidence", {"query": "app", "bank": "DBS",
                                                 **({"aspect": aspect} if aspect else {})})
    sent = withheld_tool_result("search_evidence", raw)
    content = json.loads(sent)
    assert content[key]["score"] == 0.12 and content[key]["positive_pct"] == 30.0
    assert content["data_runs_to"] == "2026-09-25"
    assert "reddit secret" not in sent and "cna secret" not in sent and "reddit.com" not in sent
    assert "news words about the app" in sent


def test_figures_from_the_search_score_are_not_flagged(monkeypatch):
    _fake_search(monkeypatch)
    t = _ToolCallTracker()
    t.execute("search_evidence", {"query": "app", "bank": "DBS"})
    answer = "DBS reads slightly positive at +0.12 over 300 sentences, 30% positive, data to 25 September 2026."
    assert unverified_numbers(answer, [c["result"] for c in t.calls]) == []
