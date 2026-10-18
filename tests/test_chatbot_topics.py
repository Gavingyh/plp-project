"""
The model chooses the topic. It is shown each topic's definition, so an app question
can be matched to the topic that covers app outages, and when none fits it is told to
leave the topic out and say so, instead of giving the bank's overall mood as if it
were the answer to the question.
"""

from chatbot import tools
from chatbot.prompts import SYSTEM_PROMPT
from config import aspect_taxonomy
from tests.test_chatbot_reader import _index


def test_the_prompt_lists_every_topic_with_its_definition():
    for key, spec in aspect_taxonomy.load()["aspects"].items():
        if key == "other":
            continue
        assert f"- {key}: {spec['llm_definition']}" in SYSTEM_PROMPT, key


def test_other_is_not_offered_as_a_topic_to_pick():
    assert "- other:" not in SYSTEM_PROMPT


def test_the_prompt_says_what_to_do_when_no_topic_fits():
    text = " ".join(SYSTEM_PROMPT.split())
    assert "leave aspect out" in text and "could not match the question to a topic" in text
    assert "overall" in text


def test_a_search_without_a_topic_tells_the_model_to_say_none_fitted(temp_db, monkeypatch):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    note = tools.chat_search_evidence("DBS app", bank="DBS")["bank_overall_score"]["covers"]
    assert "no topic was chosen" in note.lower() and "no matching topic" in note.lower()


def test_a_search_with_a_topic_does_not(temp_db, monkeypatch):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    note = tools.chat_search_evidence("DBS app", bank="DBS", aspect="dividend_policy")["topic_score"]["covers"]
    assert "no matching topic" not in note.lower()


def test_the_wording_added_to_a_search_has_no_quote_marks(temp_db, monkeypatch):
    # The model copied the search words in quote marks and the quote check stripped them
    # ("there is no specific score for, but ..."), so the search words are not quoted here.
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    r = tools.chat_search_evidence("DBS app", bank="DBS")
    assert '"' not in r["no_evidence"] and '"' not in r["bank_overall_score"]["covers"]
