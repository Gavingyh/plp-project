"""
Re-validation of the grounded chatbot claim after the fixes of 4 Oct 2026
(commit 8082469): probes of each fix beyond the tests that guard it.

- the year-less date patterns in chatbot/guards.py (lower-case months,
  "Sept.", a day before "%", a day at a sentence end, counts listed by month);
- the bare "[n]" marker check (_BARE_MARK in chatbot/agent.py) on correct
  answers and on other invented markers;
- the topic-name exemption (_TOPIC_NAMES);
- the trend sentence's "unclear" case (_settled in chatbot/tools.py) on the
  7-day/30-day path and the monthly path;
- the strip replay over every recorded *_v2 gold-set run.

Synthetic data only, except the replay, which reads recorded runs under
data/eval/. No model, no network, no data/plp.db.
"""

import glob
import os
import random

import pytest

from chatbot import tools
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from chatbot.judge import load_results
from chatbot.replay import replay

# A date written without its year is skipped only when a tool returned it (4 Oct 2026),
# as a real answer's date always is (data_runs_to): these tests give the tools that date.
TOOL = [{"bank": "DBS", "score": 0.31, "n": 120}]
TOOL_DATES = TOOL + [{"data_runs_to": d} for d in ("2026-09-25", "2026-09-30", "2026-10-24")]


# --- year-less dates in the number check ------------------------------------------------

@pytest.mark.parametrize("answer, figure", [
    ("Negative share was 25% in September.", "25%"),
    ("In September 25% of sentences were negative.", "25%"),
    ("June 30.5% of sentences were negative.", "30.5%"),
    ("In Sept. 30.5 percent were negative.", "30.5"),
    ("Mentions rose to 47 in may.", "47"),
    ("On 25 Sept. 47 new posts appeared.", "47"),
    ("Sentences rose to 25 in May.", "25"),
])
@pytest.mark.parametrize("tools", [TOOL, TOOL_DATES], ids=["no tool dates", "with data_runs_to"])
def test_an_invented_figure_near_a_month_is_flagged(answer, figure, tools):
    # Real answers always carry data_runs_to; without it here, a date rule that swallowed
    # "25.7%" after a returned 25 September passed (fourth validation, 4 Oct 2026).
    assert figure in unverified_numbers(answer, tools)


@pytest.mark.parametrize("answer", [
    "The data runs to Sept. 25.",
    "The data runs to 25 Sept.",
    "The data runs to Sep 30",
    "The data runs to September 25th; OCBC's to 24 Oct.",
])
def test_a_real_year_less_date_is_not_a_figure(answer):
    assert unverified_numbers(answer, TOOL_DATES) == []


@pytest.mark.parametrize("answer, figures", [
    ("Negative sentences by month: July 18, August 24, September 29.", ["18", "24", "29"]),
    ("Negative sentences by month: 18 July, 24 August, 29 September.", ["18", "24", "29"]),
    ("Mentions in May 25.", ["25"]),
])
def test_counts_listed_by_month_are_checked(answer, figures):
    assert unverified_numbers(answer, TOOL) == figures


@pytest.mark.parametrize("answer", ["The data runs to september 25th.", "The data runs to 25 september."])
def test_a_lower_case_year_less_date_is_not_a_figure(answer):
    assert unverified_numbers(answer, TOOL_DATES) == []


# --- the bare [n] marker check ------------------------------------------------------------

SID = "a" * 24
# A real stored sentence (yahoo_news) has a footnote marker in its text.
FOOTNOTE_TEXT = ("ASEAN consumers remained optimistic about both the macroeconomic environment and "
                 "their personal finances in 2026, with the UOB ASEAN Consumer Sentiment Index "
                 "(the Index)[1] holding steady at 54.")
ITEM = {"sentence_id": SID, "bank": "UOB", "source": "yahoo_news", "date": "2026-09-02",
        "text": FOOTNOTE_TEXT, "url": "https://news.example/uob",
        "cite_as": f"[UOB, 2026-09-02, sentence_id {SID}]"}


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"results": [dict(ITEM)], "n_found": 1}}])


def test_a_markdown_list_with_real_citations_is_not_flagged():
    answer = (f"Highlights:\n- UOB: upbeat {ITEM['cite_as']}\n- DBS: steady\n1. first\n2. second\n"
              f"[the article](https://news.example/uob)")
    assert not _searched().answer_has_unverified_citation(answer)


@pytest.mark.parametrize("mode", ["off", "strip"])
def test_a_verbatim_quote_with_a_footnote_marker_passes_unchanged(mode):
    answer = f'UOB coverage is upbeat: "{FOOTNOTE_TEXT}" {ITEM["cite_as"]}'
    out, flagged = enforce_evidence(answer, _searched(), "UOB?", mode)
    assert not flagged
    assert out == answer


@pytest.mark.parametrize("marker", ["[2, 3]", "[2-3]", "[100]"])
def test_an_invented_multi_number_marker_is_flagged_or_stripped(marker):
    answer = f"UOB is upbeat {ITEM['cite_as']}; fees worry readers {marker}."
    tracker = _searched()
    out, flagged = enforce_evidence(answer, tracker, "UOB?", "strip")
    assert flagged or marker not in out


def test_a_single_invented_marker_is_stripped():
    answer = f"UOB is upbeat {ITEM['cite_as']}; fees worry readers [2]."
    out, flagged = enforce_evidence(answer, _searched(), "UOB?", "strip")
    assert "[2]" not in out and not flagged


# --- the topic-name exemption ----------------------------------------------------------------

def _sentiment_call(aspect, topic_name):
    return {"name": "get_sentiment", "arguments": {"bank": "DBS", "aspect": aspect},
            "result": {"bank": "DBS", "aspect": aspect, "insufficient_data": False, "score": 0.2,
                       "n": 100, "topic_name": topic_name, "reading": "moderately positive"}}


def test_a_real_topic_name_and_reading_may_be_quoted():
    from config import aspect_taxonomy
    key, name = next(iter(aspect_taxonomy.labels().items()))
    tracker = _ToolCallTracker.from_calls([_sentiment_call(key, name)])
    assert not tracker.unverified_quotes(f'On "{name}", DBS reads "moderately positive".', strict=True)


def test_a_made_up_topic_name_cannot_vouch_for_a_quote(monkeypatch):
    invented = "the app crashed three times while i was paying rent"
    tracker = _ToolCallTracker.from_calls([_sentiment_call(invented, invented)])
    assert tracker.answer_has_unverified_citation(f'One customer wrote "{invented}".')


def test_the_real_tool_never_names_a_made_up_aspect(monkeypatch):
    monkeypatch.setattr(tools, "get_sentiment", lambda bank, aspect=None, window="all_time": {
        "bank": bank, "aspect": aspect, "insufficient_data": True})
    monkeypatch.setattr(tools, "_data_runs_to", lambda bank=None: "2026-10-01")
    invented = "customers are furious about the outage"
    out = tools.chat_get_sentiment("DBS", invented)
    assert out["topic_name"] is None


# --- the trend sentence's "unclear" case ------------------------------------------------------

def _win(score, n):
    p = n // 2
    return {"bank": "DBS", "aspect": "ALL", "score": score, "n": n, "insufficient_data": False,
            "positive_n": p, "neutral_n": n - p, "negative_n": 0}


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(tools, "_data_runs_to", lambda bank=None: "2026-10-01")


def _weekly(monkeypatch, rs, rn, bs, bn):
    r, b = _win(rs, rn), _win(bs, bn)
    delta = round(round(tools._unshrunk(r), 4) - round(tools._unshrunk(b), 4), 4)
    d = "improving" if delta > 0.02 else "declining" if delta < -0.02 else "stable"
    monkeypatch.setattr(tools, "get_trend", lambda bank, aspect=None: {
        "bank": bank, "aspect": "ALL", "trend_available": True, "direction": d,
        "delta_7d_vs_30d": delta, "recent_7d": r, "baseline_30d": b, "monthly_series": []})
    return tools.chat_get_trend("DBS")


def test_weekly_trend_is_unclear_when_printed_scores_point_the_other_way(monkeypatch, no_db):
    out = _weekly(monkeypatch, 0.27, 10, 0.30, 400)       # unshrunk +0.10, printed 0.27 < 0.30
    assert out["direction"] == "unclear"
    assert "up on" not in out["trend_in_words"] and "+0.27, 10 sentences" in out["trend_in_words"]


def test_monthly_trend_is_unclear_when_printed_scores_point_the_other_way(monkeypatch, no_db):
    monkeypatch.setattr(tools, "get_trend", lambda bank, aspect=None: {**_win(0.3, 500), "trend_available": False})
    monkeypatch.setattr(tools, "_monthly_series", lambda b, a: ([{"period": "2026-08", "score": 0.44, "n": 200},
                                                                 {"period": "2026-09", "score": 0.27, "n": 6}], None))
    out = tools.chat_get_trend("DBS")
    assert out["month_on_month"] == "unclear" and "up on" not in out["trend_in_words"]


def test_trend_words_never_contradict_the_printed_scores(monkeypatch, no_db):
    """20,000 random pairs on each path: "up" only beside a higher printed
    score, "down" beside a lower one, "about the same" within 0.02."""
    rng, bad = random.Random(0), []
    printed = lambda s: float(f"{s:+.2f}")                 # noqa: E731
    for _ in range(20000):
        rs, bs = round(rng.uniform(-0.6, 0.6), 4), round(rng.uniform(-0.6, 0.6), 4)
        if rng.random() < 0.5:
            bs = round(rs + rng.uniform(-0.04, 0.04), 4)
        rn, bn = rng.randint(10, 400), rng.randint(10, 400)
        pr, pb = printed(rs), printed(bs)
        for path, word in (
                ("7d", _weekly(monkeypatch, rs, rn, bs, bn)["direction"]),
                ("month", tools._month_on_month([{"period": "2026-08", "score": bs, "n": bn},
                                                 {"period": "2026-09", "score": rs, "n": rn}])["month_on_month"])):
            if (word in ("improving", "up") and not pr > pb) or (word in ("declining", "down") and not pr < pb) \
                    or (word in ("stable", "about the same") and abs(pr - pb) > 0.02 + 1e-9):
                bad.append((path, rs, rn, bs, bn, word))
    assert not bad, bad[:5]


# --- strip replay over every recorded v2 run -------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "data/eval/chatbot_eval_results_*_v2*.jsonl")))


def _tool_wording(calls):
    """Readings and real topic names a tool returned: the claim lets an answer quote them."""
    from chatbot.agent import _TOPIC_NAMES, _norm_text
    out = set()

    def walk(o, key=None):
        if isinstance(o, str) and key in ("reading", "topic_name"):
            if key == "reading" or _norm_text(o) in _TOPIC_NAMES:
                out.add(_norm_text(o).strip(" .,;:"))
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
    for c in calls:
        walk(c.get("result"))
    return out


@pytest.mark.parametrize("run", RUNS)
def test_strip_replay_of_every_v2_run_keeps_no_unflagged_unsearched_evidence(run):
    """After strip, an answer keeps no evidence a search didn't return, or is
    flagged (the claim: such answers are flagged, and strip removes evidence)."""
    from chatbot.agent import _norm_text
    from tests.test_validate_chatbot_replay_grounding import _unsearched_evidence
    results = load_results(os.path.join(ROOT, run))
    calls = {r["id"]: r.get("tool_calls", []) for r in results}
    rows = replay(results, "strip")
    found = {}
    for r in rows:
        wording = _tool_wording(calls[r["id"]])
        bad = [b for b in _unsearched_evidence(r["answer_after"], calls[r["id"]])
               if not (b[0] == "quote" and _norm_text(b[1]).strip(" .,;:") in wording)]
        if bad:
            found[r["id"]] = (r["citation_flag_after"], bad)
    print(f"\n{run}: {len(rows)} replayed, {sum(r['changed'] for r in rows)} changed, citation flags "
          f"{sum(r['citation_flag_before'] for r in rows)} -> {sum(r['citation_flag_after'] for r in rows)}, "
          f"left with unsearched evidence {len(found)} (flagged {sum(f[0] for f in found.values())})")
    assert all(flagged for flagged, _ in found.values()), found
