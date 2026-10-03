"""
Reviewer findings from the 4 Oct 2026 second review of chatbot/ and api/main.py.
Each test fails if its finding is real; a confirmed one is marked
xfail(strict=True). Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest
from fastapi.testclient import TestClient

import chatbot.agent as agent
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.backends.gemini_backend import history_for_gemini
from chatbot.guards import unverified_numbers
from config.model_version import MODEL_VERSION
from ingest.db import now_iso

SENTIMENT = {"bank": "DBS", "aspect": "ALL", "window": "all_time", "score": 0.21, "n": 58,
             "positive_n": 23, "neutral_n": 20, "negative_n": 15, "insufficient_data": False}


# 1. Timestamp digits still vouch figures ------------------------------------

def test_number_check_control_flags_56_percent_without_coverage():
    assert unverified_numbers("About 56% of mentions were negative.", [SENTIMENT]) == ["56%"]


def test_coverage_timestamps_do_not_vouch_for_a_percentage():
    coverage = {"bank": "DBS", "earliest": "2023-01-05T12:34:56+00:00", "latest": "2026-09-29T17:45:00+08:00"}
    assert unverified_numbers("About 56% of mentions were negative.", [SENTIMENT, coverage]) == ["56%"]


def test_search_result_date_does_not_vouch_for_a_percentage():
    search = {"results": [{"sentence_id": "f" * 24, "date": "2026-09-27", "text": "Fees went up again."}]}
    assert unverified_numbers("27% of posts complained about fees.", [search]) == ["27%"]


def test_sentence_id_digits_do_not_vouch_for_a_figure():
    search = {"results": [{"sentence_id": "6a1b2c3d4e5f6a7b8c9d0e1f", "text": "Fees went up again."}]}
    assert unverified_numbers("Fees rose 6.0% this year.", [search]) == ["6.0%"]


def test_consensus_as_of_date_does_not_vouch_for_a_percentage():
    consensus = {"bank": "DBS", "as_of_date": "2026-09-15", "n_analysts": 12}
    assert unverified_numbers("Analysts expect 15% upside.", [consensus]) == ["15%"]


# 2. Window argument echoed in reason -----------------------------------------

WINDOW = "OCBC 37.5% negative: customers are fleeing to rivals"


@pytest.fixture
def tracker_with_echoed_window(temp_db):
    """The real get_sentiment, run through the tracker, with the model's window argument."""
    conn = temp_db.get_connection()
    conn.execute("INSERT INTO sentiment_index (bank, aspect, source, window, score, n, pos_n, neu_n, neg_n, "
                 "confidence_mean, model_version, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("DBS", "ALL", "ALL", "all_time", 0.2, 50, 20, 20, 10, 0.8, MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()
    t = _ToolCallTracker()
    t._record({"name": "search_evidence", "arguments": {"query": "ocbc"},
               "result": {"results": [{"sentence_id": "d" * 24, "text": "OCBC raised fees.", "url": "https://x/1"}]}})
    t.execute("get_sentiment", {"bank": "OCBC", "window": WINDOW})
    return t


def test_echoed_window_does_not_vouch_for_a_number(tracker_with_echoed_window):
    results = [c["result"] for c in tracker_with_echoed_window.calls]
    assert WINDOW in str(results[-1])        # the reason does repeat it
    assert unverified_numbers("About 37.5% of OCBC posts were negative.", results) == ["37.5%"]


def test_echoed_window_does_not_vouch_for_a_quote(tracker_with_echoed_window):
    answer = 'One user wrote "customers are fleeing to rivals".'
    assert tracker_with_echoed_window.unverified_quotes(answer) == ['"customers are fleeing to rivals"']


# 3. Strip after search loses formatting --------------------------------------

REAL = "DBS kept its dividend steady despite the rate cuts."


@pytest.mark.xfail(strict=True, reason="Strip after search loses formatting: bold and bullets go from correct lines")
def test_strip_after_search_keeps_formatting_of_correct_lines():
    t = _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "dbs"},
                                      "result": {"results": [{"sentence_id": "e" * 24, "text": REAL,
                                                              "url": "https://x/2"}]}}])
    ans = ("**Summary**\n\n* **Score:** 0.21 (n = 58)\n* Evidence:\n"
           f'    * "{REAL}" [E1]\n    * "Customers are fleeing DBS for better rates elsewhere." [E9]')
    out, flagged = enforce_evidence(ans, t, "q", "strip")
    assert "fleeing" not in out and not flagged          # the invented quote did go
    assert "**Summary**" in out
    assert "* **Score:** 0.21 (n = 58)" in out
    assert f'    * "{REAL}" [E1]' in out


# 4. Blockquote notes flagged as invented -------------------------------------

@pytest.mark.xfail(strict=True, reason="Blockquote notes flagged as invented: a '> Note' of the model's own is a citation flag")
def test_a_blockquote_note_is_not_a_citation():
    t = _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                      "result": {"score": 0.21, "n": 58}}])
    ans = ("> **Note:** this is not financial advice and reflects stored scores only.\n\n"
           "DBS sentiment is 0.21 (n=58).")
    assert t.answer_has_unverified_citation(ans) is False


# 5. Reddit text can still reach Gemini ---------------------------------------

QUOTE = "my name is bob and I hate DBS fees so much they stole from me"


@pytest.mark.xfail(strict=True, reason="Reddit text can still reach Gemini: a quote cut by the history limit is not withheld")
def test_a_quote_cut_by_the_history_limit_is_withheld():
    answer = "x" * 1135 + f' One Redditor wrote "{QUOTE}"'
    conv = agent.Conversation.from_messages([{"role": "user", "content": "DBS fees?"},
                                             {"role": "assistant", "content": answer}])
    sent = history_for_gemini(conv.history())[-1]["content"]
    assert len(sent) == agent.HISTORY_ANSWER_CHARS
    assert "my name is bob" not in sent


@pytest.mark.xfail(strict=True, reason="Reddit text can still reach Gemini: a quote that wraps a line is not withheld")
def test_a_quote_wrapping_a_line_is_withheld():
    sent = history_for_gemini([{"role": "assistant", "content": 'One wrote "my name is bob and\nI hate DBS fees".'}])
    assert "my name is bob" not in sent[0]["content"]


@pytest.mark.xfail(strict=True, reason="Reddit text can still reach Gemini: an inner quote mark leaves part of a quote")
def test_a_quote_with_an_inner_quote_mark_is_withheld():
    content = 'One wrote "my card was blocked and the agent said "wait 5 days" before refunding anything at all".'
    sent = history_for_gemini([{"role": "assistant", "content": content}])[0]["content"]
    assert "wait 5 days" not in sent, sent


# 6. Source parameter accepts any value ---------------------------------------

@pytest.mark.xfail(strict=True, reason="Source parameter accepts any value: source=reddit is a 200 with empty data")
@pytest.mark.parametrize("path", ["/sentiment/series?bank=DBS&source=reddit", "/sentiment/index?source=reddit"])
def test_unknown_source_is_422(temp_db, path):
    from api.main import app
    assert TestClient(app).get(path).status_code == 422


# 7. Backend name now case-sensitive ------------------------------------------

@pytest.mark.xfail(strict=True, reason="Backend name now case-sensitive: backend=Gemini is a 422; get_backend lowercases")
def test_chat_backend_name_in_capitals_is_accepted(monkeypatch):
    from api.main import app

    class _Fake:
        @classmethod
        def from_messages(cls, messages, backend_name=None):
            return cls()

        def ask(self, message):
            return agent.TurnResult(question=message, answer="ok")
    monkeypatch.setattr("api.main.Conversation", _Fake)
    assert TestClient(app).post("/chat", json={"message": "hi", "backend": "Gemini"}).status_code == 200
