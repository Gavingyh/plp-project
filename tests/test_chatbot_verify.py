"""
An answer is checked before it is returned. Asked "and UOB?" after a question
about another bank, the chatbot returned "slightly positive", +0.12, 44.4% and
9.7% with no tool call behind them, under three warnings. Now a draft with a
figure, a reading or a quote no tool returned is written again (the model is
told what was wrong), then trimmed of the sentences that state it, then
withheld; the reader sees no warning and no flag.
"""

import pytest

from chatbot import agent, tools
from chatbot.agent import REWRITE_NOTE, WITHHELD_REPLY, Conversation, answer_turn

SCORE = {"bank": "DBS", "aspect": None, "window": "all_time", "score": 0.0291, "n": 13452,
         "reading": "neutral", "insufficient_data": False}


@pytest.fixture(autouse=True)
def _tools_and_intent(monkeypatch):
    monkeypatch.delenv("CHATBOT_VERIFY_BEFORE_REPLY", raising=False)
    monkeypatch.delenv("CHATBOT_VERIFY_RETRIES", raising=False)
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    monkeypatch.setitem(tools.TOOL_FUNCTIONS, "get_sentiment", lambda **kw: {**SCORE, "bank": kw["bank"]})
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)


class Scripted:
    """Answers from a list, one per call; looks a score up first when `lookup` says so."""
    name, model = "fake", "fake-model"

    def __init__(self, answers, lookup=(True, True, True)):
        self.answers, self.lookup, self.systems = list(answers), list(lookup), []

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        i = len(self.systems)
        self.systems.append(system)
        if self.lookup[min(i, len(self.lookup) - 1)]:
            tool_executor("get_sentiment", {"bank": "DBS"})
        return self.answers[min(i, len(self.answers) - 1)]


def _turn(*answers, **kw):
    backend = Scripted(answers, **kw)
    return answer_turn("How is DBS?", backend=backend, verbose=False), backend


def test_a_clean_answer_is_returned_after_one_try():
    r, backend = _turn("DBS reads neutral, 0.029 on 13,452 sentences.")
    assert len(backend.systems) == 1 and r.answer.startswith("DBS reads neutral")
    assert not r.retried and r.repaired is None and r.verified


def test_a_wrong_figure_is_written_again_and_the_reader_sees_no_warning():
    r, backend = _turn("DBS scored 0.41 on 13,452 sentences.", "DBS scored 0.029 on 13,452 sentences.")
    assert r.answer.startswith("DBS scored 0.029") and "CHECK" not in r.answer and "⚠" not in r.answer
    assert r.retried and r.repaired == "rewritten"
    assert r.unverified_numbers == ["0.41"]              # the first draft's flags stay on the record
    assert r.shown_flags() == {"citation_unverified": False, "unverified_numbers": [], "unverified_readings": []}


def test_the_model_is_told_what_was_wrong_on_the_second_try():
    _, backend = _turn("DBS scored 0.41 on 13,452 sentences.", "DBS scored 0.029 on 13,452 sentences.")
    assert REWRITE_NOTE.split("{problems}")[0] in backend.systems[1]
    assert "0.41" in backend.systems[1] and "0.41" not in backend.systems[0]


def test_a_wrong_reading_is_written_again():
    r, _ = _turn("People are clearly positive on DBS.", "DBS reads neutral.")
    assert r.answer == "DBS reads neutral." and r.unverified_readings == ["clearly positive"]


def test_an_answer_with_no_lookup_is_sent_back_to_look_it_up():
    # The follow-up failure: figures and a reading from nowhere, no tool called.
    r, backend = _turn("DBS reads slightly positive, +0.12, 44.4% positive.", "DBS reads neutral, 0.029.",
                       lookup=(False, True))
    assert r.answer == "DBS reads neutral, 0.029." and r.repaired == "rewritten"
    assert "Call the tools" in backend.systems[1]


def test_a_second_wrong_answer_is_trimmed_to_what_can_be_confirmed():
    r, backend = _turn("DBS scored 0.41 on 13,452 sentences. Dividends are the topic people raise most.")
    assert len(backend.systems) == 2
    assert r.answer == "Dividends are the topic people raise most." and r.repaired == "trimmed"
    assert "0.41" not in r.answer and r.verified


def test_an_answer_with_nothing_confirmed_is_withheld_without_a_warning():
    r, _ = _turn("DBS scored 0.41.")
    assert r.answer == WITHHELD_REPLY and r.repaired == "withheld" and "⚠" not in r.answer
    assert r.shown_flags()["unverified_numbers"] == []


def test_no_second_try_when_retries_are_zero(monkeypatch):
    monkeypatch.setenv("CHATBOT_VERIFY_RETRIES", "0")
    r, backend = _turn("DBS scored 0.41 on 13,452 sentences. Dividends come up most.")
    assert len(backend.systems) == 1 and r.answer == "Dividends come up most." and not r.retried


def test_invented_quotes_never_stand_even_with_enforcement_off(monkeypatch):
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "off")
    r, _ = _turn('DBS reads neutral. One post said "the bank cheats everyone every single day" [DBS, 2026-01-01, '
                 'sentence_id 111111111111111111111111].')
    assert "cheats everyone" not in r.answer and r.verified


def test_verifying_off_keeps_the_old_flag_and_warning(monkeypatch):
    monkeypatch.setenv("CHATBOT_VERIFY_BEFORE_REPLY", "false")
    r, backend = _turn("DBS scored 0.41 on 13,452 sentences.")
    assert len(backend.systems) == 1 and "NUMBER CHECK" in r.answer and not r.verified
    assert r.shown_flags()["unverified_numbers"] == ["0.41"]


def test_the_conversation_keeps_the_verified_answer_for_the_next_turn(monkeypatch):
    backend = Scripted(["DBS scored 0.41.", "DBS scored 0.41.", "OCBC reads neutral."])
    monkeypatch.setattr(agent, "get_backend", lambda name=None: backend)
    conv = Conversation()
    first = conv.ask("How is DBS?")
    assert first.answer == WITHHELD_REPLY
    conv.ask("and OCBC?")
    assert "0.41" not in str(backend.systems[-1])


def test_the_api_returns_no_flags_for_a_verified_answer(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app

    backend = Scripted(["DBS scored 0.41.", "DBS scored 0.029 on 13,452 sentences."])
    monkeypatch.setattr(agent, "get_backend", lambda name=None: backend)
    body = TestClient(app).post("/chat", json={"message": "How is DBS?"}).json()
    assert body["answer"].startswith("DBS scored 0.029") and "⚠" not in body["answer"]
    assert body["unverified_numbers"] == [] and body["unverified_readings"] == [] and not body["citation_unverified"]
