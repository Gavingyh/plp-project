"""
The progress steps a chatbot turn reports while it runs (chatbot/progress.py),
for a display of its working while the reader waits. Synthetic data only: no
model, no network, no data/plp.db.
"""

import chatbot.agent as agent
from chatbot.progress import Step, describe_call, notify


def _fake_turn(monkeypatch, answer, calls):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "enforce_evidence_mode", lambda: "strip")
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "get_sentiment": lambda **k: {"bank": k["bank"], "window": "all_time", "score": 0.2, "n": 120,
                                      "reading": "slightly positive", "topic_name": "Dividend Policy"}})

    class Model:
        name = model = "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            for name, args in calls:
                execute(name, args)
            return answer
    return Model()


def test_a_turn_reports_its_steps_in_order(monkeypatch):
    model = _fake_turn(monkeypatch, "DBS reads slightly positive, +0.20 on 120 sentences.",
                       [("get_sentiment", {"bank": "DBS", "aspect": "dividend_policy"})])
    steps = []
    r = agent.answer_turn("How is DBS on dividends?", backend=model, verbose=False, on_step=steps.append)
    kinds = [s.kind for s in steps]
    assert kinds == ["read", "intent", "think", "tool", "think", "check", "check", "done"]
    tool = steps[3]
    assert tool.title == "Looked up DBS sentiment on Dividend Policy (all time)"
    assert tool.detail == "+0.20, slightly positive, 120 sentences"
    assert steps[-2].detail == "everything matches what the tools returned"
    assert r.answer.startswith("DBS reads slightly positive")


def test_a_flagged_figure_shows_in_the_check_step(monkeypatch):
    model = _fake_turn(monkeypatch, "DBS scored +0.45 on 120 sentences.",
                       [("get_sentiment", {"bank": "DBS"})])
    steps = []
    agent.answer_turn("How is DBS?", backend=model, verbose=False, on_step=steps.append)
    assert "flagged" in steps[-2].detail and "0.45" in steps[-2].detail


def test_a_set_reply_says_what_kind_of_question_it_was(monkeypatch):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: "advice")
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: "I can't give advice.")
    steps = []
    agent.answer_turn("Should I buy DBS?", verbose=False, on_step=steps.append)
    assert [s.kind for s in steps] == ["read", "intent", "done"]
    assert steps[1].detail == "an investment-advice question"


def test_a_failing_display_never_breaks_the_answer(monkeypatch):
    model = _fake_turn(monkeypatch, "DBS reads slightly positive.", [("get_sentiment", {"bank": "DBS"})])

    def broken(step):
        raise RuntimeError("display gone")
    r = agent.answer_turn("How is DBS?", backend=model, verbose=False, on_step=broken)
    assert r.answer.startswith("DBS reads slightly positive")


def test_no_callback_changes_nothing(monkeypatch):
    model = _fake_turn(monkeypatch, "DBS reads slightly positive.", [("get_sentiment", {"bank": "DBS"})])
    assert agent.answer_turn("How is DBS?", backend=model, verbose=False).answer.startswith("DBS reads")
    notify(None, Step("done", "Done"))


def test_each_tool_is_described_in_words():
    assert describe_call("compare_banks", {"aspect": "dividend_policy"},
                         {"window": "all_time", "banks": {"DBS": {"score": 0.2, "topic_name": "Dividend Policy"},
                                                          "OCBC": {"score": 0.21}}}).detail == "DBS +0.20; OCBC +0.21"
    assert describe_call("get_trend", {"bank": "UOB"}, {"trend_in_words": "September was up on August."}).detail \
        == "September was up on August."
    search = describe_call("search_evidence", {"query": "DBS dividend", "bank": "DBS"},
                           {"results": [{"source": "arctic_shift"}, {"source": "earnings"}]})
    assert search.title == "Searched what people say about DBS: “DBS dividend”"
    assert search.detail.startswith("2 sentences found, from ")
    assert describe_call("search_evidence", {"query": "q"}, {"results": []}).detail == "nothing found"
    assert describe_call("get_analyst_consensus", {"bank": "UOB"},
                         {"consensus_rating": "hold", "n_analysts": 16, "target_mean": 43.2975}).detail \
        == "hold from 16 analysts, average target 43.30"
    assert describe_call("get_coverage", {"bank": "DBS"}, {"n": 24431, "latest": "2026-09-25T10:37"}).detail \
        == "24,431 sentences, the newest from 2026-09-25"
    assert describe_call("get_sentiment", {"bank": "DBS"}, {"insufficient_data": True}).detail \
        == "not enough sentences to score"
    assert describe_call("get_sentiment", {"bank": "DBS"}, {"error": "boom"}).detail == "It failed: boom"
