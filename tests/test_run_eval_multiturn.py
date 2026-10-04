"""Tests for the v2 gold set and the multi-turn runner in chatbot/run_eval.py (no model calls)."""

from types import SimpleNamespace

import yaml

import chatbot.run_eval as re_


def test_v2_extends_v1_with_valid_aspects():
    from chatbot.eval_gold_set import GOLD_SET, GOLD_SET_V2, MULTI_TURN
    with open("config/aspects.yaml") as f:
        keys = set(yaml.safe_load(f)["aspects"])
    assert GOLD_SET_V2[:len(GOLD_SET)] == GOLD_SET and len(GOLD_SET_V2) == 32
    for item in GOLD_SET_V2 + [t for sc in MULTI_TURN for t in sc["turns"]]:
        assert item.get("expected_aspect") in keys | {None}


def test_multi_turn_checks_each_turn_inside_one_conversation(tmp_path, monkeypatch):
    monkeypatch.setattr(re_, "EVAL_DIR", str(tmp_path))
    monkeypatch.setattr(re_, "_describe_model", lambda b: "fake")
    scenario = [{"id": "mt-x", "turns": [
        {"question": "DBS dividends?", "expected_tool": "get_sentiment", "expected_bank": "DBS", "expected_aspect": "dividend_policy"},
        {"question": "And OCBC?", "expected_tool": "get_sentiment", "expected_bank": "OCBC", "expected_aspect": "dividend_policy"},
        {"question": "Should I buy it?", "expected_behavior": "decline_advice"}]}]
    convs = []

    class FakeConversation:
        def __init__(self, backend_name=None):
            self.memory = []
            convs.append(self)

        def ask(self, q):
            self.memory.append(q)
            if q.startswith("Should"):
                return SimpleNamespace(answer="This is not financial advice.", calls=[])
            bank = "DBS" if q.startswith("DBS") else "OCBC"
            # a model that forgot the aspect on the follow-up
            aspect = "dividend_policy" if len(self.memory) == 1 else None
            return SimpleNamespace(answer="ok", calls=[{"name": "get_sentiment", "arguments": {"bank": bank, "aspect": aspect}}])

    out = re_.run_multi_turn(scenarios=scenario, conversation=FakeConversation)
    assert len(convs) == 1 and len(convs[0].memory) == 3              # one conversation for the scenario
    assert out == {"turns": 3, "turns_correct": 2, "scenarios": 1, "scenarios_correct": 0}
    summary = (tmp_path / "chatbot_multiturn_summary.md").read_text()
    assert "wrong aspect" in summary
