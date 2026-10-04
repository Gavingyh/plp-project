"""
Tests for the harness around the chatbot model (docs/DESIGN.md decision 19):
the intent classifier's replies, output checks, conversation memory, evidence
packaging and decoding temperature. No model or network calls: backends and
the classifier's answers are fakes. Whether the classifier picks the right
intent is measured, not asserted: chatbot/eval_intent.py.
"""

import json

import pytest

import chatbot.agent as agent
import chatbot.tools as tools
from chatbot.agent import Conversation, answer_turn
from chatbot.guards import unverified_numbers, unverified_sentence_ids


# --- input: intents (chatbot/intent.py; the model's answers are faked here) -----------

def _intent(monkeypatch, name):
    monkeypatch.setattr("chatbot.intent.ollama_chat", lambda model, messages, names: json.dumps({"intent": name}))


def _no_backend(*a, **k):
    raise AssertionError("the model must not be called for this question")


def test_advice_is_answered_without_calling_the_model(monkeypatch):
    _intent(monkeypatch, "advice")
    monkeypatch.setattr(agent, "get_backend", _no_backend)
    r = answer_turn("Should I sell UOB?", verbose=False)
    assert r.guard == "advice" and r.calls == []
    assert "UOB" in r.answer and "financial advice" in r.answer


def test_advice_reply_uses_the_bank_from_the_conversation():
    from chatbot.intent import reply_for
    assert "OCBC" in reply_for("advice", "Should I buy it?", {"banks": ["OCBC"]})


def test_question_only_about_another_bank_gets_its_reply(monkeypatch):
    _intent(monkeypatch, "other_bank")
    monkeypatch.setattr(agent, "get_backend", _no_backend)
    r = answer_turn("What's the sentiment on Maybank?", verbose=False)
    assert r.guard == "other_bank" and "DBS, OCBC and UOB" in r.answer


# --- output check: numbers -------------------------------------------------------

TOOL = [{"bank": "DBS", "score": 0.0627, "n": 49716, "positive_n": 1234,
         "computed_at": "2026-09-26T02:00:00+00:00"}]


@pytest.mark.parametrize("answer", [
    "DBS scores 0.063 across 49,716 mentions.",
    "The score is +0.06 (n=49716).",
    "That is a score of about 6.3%.",
    "About 2.5% of mentions are positive.",            # 1234 / 49716
    "1. Since 2023 the 7-day and 30d views agree.",     # year, list marker, windows
    "Scores were computed on 2026-09-26.",
])
def test_figures_from_the_tools_pass(answer):
    assert unverified_numbers(answer, TOOL, question="") == []


def test_invented_figures_are_flagged():
    assert unverified_numbers("DBS scores 0.41 across 52,000 mentions.", TOOL) == ["0.41", "52,000"]


def test_numbers_the_user_typed_are_not_flagged():
    assert unverified_numbers("Over the last 90 days it was flat.", TOOL, question="last 90 days?") == []


def test_numbers_with_no_tool_call_are_flagged():
    assert unverified_numbers("The score is 0.35.", []) == ["0.35"]


# --- output check: sentence ids ---------------------------------------------------

def test_cited_sentence_ids_must_have_been_retrieved():
    real, fake = "a" * 24, "b" * 24
    assert unverified_sentence_ids(f"see sentence_id {real}", {real}) == []
    assert unverified_sentence_ids(f"see {fake}", {real}) == [fake]


# --- answer_turn end to end with a fake model --------------------------------------

class _ToolUsingBackend:
    name, model = "fake", "fake-model"

    def __init__(self, answer):
        self.answer, self.seen = answer, []

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        self.seen.append({"question": question, "system": system, "history": history})
        tool_executor("get_sentiment", {"bank": "DBS", "aspect": "dividend_policy"})
        return self.answer


@pytest.fixture
def fake_sentiment(monkeypatch):
    monkeypatch.setitem(tools.TOOL_FUNCTIONS, "get_sentiment",
                        lambda **kw: {"bank": kw["bank"], "aspect": kw.get("aspect"),
                                      "score": 0.0291, "n": 13452, "insufficient_data": False})


def test_correct_figure_gets_no_number_warning(fake_sentiment):
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend("Score 0.029 (n=13,452)."),
                    verbose=False)
    assert r.unverified_numbers == [] and "NUMBER CHECK" not in r.answer


def test_wrong_figure_gets_number_warning(fake_sentiment):
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend("Score 0.41 (n=13,452)."),
                    verbose=False)
    assert r.unverified_numbers == ["0.41"] and "NUMBER CHECK" in r.answer


# --- memory -----------------------------------------------------------------------------

def test_follow_up_receives_history_and_state(fake_sentiment, monkeypatch):
    backend = _ToolUsingBackend("Neutral.")
    monkeypatch.setattr(agent, "get_backend", lambda name=None: backend)
    conv = Conversation()
    conv.ask("What is sentiment on DBS dividends?")
    conv.ask("and OCBC?")

    second = backend.seen[1]
    assert [m["role"] for m in second["history"]] == ["user", "assistant"]
    assert second["history"][0]["content"] == "What is sentiment on DBS dividends?"
    assert "bank(s): DBS" in second["system"] and "aspect: dividend_policy" in second["system"]


def test_history_is_trimmed_and_warnings_dropped():
    conv = Conversation()
    conv.turns.append(agent.TurnResult(question="q", answer="x" * 5000 + "\n\n⚠️ NUMBER CHECK: 1"))
    content = conv.history()[1]["content"]
    assert len(content) == agent.HISTORY_ANSWER_CHARS and "⚠️" not in content


def test_only_recent_turns_are_kept():
    conv = Conversation()
    for i in range(6):
        conv.turns.append(agent.TurnResult(question=f"q{i}", answer="a"))
    assert [m["content"] for m in conv.history() if m["role"] == "user"] == ["q3", "q4", "q5"]


def test_conversation_rebuilt_from_messages():
    conv = Conversation.from_messages([{"role": "user", "content": "How is UOB doing?"},
                                       {"role": "assistant", "content": "Neutral."}])
    assert len(conv.turns) == 1 and conv.state["banks"] == ["UOB"]


def test_trace_file_gets_one_line_per_turn(tmp_path, monkeypatch):
    _intent(monkeypatch, "advice")
    monkeypatch.setattr(agent, "get_backend", _no_backend)
    path = tmp_path / "trace.jsonl"
    conv = Conversation(trace_path=str(path))
    conv.ask("Should I buy DBS?")  # answered by its fixed reply, no model needed
    rec = json.loads(path.read_text().strip())
    assert rec["guard"] == "advice" and rec["state_after"]["banks"] == ["DBS"]


# --- evidence packaging -------------------------------------------------------------------

def test_search_evidence_results_are_packaged_for_citing(monkeypatch):
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **k: [
        {"sentence_id": "c" * 24, "text": "DBS raised its dividend.", "bank": "DBS",
         "url": "https://example.com/1", "published_at": "2026-02-10T08:00:00+00:00", "score": 0.81}])
    item = tools.search_evidence("DBS dividend")["results"][0]
    assert item["evidence_id"] == "E1" and item["date"] == "2026-02-10"
    assert item["cite_as"] == f"[DBS, 2026-02-10, sentence_id {'c' * 24}]"
    assert "score" not in item and item["relevance"] == 0.81


# --- decoding temperature -------------------------------------------------------------------

def test_low_temperature_by_default_and_configurable(monkeypatch):
    from chatbot.backends import get_backend
    monkeypatch.delenv("CHATBOT_TEMPERATURE", raising=False)
    assert get_backend("ollama").temperature == 0.2
    monkeypatch.setenv("CHATBOT_TEMPERATURE", "0.5")
    assert get_backend("ollama").temperature == 0.5
    monkeypatch.setenv("CHATBOT_TEMPERATURE", "not-a-number")
    assert get_backend("ollama").temperature == 0.2


def test_ollama_request_carries_temperature_and_history(monkeypatch):
    from chatbot.backends.ollama_backend import OllamaBackend
    sent = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"message": {"role": "assistant", "content": "ok"}}

    def fake_post(url, json=None, timeout=None):
        sent.update(json, messages=list(json["messages"]))  # copy: the backend appends later
        return _Resp()

    monkeypatch.setattr("requests.post", fake_post)
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
    OllamaBackend().ask("now", "sys", [], lambda n, a: "{}", verbose=False, history=history)
    assert sent["options"] == {"temperature": 0.2}
    assert [m["content"] for m in sent["messages"]] == ["sys", "earlier", "reply", "now"]


# --- fixes from the first live evaluation (2026-09-26) -------------------------------

def test_dates_written_in_prose_are_not_figures():
    tool = [{"n": 1218, "latest": "2026-09-24T07:49:30+00:00"}]
    answer = "Based on 1218 observations from June 1st, 2020 to September 24th, 2026 (24 Sep 2026)."
    assert unverified_numbers(answer, tool) == []


def test_figures_quoted_from_retrieved_text_pass():
    tool = [{"results": [{"text": "I have 4400 DBS shares; DBS pays $0.54 per share."}]}]
    assert unverified_numbers('Quote: "I have 4400 DBS shares; DBS pays $0.54 per share."', tool) == []


def test_off_topic_question_gets_its_reply_without_the_model(monkeypatch):
    _intent(monkeypatch, "off_topic")
    monkeypatch.setattr(agent, "get_backend", _no_backend)
    r = answer_turn("What's the weather like in Singapore today?", verbose=False)
    assert r.guard == "off_topic" and "outside what I can help with" in r.answer


def test_gap_between_two_short_quotes_is_not_a_quote():
    from chatbot.agent import _QUOTE_PATTERN
    honest = 'Consensus is "buy". The average target is SGD 78.14; 8 analysts rate it "hold".'
    assert _QUOTE_PATTERN.search(honest) is None
    assert _QUOTE_PATTERN.search('Evidence: "totally made up quote" (sentence_id 999)')


def test_empty_or_braces_answer_is_replaced():
    class _Empty:
        name, model = "fake", "fake"
        def ask(self, *a, **k):
            return "{}"
    r = answer_turn("How is sentiment on DBS?", backend=_Empty(), verbose=False)
    assert r.answer == agent.EMPTY_ANSWER_REPLY


def test_names_with_numbers_are_not_figures():
    assert unverified_numbers("Unlike the COVID-19 period, 3Q24 was calm.", [{"n": 5}]) == []


# --- fixes from the gold-set runs of 2026-10-01 ---------------------------------------

def test_the_classifier_sees_the_conversation():
    from chatbot.intent import build_messages, describe_context
    ctx = describe_context({"banks": ["UOB"], "aspect": "asset_quality"}, "What about its asset quality?")
    last = build_messages("Has that improved lately?", ctx)[-1]["content"]
    assert "bank: UOB" in last and "asset quality" in last and "previous question" in last


def test_follow_up_reaches_the_model_in_a_conversation(fake_sentiment, monkeypatch):
    backend = _ToolUsingBackend("Neutral.")
    monkeypatch.setattr(agent, "get_backend", lambda name=None: backend)
    conv = Conversation()
    conv.ask("What is sentiment on DBS dividends?")
    r = conv.ask("Has that improved lately?")
    assert r.guard is None and len(backend.seen) == 2


INVENTED = ("DBS's dividend sentiment is positive, at 0.0291 on 13,452 sentences.\n\n"
            "Supporting evidence:\n"
            '* "DBS raises its payout ratio to 40%." (sentence_id: 12345, URL: https://example.com/dbs)\n'
            '* "Analysts worry the dividend is unsustainable." (Bloomberg)\n\n'
            "Sample size and time window: 13,452 sentences, all time.\n\n"
            "Caveats: Reddit skews towards DBS.")


def test_strip_removes_the_evidence_section_and_keeps_the_rest():
    out = agent.strip_unsearched_evidence(INVENTED)
    assert out.startswith("DBS's dividend sentiment is positive, at 0.0291")
    assert "12345" not in out and "example.com" not in out and "Bloomberg" not in out
    assert "Sample size and time window" in out and "Caveats" in out


def test_enforcement_is_strip_by_default(fake_sentiment, monkeypatch):
    # Decided 4 Oct 2026: invented evidence is removed unless the setting says otherwise.
    monkeypatch.delenv("CHATBOT_ENFORCE_EVIDENCE", raising=False)
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend(INVENTED), verbose=False)
    assert r.evidence_enforced == "strip" and not r.citation_unverified and "12345" not in r.answer


def test_enforcement_off_still_flags_and_keeps_the_answer(fake_sentiment, monkeypatch):
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "off")
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend(INVENTED), verbose=False)
    assert r.evidence_enforced is None and r.citation_unverified and "12345" in r.answer


def test_strip_mode_removes_invented_evidence_and_says_so(fake_sentiment, monkeypatch):
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend(INVENTED), verbose=False)
    assert r.evidence_enforced == "strip" and not r.citation_unverified
    assert "12345" not in r.answer and "VERIFICATION WARNING" not in r.answer
    assert agent.EVIDENCE_REMOVED_NOTE.strip() in r.answer and r.unverified_numbers == []


def test_search_mode_shows_real_quotes_found_by_the_harness(fake_sentiment, monkeypatch):
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "search")
    seen = {}

    def fake_search(**kw):
        seen.update(kw)
        return {"results": [{"sentence_id": "a" * 24, "text": "DBS kept its dividend at 60 cents.",
                             "url": "u", "cite_as": f"[DBS, 2026-01-01, sentence_id {'a' * 24}]"}]}
    monkeypatch.setitem(tools.TOOL_FUNCTIONS, "search_evidence", fake_search)
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend(INVENTED), verbose=False)
    assert r.evidence_enforced == "search" and not r.citation_unverified
    assert '"DBS kept its dividend at 60 cents."' in r.answer and "12345" not in r.answer
    assert seen["bank"] == "DBS" and seen["aspect"] == "dividend_policy"
    assert [c.get("by") for c in r.calls] == [None, "harness"]


def test_an_answer_that_searched_is_left_alone(monkeypatch):
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    monkeypatch.setitem(tools.TOOL_FUNCTIONS, "search_evidence",
                        lambda **kw: {"results": [{"sentence_id": "b" * 24, "url": "https://x.org/1",
                                                   "text": "Margins held up well this quarter."}]})

    class _Searching:
        name, model = "fake", "fake"
        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "q", "bank": "DBS"})
            return 'Evidence:\n- "Margins held up well this quarter." (https://x.org/1)'
    r = answer_turn("DBS margins?", backend=_Searching(), verbose=False)
    assert r.evidence_enforced is None and "Margins held up" in r.answer and not r.citation_unverified


def test_invented_evidence_in_the_opening_paragraph_is_removed(fake_sentiment, monkeypatch):
    # Until 3 Oct the opening paragraph was kept as written, so this quote stayed
    # (and was flagged) under a note saying the quotes were removed.
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    answer = 'DBS is positive, as "one analyst called the payout safe for years" (Reuters).\n\nEvidence:\n* "made up"'
    r = answer_turn("DBS dividends?", backend=_ToolUsingBackend(answer), verbose=False)
    assert r.evidence_enforced == "strip" and not r.citation_unverified
    assert "payout safe for years" not in r.answer and "made up" not in r.answer
    assert r.answer.startswith("DBS is positive")


def test_tool_selection_ignores_searches_the_harness_made():
    from chatbot.run_eval import _check_tool_selection
    item = {"expected_tool": "search_evidence", "expected_bank": "OCBC"}
    harness_only = [{"name": "get_sentiment", "arguments": {"bank": "OCBC"}},
                    {"name": "search_evidence", "arguments": {"bank": "OCBC"}, "by": "harness"}]
    assert _check_tool_selection(item, harness_only)["correct"] is False
    model_made = [{"name": "search_evidence", "arguments": {"bank": "OCBC"}}]
    assert _check_tool_selection(item, model_made)["correct"] is True


def test_tracker_rebuilt_from_recorded_calls():
    t = agent._ToolCallTracker.from_calls([
        {"name": "get_sentiment", "arguments": {"bank": "DBS"}, "result": {"score": 0.1}},
        {"name": "search_evidence", "arguments": {}, "result": {"results": [{"sentence_id": "c" * 24, "url": "u1"}]}}])
    assert t.search_evidence_called and t.verified_sentence_ids == {"c" * 24} and len(t.calls) == 2


def test_shares_of_an_analyst_breakdown_are_derivable():
    # 1, 7, 8 and 1 of 17 analysts are 6%, 41%, 47% and 6%: flagged as unverified
    # in the 4 Oct live run although they were right.
    result = {"bank": "DBS", "n_analysts": 17, "target_mean": 78.14,
              "rating_breakdown": {"strong_buy": 1, "buy": 7, "hold": 8, "sell": 1, "strong_sell": 0}}
    answer = "Strong buy (6%), buy (41%), hold (47%), sell (6%)."
    assert unverified_numbers(answer, [result]) == []
    assert unverified_numbers("Buy (52%).", [result]) == ["52%"]


def test_shares_of_the_total_are_only_for_objects_made_of_counts():
    # A sentiment row mixes counts with a score, so 20% is not "a count over the sum of everything".
    result = {"score": 0.12, "n": 10, "positive_n": 2, "neutral_n": 6, "negative_n": 2}
    assert unverified_numbers("10% were negative.", [result]) == ["10%"]
    assert unverified_numbers("20% were negative.", [result]) == []


def test_a_plain_decline_counts_as_declining_an_uncovered_bank():
    from chatbot.run_eval import _check_behavior
    item = {"expected_behavior": "decline_or_no_data"}
    assert _check_behavior(item, "I can't help with that part of your question. I cover DBS, OCBC and UOB.")["correct"]
    assert not _check_behavior(item, "HSBC sentiment is broadly positive this month.")["correct"]
