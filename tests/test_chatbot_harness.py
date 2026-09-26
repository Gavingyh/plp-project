"""
Tests for the harness around the chatbot model (docs/DESIGN.md decision 19):
input guards, output checks, conversation memory, evidence packaging and
decoding temperature. No model or network calls: backends are fakes.

The advice-guard phrasings here were written independently of the gold set
in chatbot/eval_gold_set.py, so that the gold-set run remains a check of the
guard rather than a restatement of it.
"""

import json

import pytest

import chatbot.agent as agent
import chatbot.tools as tools
from chatbot.agent import Conversation, answer_turn
from chatbot.guards import (advice_reply, is_advice_seeking, scope_reply, unverified_numbers,
                            unverified_sentence_ids)


# --- input guard: advice and prediction -------------------------------------

@pytest.mark.parametrize("q", [
    "Should I buy DBS now?",
    "should we sell our OCBC shares before results",
    "Is it a good time to buy UOB?",
    "Buy or sell UOB?",
    "Is OCBC worth buying at this price?",
    "Which bank should I invest in?",
    "Which of the three is the best buy?",
    "Will DBS share price go up next month?",
    "Can you predict where the UOB stock price will be in December?",
    "What should I do with my DBS shares?",
    "Would you recommend holding OCBC stock?",
    "Is DBS a buy?",
])
def test_advice_and_prediction_questions_are_caught(q):
    assert is_advice_seeking(q)


@pytest.mark.parametrize("q", [
    "How has sentiment on DBS dividends changed?",
    "Compare OCBC and UOB on asset quality",
    "What are people saying about DBS's share buyback?",
    "Why did sentiment on UOB fall last month?",
    "Should I be worried about DBS's asset quality?",
    "What do analysts recommend for DBS?",
    "Show me quotes about OCBC's net interest margin",
])
def test_ordinary_questions_are_not_caught(q):
    assert not is_advice_seeking(q)


def test_advice_reply_names_the_bank_and_says_not_advice():
    reply = advice_reply("Should I sell UOB?")
    assert "UOB" in reply and "financial advice" in reply


def test_advice_is_answered_without_calling_the_model(monkeypatch):
    def no_backend(*a, **k):
        raise AssertionError("the model must not be called for an advice question")
    monkeypatch.setattr(agent, "get_backend", no_backend)
    r = answer_turn("Should I buy DBS?", verbose=False)
    assert r.guard == "advice" and r.calls == []


# --- input guard: scope --------------------------------------------------------

def test_question_only_about_another_bank_gets_scope_reply():
    reply = scope_reply("What's the sentiment on Maybank?")
    assert reply and "Maybank" in reply and "DBS, OCBC and UOB" in reply


def test_question_naming_a_covered_bank_is_left_to_the_model():
    assert scope_reply("How does DBS compare with HSBC?") is None
    assert scope_reply("How is sentiment on dividends?") is None


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
    path = tmp_path / "trace.jsonl"
    conv = Conversation(trace_path=str(path))
    conv.ask("Should I buy DBS?")  # answered by the guard, no model needed
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


def test_off_topic_question_gets_scope_reply_without_the_model(monkeypatch):
    monkeypatch.setattr(agent, "get_backend", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    r = answer_turn("What's the weather like in Singapore today?", verbose=False)
    assert r.guard == "scope" and "outside what I can help with" in r.answer


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


def test_advice_reply_uses_the_bank_from_the_conversation():
    assert "OCBC" in advice_reply("Should I buy it?", context_banks=["OCBC"])


def test_names_with_numbers_are_not_figures():
    assert unverified_numbers("Unlike the COVID-19 period, 3Q24 was calm.", [{"n": 5}]) == []
