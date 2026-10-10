"""
Validation of four reviewer findings on the chatbot's reader-facing changes.
Each test asserts the correct behaviour, so it fails while the
finding is real; a confirmed finding carries xfail(strict=True). Synthetic
data only: no database, no Ollama.
"""

import pytest

import chatbot.agent as agent
from chatbot import tools
from chatbot.agent import Conversation, _ToolCallTracker, answer_turn
from chatbot.guards import unverified_numbers


# --- Year-less date regex hides figures -------------------------------------------------

@pytest.mark.parametrize("answer, figure", [
    ("A score of 0.45 may suggest caution.", "0.45"),
    ("Only 47 may be reliable.", "47"),
    ("In September 45 sentences were negative.", "45"),
])
def test_a_figure_beside_a_month_word_is_still_checked(answer, figure):
    assert unverified_numbers(answer, [{"score": 0.12, "n": 300}]) == [figure]


# --- Trend sentence contradicts its figures ---------------------------------------------

def test_month_on_month_words_agree_with_the_figures_they_print():
    series = [{"period": "2026-08", "score": 0.44, "n": 200},     # raw about 0.45
              {"period": "2026-09", "score": 0.27, "n": 6}]       # raw about 0.50
    r = tools._month_on_month(series)
    print(f"\n{r['trend_in_words']}")
    latest, previous = r["latest_month"]["score"], r["previous_month"]["score"]
    if r["month_on_month"] == "up":
        assert latest > previous, r["trend_in_words"]
    elif r["month_on_month"] == "down":
        assert latest < previous, r["trend_in_words"]


# --- Model-chosen aspect exempts invented quotes ----------------------------------------

def test_a_quote_of_the_models_own_aspect_argument_is_unverified():
    text = "customers are furious about the outage"
    tracker = _ToolCallTracker.from_calls([{
        "name": "get_sentiment", "arguments": {"bank": "DBS", "aspect": text},
        "result": {"bank": "DBS", "aspect": text, "insufficient_data": True, "topic_name": text}}])
    assert tracker.answer_has_unverified_citation(f'One customer said "{text}".')


# --- Numbered markers leak into follow-ups ----------------------------------------------

EARLIER = ("DBS is slightly positive on dividends [1], though some worry about fees [2].\n\n"
           "Sources:\n- [1] news, DBS, 2 Sep 2026: https://news.example/dbs\n"
           "- [2] Reddit, DBS, 3 Sep 2026: https://www.reddit.com/r/singapore/comments/abc/")


class _LocalModel:
    name, model = "ollama", "fake"

    def __init__(self, answer):
        self.answer, self.history = answer, None

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        self.history = history
        return self.answer


def test_a_follow_up_citing_an_earlier_number_without_a_search_is_flagged(monkeypatch):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    conv = Conversation.from_messages([{"role": "user", "content": "How is DBS?"},
                                       {"role": "assistant", "content": EARLIER}])
    history = conv.history()
    kept = "Sources:" in history[-1]["content"] and "reddit.com" in history[-1]["content"]
    model = _LocalModel("As noted in [2], it fell.")
    r = answer_turn("And fees?", backend=model, history=history, verbose=False)
    print(f"\nhistory keeps Sources and links: {kept}; citation_unverified: {r.citation_unverified}")
    assert not kept or r.citation_unverified
