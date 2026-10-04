"""Tests for chatbot/intent.py: the prompt, parsing, failing open, and the replies.
Whether the model picks the right intent is measured by chatbot/eval_intent.py."""

import json

import pytest
import requests

import chatbot.intent as intent
from chatbot.eval_gold_set import GOLD_SET_V2, MULTI_TURN, MULTI_TURN_SCOPE, SCOPE_SET


def _answers(*replies):
    seen = []

    def chat(model, messages, names):
        seen.append(messages)
        r = replies[min(len(seen) - 1, len(replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    return chat, seen


def test_the_prompt_lists_every_intent_and_ends_with_the_question():
    msgs = intent.build_messages("How is UOB?", "bank: DBS")
    assert all(f"- {name}:" in msgs[0]["content"] for name in intent.intent_names())
    assert msgs[-1] == {"role": "user", "content": "Conversation so far: bank: DBS\nQuestion: How is UOB?"}


def test_no_example_is_an_evaluation_question():
    # the few-shot examples would otherwise inflate the measured accuracy
    examples = {ex["question"].strip().lower() for ex in intent.load_config()["examples"]}
    evaluated = {i["question"] for i in GOLD_SET_V2 + SCOPE_SET}
    evaluated |= {t["question"] for sc in MULTI_TURN + MULTI_TURN_SCOPE for t in sc["turns"]}
    assert not examples & {q.strip().lower() for q in evaluated}


def test_every_example_and_reply_names_a_real_intent():
    cfg = intent.load_config()
    names = set(intent.intent_names())
    assert {ex["intent"] for ex in cfg["examples"]} <= names
    assert set(cfg["replies"]) - {"what_i_do", "context"} == names - {"in_scope"}


@pytest.mark.parametrize("name", [n for n in intent.intent_names() if n != "in_scope"])
def test_every_reply_fills_in(name):
    for state in (None, {"banks": ["OCBC"], "aspect": "asset_quality"}):
        reply = intent.reply_for(name, "Some question about UOB", state)
        assert reply and "{" not in reply and "}" not in reply


def test_a_valid_answer_is_returned():
    chat, _ = _answers('{"intent": "off_topic"}')
    assert intent.classify_intent("How is the weather?", chat=chat) == "off_topic"


def test_an_answer_outside_the_list_is_retried_once_then_lets_the_question_through():
    chat, seen = _answers('{"intent": "weather"}', '{"intent": "nonsense"}')
    assert intent.classify_intent("hm", chat=chat) is None and len(seen) == 2
    chat, seen = _answers('{"intent": "weather"}', '{"intent": "greeting"}')
    assert intent.classify_intent("hi", chat=chat) == "greeting"


@pytest.mark.parametrize("error", [requests.ConnectionError("Ollama isn't running"), requests.Timeout("slow")])
def test_an_unavailable_classifier_lets_the_question_through(error):
    chat, _ = _answers(error)
    assert intent.classify_intent("How is DBS?", chat=chat) is None


def test_in_scope_and_no_intent_get_no_fixed_reply():
    assert intent.reply_for("in_scope", "How is DBS?") is None
    assert intent.reply_for(None, "How is DBS?") is None


def test_replies_carry_the_conversation_and_the_bank():
    assert "We were looking at DBS dividend policy" in intent.reply_for(
        "off_topic", "How is the weather?", {"banks": ["DBS"], "aspect": "dividend_policy"})
    service = intent.reply_for("service", "What's my UOB account balance?")
    assert "For UOB" in service and "don't share account numbers" in service
    assert "For your bank" in intent.reply_for("service", "How do I reset my password?")


def test_a_question_goes_to_the_model_when_the_classifier_is_down(monkeypatch):
    import chatbot.agent as agent
    monkeypatch.setattr("chatbot.intent.ollama_chat", lambda *a: (_ for _ in ()).throw(requests.ConnectionError()))

    class Backend:
        name, model = "fake", "fake"

        def ask(self, *a, **k):
            return "DBS sentiment is steady."
    r = agent.answer_turn("Should I buy DBS?", backend=Backend(), verbose=False)
    assert r.guard is None and r.intent is None and r.answer.startswith("DBS sentiment")


def test_the_evaluation_labels_every_question_and_carries_the_conversation():
    from chatbot.eval_intent import labelled_questions
    rows = {r["id"]: r for r in labelled_questions()}
    assert rows["advice-1"]["intent"] == "advice" and rows["oos-4"]["intent"] == "other_bank"
    assert rows["oos-3"]["intent"] == "off_topic" and rows["lookup-1"]["intent"] == "in_scope"
    assert rows["mts-1.2"]["intent"] == "off_topic"
    assert rows["mts-1.3"]["state"] == {"banks": ["DBS"], "aspect": "dividend_policy"}   # carried past the weather
    assert rows["mt-4.2"]["intent"] == "advice" and rows["mt-4.2"]["previous"] == "What do analysts think of OCBC?"


def test_the_evaluation_summary_counts_blocks_and_misses():
    from chatbot.eval_intent import evaluate, summarize
    rows = evaluate("fake", chat=lambda model, messages, names: '{"intent": "in_scope"}')
    text = summarize(rows, "fake")
    assert "Real questions wrongly blocked: 0" in text
    assert f"Let through to the chatbot model: {sum(r['intent'] != 'in_scope' for r in rows)}" in text
