"""
Probes from the eleventh validation of fix/chatbot-answers (after f7a90fb:
citations that vouch for words no search returned are cut; every line ending
read as a line feed; evidence figures vouch only among their words). Each test
asserts what the grounded chatbot claim needs, or that a correct answer is kept
as written, so it fails while the problem is real; a confirmed one carries
xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot import agent
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from tests.quote_marks import in_quote_marks

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}


def _searched(item=ITEM):
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [item]}}])


def _turn(monkeypatch, answer):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "app"})
            return answer

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [ITEM]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    return agent.answer_turn("What do people say about the DBS app?", backend=Backend(), verbose=False)


# --- a scare-quoted term in an earlier sentence cuts a correct citation --------

SCARE = 'DBS markets it as a "super app".'
PARAPHRASE = f"Users complain the app is slow at night {CITE}."
SCARE_ANSWERS = [f"{SCARE} {PARAPHRASE}", f"{SCARE}\n{PARAPHRASE}"]
SCARE_REASON = ("SCARE_QUOTE_CUTS_NEXT_CITATION: a two-word scare quote in an earlier sentence of the "
                "paragraph now cuts the next sentence's correct citation and is flagged in off mode "
                "(kept unchanged and unflagged at 03dc631)")


@pytest.mark.parametrize("answer", SCARE_ANSWERS, ids=["same_line", "next_line"])
def test_a_scare_quote_in_an_earlier_sentence_keeps_the_next_citation(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert CITE in out and not flagged


@pytest.mark.parametrize("answer", SCARE_ANSWERS, ids=["same_line", "next_line"])
def test_off_mode_does_not_flag_a_scare_quote_in_an_earlier_sentence(answer):
    assert not enforce_evidence(answer, _searched(), "q", "off")[1]


def test_answer_turn_keeps_the_citation_after_an_earlier_scare_quote(monkeypatch):
    r = _turn(monkeypatch, SCARE_ANSWERS[0])
    assert CITE in r.model_answer and not r.citation_unverified


def test_a_scare_quote_after_the_citation_keeps_it():
    answer = f'Users complain the app is slow at night {CITE}, despite the "super app" label.'
    assert enforce_evidence(answer, _searched(), "q", "strip") == (answer, False)


# --- off mode and a blockquote of returned text --------------------------------

@pytest.mark.parametrize("answer", [f"Users said:\n> {REAL} {CITE}", f"> {REAL} {CITE}"])
def test_off_mode_does_not_flag_a_returned_blockquote_with_its_citation(answer):
    assert enforce_evidence(answer, _searched(), "q", "strip") == (answer, False)
    assert not enforce_evidence(answer, _searched(), "q", "off")[1]


# --- correct answers kept as written --------------------------------------------

CORRECT = [
    f'Users say "{REAL}" {CITE}.',
    f"Users complain the app is slow at night {CITE}.",
    f"Main complaint {CITE}: the app is slow at night.",
    f'Complaints:\n- the app is slow at night {CITE}\n- "{REAL}" {CITE}',
    f"DBS's app is slow at night, per users {CITE}.",
    f"Users don't like that the app is slow to load {CITE}.",
    f"DBS's app draws fire because users say it is slow, and OCBC's is fine {CITE}.",
    f"O'Brien said the app is slow to load at night {CITE}.",
    f'"{REAL}" {CITE}: a common view.',
    f"## App\nUsers complain the app is slow at night {CITE}.",
    f'Users call it "slow" at night {CITE}.',
    f"{CITE} - the app is slow at night.",
    f"Two points {CITE}:\n- the app is slow at night\n- users want fixes",
]


@pytest.mark.parametrize("answer", CORRECT)
def test_a_correct_answer_is_kept_and_not_flagged(answer):
    assert enforce_evidence(answer, _searched(), "q", "strip") == (answer, False)
    assert not enforce_evidence(answer, _searched(), "q", "off")[1]


# --- invented evidence in many shapes -------------------------------------------

INVENTED_ANSWERS = [
    f'Users say "{INVENTED}" {CITE}.',
    f"Users say '{INVENTED}' {CITE}.",
    f"Users say ‘{INVENTED}’ {CITE}.",
    f"Users say ’{INVENTED}’ {CITE}.",
    f'Users say "{INVENTED} {CITE}.',
    f"He wrote \"they said '{INVENTED}' loudly\" {CITE}.",
    f'- "{INVENTED}" {CITE}\n- "{REAL}" {CITE}',
    f"Users:\n> {INVENTED} {CITE}",
    f"Users:\r\n> {INVENTED}",
    f"Users: > {INVENTED}",
    f"Users:\x85> {INVENTED}",
    f"Users:\x0b> {INVENTED}",
    f"Users:\x1c> {INVENTED}",
    f"Users:\n> > {INVENTED}",
    f"Users:\n1. > {INVENTED}",
    f'"{REAL}" and "{INVENTED}" {CITE}',
    f'"{INVENTED}"really {CITE}',
    f"Users say &quot;{INVENTED}&quot; {CITE}.",
    f'"the app is slow ... {INVENTED}" {CITE}',
    f"Users' view: 'OCBC will cut it's dividend, they'll see' {CITE}.",
    f"Users say ＂{INVENTED}＂ {CITE}.",
    f"Users say «{INVENTED}» {CITE}.",
    f"Users say 「{INVENTED}」 {CITE}.",
    f"Users say „{INVENTED}“ {CITE}.",
    f"Users say ″{INVENTED}″ {CITE}.",
]


@pytest.mark.parametrize("answer", INVENTED_ANSWERS)
def test_invented_evidence_is_not_shown_as_a_quote_or_vouched_for(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert flagged or INVENTED not in out or (not in_quote_marks(out.replace("\r\n", "\n"), INVENTED)
                                              and CITE not in out)
    assert enforce_evidence(answer, _searched(), "q", "off")[1]


def test_answer_turn_strips_an_invented_quote_next_to_a_real_one(monkeypatch):
    r = _turn(monkeypatch, f'Mixed views. "{REAL}" {CITE} and "{INVENTED}" {CITE}')
    assert INVENTED not in r.answer and REAL in r.answer and not r.citation_unverified


# --- figures ---------------------------------------------------------------------

FIG_TOOLS = [{"score": 0.31, "n": 45, "data_runs_to": "2026-09-25"},
             {"query": "q", "results": [{**ITEM, "text": "DBS raised fees by 5% in March 2026, users said"}]}]


@pytest.mark.parametrize("answer, flagged", [
    ("DBS raised fees by 5% in March 2026.", []),
    ("DBS raised fees by 7% in March 2026.", ["7%"]),
    ("The score is 0.31 from 45 posts, data to 2026-09-25.", []),
    ("The score is 0.35 from 45 posts.", ["0.35"]),
    ("DBS raised fees by 5% (users said) and 12% later.", ["12%"]),
    ("As of September 25, 2026 the score is 0.31.", []),
    ("DBS raised fees by 5% in March 2026, users said, then 9% more.", ["9%"]),
])
def test_figures_next_to_returned_figures_and_dates(answer, flagged):
    assert unverified_numbers(answer, FIG_TOOLS, "q") == flagged


def test_a_long_answer_is_enforced_quickly():
    import time
    long = "\n".join(f'- Point {i}: "the app is slow" and users say "{INVENTED} {i}" {CITE}; '
                     f"DBS's users don't like it." for i in range(80))
    t = time.time()
    out, _ = enforce_evidence(long, _searched(), "q", "strip")
    assert time.time() - t < 5 and INVENTED not in out
