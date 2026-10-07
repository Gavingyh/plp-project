"""
Tests for the free-tier request pacing (chatbot/ratelimit.py) and how the hosted
backends use it. All on a fake clock: nothing sleeps and nothing calls a provider.
"""

import json

import pytest

from chatbot import ratelimit
from chatbot.ratelimit import DAY_SECONDS, DailyBudgetExhausted, Pacer, parse_duration, provider_for


class Clock:
    """A clock whose sleep just moves it forward, so waits are measurable and instant."""
    def __init__(self):
        self.now, self.slept = 1_000_000.0, 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept += seconds
        self.now += seconds


def pacer(clock, tmp_path=None, **limits):
    path = str(tmp_path / "state.json") if tmp_path else None
    return Pacer("p", state_path=path, clock=clock.time, sleep=clock.sleep, **limits)


@pytest.mark.parametrize("text, seconds", [("7.66s", 7.66), ("2m59.56s", 179.56), ("120ms", 0.12),
                                           ("1h2m", 3720), ("30", 30.0), (None, None), ("soon", None)])
def test_parse_duration(text, seconds):
    got = parse_duration(text)
    assert got == pytest.approx(seconds) if seconds is not None else got is None


def test_provider_for_names_the_host_behind_an_openai_compatible_url():
    assert provider_for("openai", "https://api.groq.com/openai/v1") == "groq"
    assert provider_for("openai", "https://openrouter.ai/api/v1") == "openrouter"
    assert provider_for("openai", "https://api.openai.com/v1") == "openai"
    assert provider_for("gemini") == "gemini"


def test_requests_are_spaced_to_the_per_minute_budget():
    clock = Clock()
    p = pacer(clock, rpm=6)                      # one every 10 seconds
    for _ in range(4):
        p.before_request()
    assert clock.slept == pytest.approx(30.0)    # nothing before the first, 10 s before each of the other three
    assert p.requests_this_session == 4


def test_the_daily_budget_stops_the_run_and_frees_up_after_a_day(tmp_path):
    clock = Clock()
    p = pacer(clock, tmp_path, rpd=3)
    for _ in range(3):
        p.before_request()
    assert p.remaining_today() == 0
    with pytest.raises(DailyBudgetExhausted, match="3 requests in the last 24 hours"):
        p.before_request()
    clock.now += DAY_SECONDS + 1                 # a rolling window: the oldest requests age out
    p.before_request()
    assert p.used_last_24h() == 1


def test_the_daily_count_is_shared_between_processes(tmp_path):
    clock = Clock()
    pacer(clock, tmp_path, rpd=5).before_request()
    second = pacer(clock, tmp_path, rpd=5)       # a new process reading the same state file
    assert second.used_last_24h() == 1 and second.remaining_today() == 4


def test_a_request_that_would_overspend_the_token_budget_waits_for_the_window():
    clock = Clock()
    p = pacer(clock, tpm=1000)
    p.before_request(est_tokens=600)
    p.before_request(est_tokens=600)             # 1,200 in a minute: must wait for the first to age out
    assert clock.slept == pytest.approx(60.0)


def test_a_429_holds_the_next_request_for_the_providers_retry_after():
    clock = Clock()
    p = pacer(clock)
    p.before_request()
    p.after_response(429, {"Retry-After": "7"}, final=False)
    p.before_request()
    assert clock.slept == pytest.approx(7.0)


def test_a_429_without_retry_after_still_waits():
    clock = Clock()
    p = pacer(clock)
    p.before_request()
    p.after_response(429, {}, final=False)
    p.before_request()
    assert clock.slept >= 30.0                   # the backend's own short retry waits are not enough


def test_repeated_final_429s_stop_the_run_instead_of_hammering_the_key():
    p = pacer(Clock())
    p.after_response(429, {}, final=True)
    p.after_response(429, {}, final=True)
    with pytest.raises(DailyBudgetExhausted, match="429 on 3 requests in a row"):
        p.after_response(429, {}, final=True)


def test_a_success_clears_the_429_streak():
    p = pacer(Clock())
    p.after_response(429, {}, final=True)
    p.after_response(429, {}, final=True)
    p.after_response(200, {}, final=True)
    p.after_response(429, {}, final=True)        # the count started again: no stop


def test_the_providers_own_remaining_count_is_believed():
    clock = Clock()
    p = pacer(clock)
    p.before_request()
    p.after_response(200, {"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2.5s"})
    p.before_request()
    assert clock.slept == pytest.approx(2.5)


def test_a_provider_without_configured_limits_is_not_paced():
    assert ratelimit.limits_for("ollama") == {"rpm": None, "rpd": None, "tpm": None}


def test_configured_limits_sit_below_the_published_free_tiers():
    groq, gemini = ratelimit.limits_for("groq"), ratelimit.limits_for("gemini")
    assert groq["rpm"] <= 30 and groq["rpd"] <= 1000          # Groq publishes 30 a minute, 1,000 a day
    assert gemini["rpm"] <= 15 and gemini["rpd"] <= 1500      # Gemini publishes up to 15 a minute, 1,500 a day


# ----- the backends go through the pacer -----

class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body or {}, headers or {}, json.dumps(body or {})

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _openai_answer(text="ok"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def test_the_openai_backend_paces_each_attempt_and_waits_out_a_429(monkeypatch):
    from chatbot.backends import openai_backend
    clock = Clock()
    p = pacer(clock, rpm=60)
    monkeypatch.setattr(ratelimit, "get_pacer", lambda provider: p)
    monkeypatch.setattr(openai_backend.time, "sleep", clock.sleep)
    replies = iter([FakeResponse(429, headers={"retry-after": "5"}), FakeResponse(200, _openai_answer("done"))])
    monkeypatch.setattr(openai_backend.requests, "post", lambda *a, **k: next(replies))
    backend = openai_backend.OpenAIBackend(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    assert backend._chat([{"role": "user", "content": "hi"}], [])["choices"][0]["message"]["content"] == "done"
    assert p.requests_this_session == 2                        # the retry was counted too
    assert clock.slept >= 5.0


def test_the_gemini_backend_counts_every_attempt(monkeypatch):
    from chatbot.backends import gemini_backend
    clock = Clock()
    p = pacer(clock, rpm=60)
    monkeypatch.setattr(ratelimit, "get_pacer", lambda provider: p)
    monkeypatch.setattr(gemini_backend.time, "sleep", clock.sleep)
    replies = iter([FakeResponse(503), FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "x"}]}}]})])
    monkeypatch.setattr(gemini_backend.requests, "post", lambda *a, **k: next(replies))
    backend = gemini_backend.GeminiBackend(api_key="k", model="m")
    backend._generate([{"role": "user", "parts": [{"text": "hi"}]}], "system", [])
    assert p.requests_this_session == 2


def test_an_exhausted_budget_stops_before_any_request_is_sent(monkeypatch, tmp_path):
    from chatbot.backends import openai_backend
    clock = Clock()
    p = pacer(clock, tmp_path, rpd=1)
    p.before_request()
    monkeypatch.setattr(ratelimit, "get_pacer", lambda provider: p)
    sent = []
    monkeypatch.setattr(openai_backend.requests, "post", lambda *a, **k: sent.append(1) or FakeResponse(200, _openai_answer()))
    backend = openai_backend.OpenAIBackend(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    with pytest.raises(DailyBudgetExhausted):
        backend._chat([{"role": "user", "content": "hi"}], [])
    assert sent == []


# ----- strict servers: optional arguments may be null -----

def test_optional_tool_arguments_accept_null_for_the_openai_compatible_backend():
    from chatbot.backends._openai_compat import to_openai_function_tools
    from chatbot.tools import TOOL_SCHEMAS
    strict = {t["function"]["name"]: t["function"]["parameters"] for t in to_openai_function_tools(TOOL_SCHEMAS, nullable_optional=True)}
    plain = {t["function"]["name"]: t["function"]["parameters"] for t in to_openai_function_tools(TOOL_SCHEMAS)}
    aspect = strict["get_sentiment"]["properties"]["aspect"]
    assert "null" in aspect["type"] and None in aspect["enum"]
    assert strict["get_sentiment"]["properties"]["bank"]["type"] == "string", "a required argument stays required"
    assert plain["get_sentiment"]["properties"]["aspect"]["type"] == "string", "other backends are unchanged"
    assert TOOL_SCHEMAS[0]["input_schema"]["properties"]["aspect"]["type"] == "string", "the shared schema is not modified"


def test_a_null_argument_is_treated_as_not_given():
    from chatbot.tools import coerce_tool_arguments
    assert coerce_tool_arguments("get_sentiment", {"bank": "DBS", "aspect": None}) == {"bank": "DBS"}
