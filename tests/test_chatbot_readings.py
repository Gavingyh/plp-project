"""
A score described in words the tool did not give it, and a score with no
period beside it. Asked "what do people say about UOB's wealth business in the
last week", the chatbot called the topic "neutral" and "slightly positive"
beside a topic score of 0.4004, which the tools read as "clearly positive",
and that score covered all the data, not the last week.
"""

from chatbot import tools
from chatbot.agent import _ToolCallTracker, answer_turn
from chatbot.guards import unverified_readings
from tests.test_chatbot_reader import _index

CLEARLY = {"topic_score": {"topic_name": "Wealth", "window": "all_time", "reading": "clearly positive",
                           "score": 0.4004, "positive_pct": 50.0}}


# --- the check on the words ----------------------------------------------------------

def test_a_reading_the_tools_did_not_give_is_flagged():
    answer = ("People are neutral on UOB's wealth business, with a topic score of 0.4004 that "
              "shows a slightly positive view.")
    assert unverified_readings(answer, [CLEARLY]) == ["neutral", "slightly positive"]


def test_the_reading_the_tools_gave_passes_whatever_the_case():
    assert unverified_readings("The mood is Clearly Positive (+0.40).", [CLEARLY]) == []


def test_no_reading_returned_flags_any_reading_in_the_answer():
    assert unverified_readings("Sentiment is neutral.", [{"bank": "UOB"}]) == ["neutral"]


def test_neutral_as_a_share_of_sentences_is_not_a_reading():
    answer = ("50% positive, 30% neutral and 20% negative. The neutral share is 30%, "
              "and 12 neutral sentences. Neutral (30%) is the largest group.")
    assert unverified_readings(answer, [CLEARLY]) == []


def test_a_reading_inside_quote_marks_is_the_evidence_not_the_answer():
    answer = 'One post says "the outlook is clearly negative for wealth" [1], yet the mood is clearly positive.'
    assert unverified_readings(answer, [CLEARLY]) == []


def test_a_reading_denied_is_not_flagged():
    assert unverified_readings("The mood is clearly positive, not neutral.", [CLEARLY]) == []


def test_readings_are_found_in_nested_results():
    nested = [{"banks": {"UOB": {"reading": "neutral"}, "DBS": {"reading": "slightly negative"}}}]
    assert unverified_readings("UOB is neutral and DBS slightly negative.", nested) == []


# --- the turn --------------------------------------------------------------------------

class _Backend:
    name, model = "scripted", "scripted"

    def __init__(self, answer):
        self.answer = answer

    def ask(self, question, system, schemas, execute, verbose=True, history=None):
        execute("search_evidence", {"query": "wealth", "bank": "UOB", "aspect": "dividend_policy"})
        return self.answer


def test_a_turn_flags_the_wrong_reading_and_says_what_the_tools_gave(temp_db, monkeypatch):
    monkeypatch.setenv("CHATBOT_VERIFY_BEFORE_REPLY", "false")      # the warning is the unverified mode's
    _index(temp_db, [("UOB", "dividend_policy", "2026-08", 8, 1, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    given = tools.chat_search_evidence("wealth", bank="UOB", aspect="dividend_policy")["topic_score"]["reading"]
    turn = answer_turn("how do people feel about UOB dividends", backend=_Backend("The mood is neutral."),
                       verbose=False)
    assert turn.unverified_readings == ["neutral"]
    assert "READING CHECK" in turn.answer and given in turn.answer
    ok = answer_turn("how do people feel about UOB dividends", backend=_Backend(f"The mood is {given}."),
                     verbose=False)
    assert ok.unverified_readings == [] and "READING CHECK" not in ok.answer


# --- the period beside the score -------------------------------------------------------

def test_the_evidence_score_names_its_window(temp_db, monkeypatch):
    _index(temp_db, [("UOB", "dividend_policy", "2026-08", 8, 1, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    r = tools.chat_search_evidence("wealth", bank="UOB", aspect="dividend_policy")
    assert r["topic_score"]["window"] == "all_time" and "evidence_from" not in r


def test_a_week_asked_for_limits_the_quotes_and_scores_that_week(temp_db, monkeypatch):
    _index(temp_db, [("UOB", "dividend_policy", "2026-08", 8, 1, 1)])
    seen = {}
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: seen.update(kw) or [])
    r = tools.chat_search_evidence("wealth", bank="UOB", aspect="dividend_policy", window="7d")
    newest = tools.data_as_of()
    assert r["topic_score"]["window"] == "7d"
    assert seen["date_from"] == r["evidence_from"] and r["evidence_from"] < newest
    assert (tools.date.fromisoformat(newest) - tools.date.fromisoformat(r["evidence_from"])).days == 7
    r30 = tools.chat_search_evidence("wealth", bank="UOB", window="30d")
    assert (tools.date.fromisoformat(newest) - tools.date.fromisoformat(r30["evidence_from"])).days == 30


def test_the_model_can_ask_for_a_window():
    schema = next(t for t in tools.TOOL_SCHEMAS if t["name"] == "search_evidence")
    assert schema["input_schema"]["properties"]["window"]["enum"] == ["7d", "30d", "all_time"]
