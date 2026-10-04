"""Tests for chatbot/chat.py, the terminal chat for testing the bot (no model calls)."""

from types import SimpleNamespace

import chatbot.chat as chat


def _turn(**kw):
    base = dict(answer="DBS sentiment is +0.12.", guard=None, citation_unverified=False,
                unverified_numbers=[], calls=[{"name": "get_sentiment", "arguments": {"bank": "DBS"}, "result": {}}])
    return SimpleNamespace(**{**base, **kw})


def test_a_clean_answer_has_no_flags():
    assert chat.format_turn(_turn()) == "DBS sentiment is +0.12."


def test_flags_are_shown_like_the_api_returns_them():
    out = chat.format_turn(_turn(guard="advice", citation_unverified=True, unverified_numbers=[0.42]))
    assert "advice guard" in out and "don't trust it" in out and "0.42" in out


def test_tool_calls_are_listed():
    assert 'get_sentiment({"bank": "DBS"})' in chat.format_calls(_turn())
    assert "no tool calls" in chat.format_calls(None)


def test_the_loop_asks_resets_and_quits(monkeypatch, capsys):
    asked = []

    class FakeConversation:
        def __init__(self, backend_name=None, trace_path=None):
            pass

        def ask(self, q):
            asked.append(q)
            return _turn()

    inputs = iter(["How is DBS?", "/tools", "/reset", "", "/quit"])
    monkeypatch.setattr(chat, "Conversation", FakeConversation)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr("sys.argv", ["chat"])
    chat.main()
    out = capsys.readouterr().out
    assert asked == ["How is DBS?"]
    assert "bot> DBS sentiment is +0.12." in out and "get_sentiment" in out and "conversation forgotten" in out
