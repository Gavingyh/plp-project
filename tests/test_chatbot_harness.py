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


# --- quote detection: two detectors together (validation, 4 Oct 2026) -------------------
# Five validations each found a quote shape the detector of the day missed: the pattern
# knows a quote by what stands around its marks, the pairing of marks in order doesn't
# care. Both now run, the pairing only between the pattern's quotes.

QUOTE_SID = "f" * 24
QUOTED_REAL = 'What do you think of "DBS Robot" with the 0.5% fees?'    # a Reddit sentence with a quote in it
QUOTED_INVENTED = "OCBC will cut its dividend next year for sure"


def _quote_tracker():
    item = {"sentence_id": QUOTE_SID, "bank": "DBS", "source": "arctic_shift", "date": "2026-09-01",
            "text": QUOTED_REAL, "url": "https://r.example/x", "cite_as": f"[DBS, 2026-09-01, sentence_id {QUOTE_SID}]"}
    return agent._ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                               "result": {"results": [item]}}])


@pytest.mark.parametrize("answer, kept", [
    (f'The screen is 6" wide. One user said "{QUOTED_INVENTED}".', 'The screen is 6" wide. One user said.'),
    (f'On a 6" phone "{QUOTED_INVENTED}" ok', 'On a 6" phone ok'),
    (f'Fees: 2" | "{QUOTED_INVENTED}" end', 'Fees: 2" | end'),
    (f'Consensus is "buy" but one user said "{QUOTED_INVENTED}"(Reddit) and others rate it "hold".',
     'Consensus is "buy" but one user said (Reddit) and others rate it "hold".'),
    # A closing mark whose opening was lost, then a quote the pattern can't see. Since the seventh
    # validation (5 Oct 2026) a mark the detectors can't place takes its line with it: what it
    # quotes can't be checked (until then the line was kept as 'The app is bad" and then one
    # user said (Reddit).').
    (f'The app is fine.\nThe app is bad" and then one user said "{QUOTED_INVENTED}"(Reddit).',
     'The app is fine.'),
])
def test_strip_removes_the_invented_quote_and_never_the_text_between_two_quotes(answer, kept):
    out = agent.enforce_evidence(answer, _quote_tracker(), "q", "strip")
    assert out == (kept + agent.EVIDENCE_UNMATCHED_NOTE, False)


@pytest.mark.parametrize("answer", [
    'The screen is 6" wide and bright.',
    'Branch had a 55" TV and a "queue" display.',
    "Analysts rate DBS a 'strong buy' and OCBC a 'buy'.",
    "Since the '08 crisis the three banks' margins rose.",
    "OCBC's and DBS's apps don't crash, the banks' teams say.",
])
def test_an_inch_mark_an_apostrophe_or_a_term_in_quote_marks_is_no_quote(answer):
    assert agent._QUOTE_PATTERN.findall(answer) == []


def test_quotes_are_found_in_text_order_and_never_overlap():
    answer = (f'"{QUOTED_REAL}" and a 6" phone, then "{QUOTED_INVENTED}"(Reddit), «another quote here» and '
              "'a single quoted passage runs here' and “a curly quote here”.")
    spans = list(agent._QUOTE_PATTERN.finditer(answer))
    assert [m.group(0) for m in spans] == [
        '"What do you think of "', '" with the 0.5% fees?"', f'"{QUOTED_INVENTED}"',
        "«another quote here»", "'a single quoted passage runs here'", "“a curly quote here”"]
    assert all(a.end() <= b.start() for a, b in zip(spans, spans[1:]))


def test_a_quote_the_pattern_finds_stops_an_unclosed_one_shifting_the_pairs():
    # 04af72a paired the unclosed quote's mark with the next quote's opening, hiding the next quote.
    answer = f'- One said "a nightmare to use.\n- Another wrote "{QUOTED_INVENTED}"(Reddit).'
    assert agent._QUOTE_PATTERN.findall(answer) == ['"a nightmare to use.', f'"{QUOTED_INVENTED}"']


def test_a_real_quote_with_a_quote_inside_it_passes_and_an_invented_ending_does_not():
    answer = f'One user asked "{QUOTED_REAL}" [DBS, 2026-09-01, sentence_id {QUOTE_SID}]'
    assert agent.enforce_evidence(answer, _quote_tracker(), "q", "strip") == (answer, False)
    invented = answer.replace("with the 0.5% fees?", "a total scam that will collapse soon")
    out, flagged = agent.enforce_evidence(invented, _quote_tracker(), "q", "strip")
    assert "collapse soon" not in out or flagged


def test_a_marker_left_by_dropping_one_inside_it_goes_too_and_both_are_checked(monkeypatch):
    # Validation, 4 Oct 2026: "[1[2]]" left "[1]" after the drop, and noting it crashed the turn.
    tracker = agent._ToolCallTracker()
    assert agent.enforce_evidence("See note [12[34]] here.", tracker, "q", "strip") == ("See note here.", False)
    assert sorted(tracker.dropped_marks) == ["[12]", "[34]"]
    _intent(monkeypatch, None)

    class _Model:
        name = model = "fake"

        def ask(self, *a, **k):
            return "DBS reads slightly positive [12[34]]."

    r = answer_turn("How is DBS?", backend=_Model(), verbose=False)
    assert "[" not in r.answer and sorted(r.unverified_numbers) == ["12", "34"]


@pytest.mark.parametrize("answer, quotes", [
    # Opened straight, closed curly, wrapped onto the next line: once only its first line was read.
    ('One user said "OCBC will cut its\ndividend next year for sure”',
     ['"OCBC will cut its\ndividend next year for sure”']),
    # An unclosed curly quote, then a straight one: the curly mark mustn't take the next quote's opening.
    (f'One user called the app “a nightmare to use. Another wrote "{QUOTED_INVENTED}" ok.',
     ["“a nightmare to use. Another wrote", f'"{QUOTED_INVENTED}"']),
    # A quote never runs past its closing mark of the other style to a later mark.
    ('"the app keeps crashing on payday”(Reddit) \n- Fees: 2" |', ['"the app keeps crashing on payday”']),
    ('"the app keeps crashing on payday”[2] The screen is 6" wide.', ['"the app keeps crashing on payday”']),
    ('|“the app keeps crashing on payday"| Another wrote “the app keeps crashing on payday”and',
     ['“the app keeps crashing on payday"', "“the app keeps crashing on payday”"]),
    ('“the app keeps crashing on payday “the fees are far too high for me”',
     ["“the app keeps crashing on payday", "“the fees are far too high for me”"]),
    # A quote left open stops before its citation, as the pairing's always did.
    (f'"the app keeps crashing on payday [DBS, 2026-09-01, sentence_id {QUOTE_SID}]',
     ['"the app keeps crashing on payday']),
])
def test_mixed_quote_marks_close_where_the_quote_does(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


# --- quote detection after the sixth validation (5 Oct 2026) -----------------------------
# A straight mark, or a closing mark used to open, now opens where no letter or digit stands
# before it and closes where none follows; a straight quote may hold curly ones and a curly
# quote straight ones, checked whole; a single-quoted passage counts from six words.

QUOTE_A = "the app keeps logging me out every single time i open it"
QUOTE_B = "fees are far too high for retail customers like me"
QUOTE_INVENTED_TAIL = "and they said the bank cheats everyone"


def _two_quote_tracker():
    items = [{"sentence_id": c * 24, "bank": "DBS", "source": "arctic_shift", "date": "2026-09-01", "text": t,
              "url": f"https://r.example/{c}", "cite_as": f"[DBS, 2026-09-01, sentence_id {c * 24}]"}
             for c, t in (("a", QUOTE_A), ("b", QUOTE_B))]
    return agent._ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                               "result": {"results": items}}])


@pytest.mark.parametrize("answer, quotes", [
    # Beside a bracket, a table bar or a closing mark used to open: the pattern finds these itself now.
    (f'One said "{QUOTE_A}"(Reddit) and "{QUOTE_B}"|', [f'"{QUOTE_A}"', f'"{QUOTE_B}"']),
    (f"| DBS |”{QUOTE_A}”| x |", [f"”{QUOTE_A}”"]),
    (f"One said ”{QUOTE_A}”(Reddit).", [f"”{QUOTE_A}”"]),
    (f"|DBS|»{QUOTE_A}«|", [f"»{QUOTE_A}«"]),
    # Markdown emphasis still opens and closes a quote: "_" is no letter or digit here.
    (f'He said _"{QUOTE_A}"_ today.', [f'"{QUOTE_A}"']),
    # A quote holding a quote in the other style is one quote.
    (f'One wrote “I asked them "{QUOTE_A}" {QUOTE_INVENTED_TAIL}” ok',
     [f'“I asked them "{QUOTE_A}" {QUOTE_INVENTED_TAIL}”']),
    (f'One wrote "I asked them “{QUOTE_A}” {QUOTE_INVENTED_TAIL}" ok',
     [f'"I asked them “{QUOTE_A}” {QUOTE_INVENTED_TAIL}"']),
    # The closing mark of one quote and the opening mark of the next are no quote inside a quote.
    (f'Users: “{QUOTE_A}" and "{QUOTE_B}” today.', [f'“{QUOTE_A}"', f'"{QUOTE_B}”']),
    # Nor, around a quote between them, in a quote with mixed marks or in angle marks (these hold none).
    (f'“ {QUOTE_INVENTED_TAIL} "; one said “{QUOTE_B}” and ”{QUOTE_A}”.',
     [f'“ {QUOTE_INVENTED_TAIL} "', f"“{QUOTE_B}”", f"”{QUOTE_A}”"]),
    (f'Users wrote: » {QUOTE_B} «, while "{QUOTE_A}" and »{QUOTE_INVENTED_TAIL}«.',
     [f'"{QUOTE_A}"', f"»{QUOTE_INVENTED_TAIL}«"]),
    # An unclosed quote before one the pattern finds: the pairing checks the fragment before it.
    (f'One said "{QUOTE_A}. Another wrote "{QUOTE_B}"(Reddit) and more.',
     [f'"{QUOTE_A}. Another wrote', f'"{QUOTE_B}"']),
    # The closing mark of a short quote, after punctuation, opens nothing.
    ('"Bad!"(Reddit) and the rest of the line runs on here', []),
    ('Analysts rated it "buy!". The average target is SGD 78.14 now.', []),
    ('It is a 6" phone, "cheap!"(Reddit) and light', []),
])
def test_quotes_beside_brackets_bars_and_nested_quotes(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


@pytest.mark.parametrize("answer", [
    f'One wrote “I asked them "{QUOTE_A}" {QUOTE_INVENTED_TAIL}” [DBS, 2026-09-01, sentence_id {"a" * 24}]',
    f'One wrote "I asked them “{QUOTE_A}” {QUOTE_INVENTED_TAIL}" [DBS, 2026-09-01, sentence_id {"a" * 24}]',
])
def test_strip_removes_a_quote_whose_words_after_a_real_inner_quote_are_invented(answer):
    out, flagged = agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip")
    assert "cheats everyone" not in out and not flagged


@pytest.mark.parametrize("answer", [
    f'Users: “{QUOTE_A}" and "{QUOTE_B}” today.',
    f'One said "{QUOTE_A}"(Reddit) and | DBS |”{QUOTE_B}”| x |',
])
def test_real_quotes_in_these_shapes_are_kept_unflagged(answer):
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == (answer, False)


def test_a_real_sentence_with_a_quote_in_it_may_be_quoted_in_curly_marks():
    answer = f'One user asked “{QUOTED_REAL}” [DBS, 2026-09-01, sentence_id {QUOTE_SID}]'
    assert agent._QUOTE_PATTERN.findall(answer) == [f"“{QUOTED_REAL}”"]
    assert agent.enforce_evidence(answer, _quote_tracker(), "q", "strip") == (answer, False)


@pytest.mark.parametrize("answer, quotes", [
    ("DBS's 'customer first digital approach' is praised.", []),          # a scare quote, five words or fewer
    ("Analysts see it as 'a clear buy on value'.", []),                     # five words, no quoting word before
    # Since the seventh validation (5 Oct 2026) "call" is a quoting word in every form, so
    # "Analysts call it 'a clear buy on value'." is a quote to check (until then, not one).
    ("Analysts call it 'a clear buy on value'.", ["'a clear buy on value'"]),
    ("One said 'the app logs me out daily now' today.", ["'the app logs me out daily now'"]),   # six words
    (f"| DBS |'{QUOTE_A}'| x |", [f"'{QUOTE_A}'"]),                        # opened after a table bar
])
def test_a_single_quoted_passage_counts_from_six_words(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


INCH_TAIL = 'my 6" phone is the worst and DBS will cut its dividend'


@pytest.mark.parametrize("marks", [("“", "”"), ('"', '"'), ("«", "»"), ("»", "«"), ('"', "”"), ("”", "”")])
def test_a_quote_holding_an_inch_mark_is_one_quote_and_checked(marks):
    # Since 6e1560f a curly quote held no straight mark, so this one went unchecked; on main it was flagged.
    answer = f"One said {marks[0]}{INCH_TAIL}{marks[1]}."
    assert agent._QUOTE_PATTERN.findall(answer) == [f"{marks[0]}{INCH_TAIL}{marks[1]}"]
    out, flagged = agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip")
    assert "cut its dividend" not in out and not flagged


@pytest.mark.parametrize("answer, quotes", [
    # A straight mark after a number still closes a quote long enough to end there.
    ('Analysts said “the target price is SGD 78" on average, and “the dividend looks safe for now”.',
     ['“the target price is SGD 78"', "“the dividend looks safe for now”"]),
    ('The screen is 6" wide and the 55" TV is "far too bright for the branch" ok', ['"far too bright for the branch"']),
])
def test_a_straight_mark_after_a_number_still_closes_or_opens_nothing(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


# --- after the seventh validation (5 Oct 2026) -------------------------------------------
# A quote mark neither detector can place is evidence the checks can't verify: the answer is
# flagged, and strip removes the line holding it, with its citation. Strip also removes the
# words between two removed quotes on one line, and runs again until nothing changes. A
# low-9 mark („) opens a quote; a single-quoted passage counts from three words after a
# quoting word or a colon, or before a citation; a quoted piece is compared without the
# punctuation at its ends.

CITE_A = f"[DBS, 2026-09-01, sentence_id {'a' * 24}]"


@pytest.mark.parametrize("answer, loose", [
    (f'One said “my 5" rate. Another wrote ”{QUOTED_INVENTED}” ok', ["”"]),   # a closing mark, nothing open
    ('The app is bad" and more', ['"']),                                       # its opening mark lost
    ('He said “a scam', ["“"]),                                                # too little after it to quote
    ('A 6" phone and a 2" frame', []),                                         # inch marks
    ('Rated "buy" and “hold”.', []),                                           # short pairs
    ('Rated ”buy” and »hold«.', []),                                           # short pairs opened with a closing mark
    ('the app and a stray " here', []),                                        # a stray straight mark
    (f'“{QUOTE_A}” and "{QUOTE_B}"', []),                                      # marks of the quotes found
])
def test_loose_marks_are_those_no_detector_places(answer, loose):
    assert [answer[i] for i in agent._QUOTE_PATTERN.loose(answer)] == loose


@pytest.mark.parametrize("searched", [True, False], ids=["after a search", "no search"])
@pytest.mark.parametrize("mode", ["off", "strip"])
def test_a_loose_mark_flags_the_answer_and_strip_removes_its_line(searched, mode):
    answer = 'DBS reads slightly positive.\nOne user said the bank cheats everyone" in a post.'
    tracker = _two_quote_tracker() if searched else agent._ToolCallTracker()
    assert tracker.answer_has_unverified_citation(answer)
    out, flagged = agent.enforce_evidence(answer, tracker, "q", mode)
    if mode == "off":
        assert (out, flagged) == (answer, True)
    else:
        assert out.startswith("DBS reads slightly positive.\n\n(") and "cheats" not in out and not flagged


def test_strip_after_a_search_removes_the_line_holding_a_loose_mark_with_its_citation():
    kept = f"**DBS** reads slightly positive.\n- “{QUOTE_A}” {CITE_A}"
    answer = f'{kept}\n- “my rate went up to 5" in one post {CITE_A}. Another wrote ”{QUOTED_INVENTED}” {CITE_A}'
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == \
        (kept + agent.EVIDENCE_UNMATCHED_NOTE, False)


@pytest.mark.parametrize("answer, kept", [
    (f'Some said "{QUOTED_INVENTED}" while others, at 0.31, wrote "{QUOTE_INVENTED_TAIL}" today.', "Some said today."),
    # Not past a real quote between them, nor across a line break.
    (f'Some said "{QUOTED_INVENTED}", "{QUOTE_A}" and "{QUOTE_INVENTED_TAIL}" today.',
     f'Some said, "{QUOTE_A}" and today.'),
    (f'Some said "{QUOTED_INVENTED}" here\nand others "{QUOTE_INVENTED_TAIL}" there.', "Some said here\nand others there."),
])
def test_strip_removes_the_words_between_two_removed_quotes_on_one_line(answer, kept):
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == \
        (kept + agent.EVIDENCE_UNMATCHED_NOTE, False)


def test_strip_without_a_search_removes_lines_holding_a_loose_mark_the_first_paragraph_too():
    answer = ("DBS reads slightly positive.\n"
              f'One said “my rate went up to 5" in one post. Another wrote ”{QUOTED_INVENTED}”\n\n'
              'Its score is 0.31.\nUsers say the fees are a scam" in posts.\nMore to come.')
    tracker = agent._ToolCallTracker()
    out, flagged = agent.enforce_evidence(answer, tracker, "q", "strip")
    assert out == "DBS reads slightly positive.\n\nIts score is 0.31.\nMore to come." + agent.EVIDENCE_REMOVED_NOTE
    assert not flagged


def test_strip_runs_again_until_nothing_changes():
    # A real sentence holding a link no search returned: the link goes first, and then the
    # quote, no longer the sentence returned (7446c89 kept it, flagged).
    text = "the report is on the website (https://bank.example/ir) for all to read"
    tracker = agent._ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"}, "result": {
        "results": [{"sentence_id": "a" * 24, "text": text, "url": "https://bank.example/other"}]}}])
    out, flagged = agent.enforce_evidence(f'Capital is sound.\n- {CITE_A}: "{text}"', tracker, "q", "strip")
    assert out == f"Capital is sound.\n- {CITE_A}:" + agent.EVIDENCE_UNMATCHED_NOTE and not flagged


@pytest.mark.parametrize("marks", [("„", "“"), ("„", "”"), ("‟", "”")])
def test_a_quote_in_low_nine_marks_is_checked(marks):
    invented = f"One post said {marks[0]}{QUOTED_INVENTED}{marks[1]} {CITE_A}"
    out, flagged = agent.enforce_evidence(invented, _two_quote_tracker(), "q", "strip")
    assert "next year for sure" not in out and not flagged
    real = f"One post said {marks[0]}{QUOTE_A}{marks[1]} {CITE_A}"
    assert agent.enforce_evidence(real, _two_quote_tracker(), "q", "strip") == (real, False)


@pytest.mark.parametrize("answer, quotes", [
    ("One user wrote 'banks charge hidden fees' today.", ["'banks charge hidden fees'"]),   # a quoting word
    ("One user: 'banks charge hidden fees' today.", ["'banks charge hidden fees'"]),         # a speaker and a colon
    # A colon after anything but a speaker is a label: since the eighth validation (5 Oct 2026)
    # it cues no quote ("Note: 'fees are high' is the theme"; until then, a quote).
    ("Their view: 'banks charge hidden fees' today.", []),
    (f"Fees are 'far too high here' {CITE_A}", ["'far too high here'"]),                   # a citation
    ("Fees are 'far too high here' (Reddit).", ["'far too high here'"]),                    # a source tag
    ("Fees are 'far too high here' for many.", []),                                          # a term
    ("One user wrote 'extremely expensive' today.", []),                                     # two words
])
def test_a_short_single_quoted_passage_is_a_quote_after_a_cue_or_before_a_citation(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


@pytest.mark.parametrize("answer", [
    f'One said "{QUOTE_A}," and more {CITE_A}',
    f'One said "{QUOTE_A}!" {CITE_A}',
    f'One said "{QUOTE_A}." {CITE_A}',
])
def test_a_real_quote_is_the_same_quote_without_its_end_punctuation(answer):
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == (answer, False)


# Checking the changes above against made-up answers with several odd shapes at once found
# more ways for one quote to take another's mark; each test below is one of them.

@pytest.mark.parametrize("answer, loose", [
    ('Fees rose" a 6" phone', ['"']),          # a closing mark and an inch mark: no word in quote marks
    ('Rated "buy" and "Tier 1" by most.', []),  # words in quote marks
    ('for sure“ a 6" phone', ["“"]),            # an opening mark typed to close, nothing open
    ('Rated ”buy” and »Tier 1« by most.', []),
    ('用户说“应用很慢”。', []),                   # in Chinese, a letter against both marks
    ('“DBS”的应用', []),
    # A word in quote marks whatever follows its closing mark, since the eighth validation
    # (5 Oct 2026: '"DBS"and' took its line; until then both marks were left unplaced here) ...
    ('“x”OCBC will cut', []),
    # ... unless a mark that reads as a closing one follows ten or more characters on: then
    # the closing mark opens a quote, and the first is left unplaced.
    (f'“x”{QUOTED_INVENTED}”', ["“"]),
])
def test_two_marks_are_a_short_pair_only_around_a_word(answer, loose):
    assert [answer[i] for i in agent._QUOTE_PATTERN.loose(answer)] == loose


@pytest.mark.parametrize("answer", [
    # The quote's own closing mark taken as a short pair with the inch mark after it.
    f'One said “my rate went up to 5" in one post. Another wrote ”{QUOTED_INVENTED}" a 6" phone',
    f'"unclosed and "{QUOTED_INVENTED}“ a stray " here',
    # Closed with an opening mark typed to close, and an inch mark after it.
    f'"unclosed and ”{QUOTED_INVENTED}“ a 6" phone',
    f'One said "{QUOTED_INVENTED[:26]}\n{QUOTED_INVENTED[27:]}“ a 6" phone',
    # Opened with the mark another quote took, closed after a number or with spaces inside.
    f'One said “my rate went up to 5" in one post. Another wrote ”{QUOTED_INVENTED} by 5" ok',
    f'"unclosed and "{QUOTED_INVENTED} " here',
    f'“my rate went up to 5" in one post. Another wrote ”**{QUOTED_INVENTED}**" ok',
])
@pytest.mark.parametrize("searched", [True, False], ids=["after a search", "no search"])
def test_an_invented_quote_in_several_odd_shapes_at_once_is_removed_or_flagged(answer, searched):
    tracker = _two_quote_tracker() if searched else agent._ToolCallTracker()
    assert tracker.answer_has_unverified_citation(answer)
    out, flagged = agent.enforce_evidence(answer, tracker, "q", "strip")
    assert "next year for sure" not in out or flagged


@pytest.mark.parametrize("answer", [
    f'One said ”{QUOTE_A}" ok',             # a closing mark used to open, a straight one to close
    f'One said »{QUOTE_A}» ok',             # as typed in Sweden or Finland
    f'One said "{QUOTE_A}“ ok',             # an opening mark typed to close
    f'One said «{QUOTE_A}« ok',
    f'One said „{QUOTE_A}„ ok',
])
def test_a_real_quote_in_mixed_marks_is_kept_and_an_invented_one_is_not(answer):
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == (answer, False)
    invented = answer.replace(QUOTE_A, QUOTED_INVENTED)
    out, flagged = agent.enforce_evidence(invented, _two_quote_tracker(), "q", "strip")
    assert "next year for sure" not in out and not flagged


@pytest.mark.parametrize("answer, quotes", [
    # '”O': the mark another quote took as its close may open this one.
    (f'One said “my rate went up to 5" in one post. Another wrote ”{QUOTED_INVENTED}',
     ['“my rate went up to 5" in one post. Another wrote ”', QUOTED_INVENTED]),
    (f'One said “my rate went up to 5" in one post. Another wrote ”{QUOTED_INVENTED}” {CITE_A}',
     ['“my rate went up to 5" in one post. Another wrote ”', QUOTED_INVENTED]),
    # Fewer than ten characters after it, as in a word in quote marks inside a quote: no quote.
    (f'One user asked "{QUOTED_REAL}"', ['"What do you think of "', '" with the 0.5% fees?"']),
])
def test_the_words_after_a_closing_mark_that_reads_as_an_opening_one_are_checked(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


@pytest.mark.parametrize("answer, quotes", [
    ("Users say 'banks charge hidden fees' a lot.", ["'banks charge hidden fees'"]),           # any form of a cue
    ("As one user put it, 'banks charge hidden fees'.", ["'banks charge hidden fees'"]),
    ("Their view: very much 'banks charge hidden fees'.", []),     # a label's colon: no cue since 5 Oct 2026
    ("Another: 'banks charge hidden fees'.", ["'banks charge hidden fees'"]),                 # a speaker's
    ("Note: one two three four 'banks charge hidden fees'.", []),                              # four words back
    ("Fees are 'far too high here' (source: Reddit).", ["'far too high here'"]),
    ("Fees are 'far too high here' [1, 2].", ["'far too high here'"]),
    ("Fees are 'far too high here' (cite_as: DBS).", ["'far too high here'"]),
    ("One user wrote ’banks charge hidden fees’ today.", ["’banks charge hidden fees’"]),        # ’...’ marks
    ("One user wrote ‘banks charge hidden fees‘ today.", ["‘banks charge hidden fees‘"]),
    ("DBS's 'customer first digital approach' is praised.", []),                               # still a term
])
def test_single_quotes_after_any_form_of_a_cue_or_before_any_citation(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes


def test_a_mark_strip_could_place_only_after_removing_a_quote_still_takes_its_line():
    # Each pass reads the marks as the model wrote them before it removes any quote: here
    # removing the invented quote would leave '«„', which reads as a pair. (The last „,
    # right after a closing mark at the end of its line, is a stray since the eighth
    # validation, 5 Oct 2026; the first « still takes the line.)
    answer = f"DBS reads slightly positive.\n«„{QUOTED_INVENTED} «„"
    assert [answer[i] for i in agent._QUOTE_PATTERN.loose(answer)] == ["«"]
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == \
        ("DBS reads slightly positive." + agent.EVIDENCE_UNMATCHED_NOTE, False)


@pytest.mark.parametrize("answer", [
    # A quote in single marks holding one in double marks, as quoted in Britain: checked whole.
    f"One said 'He said \"{QUOTE_A}\" and {QUOTED_INVENTED}' ok",
    f"One said ‘He said “{QUOTE_A}” and {QUOTED_INVENTED}’ ok",
    # A straight quote holding one, closed after punctuation: its closing mark is no stray mark.
    f'One said "He said "{QUOTE_A}" and {QUOTED_INVENTED}!" ok',
    f'One said "He said "{QUOTE_A}" and {QUOTED_INVENTED}."(Reddit)',
])
def test_the_words_after_a_real_quote_inside_another_are_checked(answer):
    out, flagged = agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip")
    assert "next year for sure" not in out or flagged
    assert _two_quote_tracker().answer_has_unverified_citation(answer)


# --- after the eighth validation (5 Oct 2026) --------------------------------------------
# Two marks around fewer than ten characters with no space just inside them are a word in
# quote marks whatever follows ('"DBS"and'), unless a mark that reads as a closing one stands
# ten or more characters on; the words glued to a quote's closing mark are checked only after
# a quote no search returned, or when they hold an inch mark; a mark at the end of its line
# right after a quote's closing mark, or its citation, is a stray; and single quotes are cued
# by a verb of saying or a speaker's colon, not by a noun or a label's colon.

@pytest.mark.parametrize("answer", [
    f'"x"{QUOTED_INVENTED}"',               # a closing mark ten or more characters on
    f'“x”{QUOTED_INVENTED}”',
    f'«x»{QUOTED_INVENTED}»',
    f'"x"{QUOTED_INVENTED} by 5"',          # an inch mark, never a mark the checks can't place
    f'“x”{QUOTED_INVENTED} by 5"',
    f'"x"{QUOTED_INVENTED}\n"',             # on the next line of the paragraph
])
@pytest.mark.parametrize("searched", [True, False], ids=["after a search", "no search"])
def test_an_invented_quote_glued_to_a_word_in_quote_marks_is_removed_or_flagged(answer, searched):
    tracker = _two_quote_tracker() if searched else agent._ToolCallTracker()
    assert tracker.answer_has_unverified_citation(answer)
    out, flagged = agent.enforce_evidence(answer, tracker, "q", "strip")
    assert "next year for sure" not in out or flagged


@pytest.mark.parametrize("answer", [
    '“DBS”and «OCBC» both rose.',
    '"buy"s and "sell"s are common.',
    'Rated "buy"by most, "hold" by some.',
])
def test_a_word_in_quote_marks_with_a_letter_after_it_is_kept(answer):
    assert agent._QUOTE_PATTERN.loose(answer) == []
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == (answer, False)


def test_the_words_glued_to_a_real_quote_are_the_models_own():
    answer = f'One user: “{QUOTE_A}”DBS also scored 0.31.'
    assert agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip") == (answer, False)
    # So in a follow-up with no search, after a quote an earlier turn's search returned.
    assert agent.enforce_evidence(answer, agent._ToolCallTracker(_two_quote_tracker().calls), "q", "strip") == \
        (answer, False)


@pytest.mark.parametrize("answer", [
    f'One user: “{QUOTED_INVENTED} now”{QUOTE_INVENTED_TAIL} today',    # after an invented quote
    f'One user: “very strong”{QUOTED_INVENTED}',                        # after one too short to check
    f'One user: “{QUOTE_A}”{QUOTED_INVENTED} by 5"',                    # holding an inch mark
])
def test_the_words_glued_to_a_closing_mark_are_checked_where_they_may_be_a_quote(answer):
    out, flagged = agent.enforce_evidence(answer, _two_quote_tracker(), "q", "strip")
    assert ("next year for sure" not in out and "cheats everyone" not in out) or flagged


@pytest.mark.parametrize("answer, loose", [
    (f'He said "{QUOTE_A}""', []),                  # right after the closing mark, at the line end
    (f'He said "{QUOTE_A}" {CITE_A}."', []),        # after the quote's citation
    (f'He said "{QUOTE_A}" [2]".', []),
    (f'He said “{QUOTE_A}”» ok', ["»"]),            # words after it
    (f'He said "{QUOTE_A}" and then"', ['"']),      # words between
    (f'He said "{QUOTE_A}"\n"', ['"']),             # not on the quote's line
])
def test_a_stray_mark_right_after_a_quote_or_its_citation_is_placed(answer, loose):
    assert [answer[i] for i in agent._QUOTE_PATTERN.loose(answer)] == loose


@pytest.mark.parametrize("answer, quotes", [
    ("**One user:** 'banks charge hidden fees'", ["'banks charge hidden fees'"]),     # a speaker's colon
    ("One Reddit user: 'banks charge hidden fees'", ["'banks charge hidden fees'"]),
    ("A user posted 'banks charge hidden fees'", ["'banks charge hidden fees'"]),      # a verb of saying
    ("Users call it 'banks charge hidden fees'", ["'banks charge hidden fees'"]),
    ("Users call the app 'buggy and slow' often.", []),                               # a noun's form, a label
    ("Posts say little; posts like 'DBS down again' were common.", []),
    ("Summary: 'fees are high' is the theme.", []),
])
def test_single_quotes_are_cued_by_a_verb_of_saying_or_a_speakers_colon(answer, quotes):
    assert agent._QUOTE_PATTERN.findall(answer) == quotes
