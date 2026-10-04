"""
Validation of the grounded chatbot claim against the reader-facing changes of
4 Oct 2026 (numbered sources, the quote exemption for tool wording, fields
hidden from the model, year-less dates in the number check). Each test runs
the real tracker, checks and answer_turn with a fake model and fake tools; no
database, no Ollama.
"""

import pytest

import chatbot.agent as agent
from chatbot.agent import _ToolCallTracker, answer_turn, number_citations
from chatbot.guards import unverified_numbers

SID_REAL = "a" * 24
SID_FAKE = "f" * 24
ITEM = {"sentence_id": SID_REAL, "bank": "DBS", "source": "google_news", "source_name": "news",
        "date": "2026-09-02", "text": "dbs raised its quarterly dividend to 60 cents a share",
        "url": "https://news.example/dbs", "cite_as": f"[DBS, 2026-09-02, sentence_id {SID_REAL}]"}


class _Model:
    """A model that makes the given tool calls, then returns a fixed answer."""
    name, model = "fake", "fake"

    def __init__(self, calls, answer):
        self.calls, self.answer = calls, answer

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        for name, args in self.calls:
            tool_executor(name, args)
        return self.answer


@pytest.fixture
def strip(monkeypatch):
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "search_evidence",
                        lambda **kw: {"query": kw.get("query"), "results": [dict(ITEM)], "n_found": 1})


# --- numbered sources: only what a search returned ------------------------------------

def test_sources_list_only_searched_sentences_and_a_fake_citation_stays_flagged(strip):
    answer = (f'DBS raised it: "dbs raised its quarterly dividend to 60 cents a share" '
              f'[DBS, 2026-09-02, sentence_id {SID_REAL}]. Also [DBS, 2026-01-01, sentence_id {SID_FAKE}].')
    r = answer_turn("dividends?", backend=_Model([("search_evidence", {"query": "dividend"})], answer),
                    verbose=False)
    sources = r.answer.split("Sources:\n", 1)[1].split("\n\n")[0].splitlines()
    assert sources == ["- [1] news, DBS, 2 Sep 2026: https://news.example/dbs"]
    assert SID_FAKE not in r.answer.split("Sources:")[1]          # never listed as a source
    assert r.citation_unverified or SID_FAKE not in r.answer     # flagged, or stripped


def test_numbering_a_citation_does_not_vouch_for_an_invented_quote(strip):
    # A real citation pinned to an invented quote: strip removes the quote and its mark.
    answer = f'One reader said "dbs will cut its dividend next year" [DBS, 2026-09-02, sentence_id {SID_REAL}].'
    r = answer_turn("dividends?", backend=_Model([("search_evidence", {"query": "dividend"})], answer),
                    verbose=False)
    assert "will cut its dividend" not in r.answer


# --- fields hidden from the model -----------------------------------------------------

def test_hidden_ids_still_verify_a_citation_and_the_model_never_sees_them(monkeypatch):
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "search_evidence",
                        lambda **kw: {"results": [dict(ITEM)], "n_found": 1})
    t = _ToolCallTracker()
    sent = t.execute("search_evidence", {"query": "q"})
    assert SID_REAL not in sent.replace(ITEM["cite_as"], "")      # only inside the ready-made citation
    assert t.calls[0]["result"]["results"][0]["sentence_id"] == SID_REAL
    assert not t.answer_has_unverified_citation(f"See {ITEM['cite_as']}.")


# --- the tool-wording exemption -------------------------------------------------------

def test_a_quote_echoing_the_models_own_argument_is_still_unverified(strip):
    # The model passes invented "evidence" as the aspect; get_sentiment echoes it back as topic_name,
    # and the quote exemption then treats it as the tool's own wording.
    invented = "the app crashed three times while i was paying rent"
    answer = f'Customers are unhappy: one wrote "{invented}".'
    r = answer_turn("DBS app?", backend=_Model([("get_sentiment", {"bank": "DBS", "aspect": invented})], answer),
                    verbose=False)
    assert r.citation_unverified or invented not in r.answer


# --- year-less dates in the number check ----------------------------------------------

@pytest.mark.parametrize("answer, figure", [
    ("DBS scored 0.45 may be read as mild optimism.", "0.45"),
    ("In May 45 sentences were negative.", "45"),
    ("In September 48 sentences were positive.", "48"),
])
def test_an_invented_figure_next_to_a_month_word_is_flagged(answer, figure):
    assert figure in unverified_numbers(answer, [{"bank": "DBS", "score": 0.12, "n": 300}], "How is DBS?")


def test_a_real_year_less_date_is_still_not_a_figure():
    # A date without its year counts only when a tool returned it (4 Oct 2026), as data_runs_to does.
    tools = [{"n": 1, "data_runs_to": "2026-09-25"}, {"data_runs_to": "2026-09-24"}]
    assert unverified_numbers("The data runs to September 25th; UOB's to 24 Sep.", tools) == []
