"""
Keeps the hosted chatbot backends under their free-tier limits.

A free tier limits requests per minute, requests per day and, for some
providers, tokens per minute. Going over costs more than a retry: the key can
be blocked for the day, and an evaluation that dies half way has to be
redone. This module is the one place that decides whether the next request may
go, so the backends (openai_backend.py, gemini_backend.py) only call
`pacer.before_request(...)` and `pacer.after_response(...)`.

Three layers, cheapest first:
  1. Pacing: at least 60 / rpm seconds between requests, and a tokens-per-minute
     window when `tpm` is set. The budgets in config/chatbot.yaml sit below the
     published limits.
  2. The provider's own numbers: a response with remaining-requests or
     remaining-tokens headers (Groq sends them) is believed over our counts, and
     the next request waits for the reset when the allowance is spent.
  3. A stop: `DailyBudgetExhausted` when the rolling 24-hour request count reaches
     `rpd`, or when the provider returns 429 more times in a row than the retries
     can explain. The evaluation catches it, keeps what it has and can be
     resumed (chatbot/run_eval.py --resume).

The 24-hour count is a rolling window of request times kept in
data/ratelimit_state.json, not a calendar day, because providers reset at
different hours (UTC midnight, Pacific midnight) and a count kept per calendar
day would over-spend across the reset.
"""

import json
import os
import re
import threading
import time
from urllib.parse import urlparse

from chatbot import settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE_DIR, "data", "ratelimit_state.json")
DAY_SECONDS = 24 * 3600
MAX_CONSECUTIVE_429 = 3          # final 429s (after the backend's own retries) before the run stops


class DailyBudgetExhausted(RuntimeError):
    """The provider's budget for now is spent. Stop, keep results, resume later."""


def provider_for(backend_name: str, base_url: str | None = None) -> str:
    """The provider a backend talks to: the host's name for an OpenAI-compatible
    base URL (api.groq.com -> groq), else the backend's own name."""
    if backend_name == "openai" and base_url:
        host = (urlparse(base_url).hostname or "").lower()
        for known in ("groq", "openrouter", "nvidia", "mistral", "cohere"):
            if known in host:
                return known
        if "openai.com" in host:
            return "openai"
        return host.split(".")[-2] if host.count(".") >= 1 else host
    return backend_name


def parse_duration(text: str | None) -> float | None:
    """'2m59.56s', '7.66s', '120ms', '1h2m' or plain seconds -> seconds."""
    if text is None:
        return None
    text = str(text).strip()
    try:
        return float(text)
    except ValueError:
        pass
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", text)
    if not parts:
        return None
    unit = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    return sum(float(n) * unit[u] for n, u in parts)


def limits_for(provider: str) -> dict:
    """{'rpm', 'rpd', 'tpm'} for a provider from config/chatbot.yaml; a provider
    with no entry gets no pacing (local models)."""
    try:
        return {k: settings.get(f"rate_limits.{provider}.{k}") for k in ("rpm", "rpd", "tpm")}
    except KeyError:
        return {"rpm": None, "rpd": None, "tpm": None}


class Pacer:
    def __init__(self, provider: str, rpm: int | None = None, rpd: int | None = None, tpm: int | None = None,
                 state_path: str | None = STATE_PATH, clock=time.time, sleep=time.sleep):
        self.provider, self.rpm, self.rpd, self.tpm = provider, rpm or None, rpd or None, tpm or None
        self.state_path, self._clock, self._sleep = state_path, clock, sleep
        self._lock = threading.Lock()
        self._last = 0.0                       # time of the last request
        self._tokens: list[tuple[float, int]] = []     # (time, estimated tokens) in the last minute
        self._hold_until = 0.0                 # a provider-reported wait, or a cooldown after a 429
        self._consecutive_429 = 0
        self.requests_this_session = 0
        self.waited_seconds = 0.0

    # ----- the rolling 24-hour request count, shared by every process -----
    def _times(self) -> list[float]:
        if not self.state_path or not os.path.exists(self.state_path):
            return []
        try:
            with open(self.state_path, encoding="utf-8") as f:
                times = json.load(f).get(self.provider, [])
        except (OSError, ValueError):
            return []
        cutoff = self._clock() - DAY_SECONDS
        return [t for t in times if t > cutoff]

    def _record(self, times: list[float]) -> None:
        if not self.state_path:
            return
        data = {}
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
        data[self.provider] = times
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def used_last_24h(self) -> int:
        return len(self._times())

    def remaining_today(self) -> int | None:
        return None if not self.rpd else max(self.rpd - self.used_last_24h(), 0)

    # ----- before and after each request -----
    def _wait(self, seconds: float) -> None:
        if seconds > 0:
            self.waited_seconds += seconds
            self._sleep(seconds)

    def before_request(self, est_tokens: int = 0) -> None:
        """Block until the request may go; raise DailyBudgetExhausted if the day's budget is spent."""
        with self._lock:
            times = self._times()
            if self.rpd and len(times) >= self.rpd:
                oldest_frees_at = min(times) + DAY_SECONDS
                raise DailyBudgetExhausted(
                    f"{self.provider}: {len(times)} requests in the last 24 hours, the budget is {self.rpd}. "
                    f"Room again in about {max(int((oldest_frees_at - self._clock()) / 60), 1)} minutes; "
                    f"rerun with --resume.")
            now = self._clock()
            wait = max(self._hold_until - now, 0.0)
            if self.rpm:
                wait = max(wait, self._last + 60.0 / self.rpm - now)
            if self.tpm and est_tokens:
                window = [(t, n) for t, n in self._tokens if t > now - 60]
                spent = sum(n for _, n in window)
                if window and spent + est_tokens > self.tpm:
                    # wait until enough of the window's tokens are older than a minute
                    needed, freed = spent + est_tokens - self.tpm, 0
                    for t, n in sorted(window):
                        freed += n
                        if freed >= needed:
                            wait = max(wait, t + 60 - now)
                            break
            self._wait(wait)
            now = self._clock()
            self._last = now
            if self.tpm and est_tokens:
                self._tokens = [(t, n) for t, n in self._tokens if t > now - 60] + [(now, est_tokens)]
            self._record(times + [now])
            self.requests_this_session += 1

    def after_response(self, status: int, headers: dict | None = None, final: bool = True) -> None:
        """Learn from a response. `final` is False for a response the backend will retry."""
        headers = {str(k).lower(): v for k, v in (headers or {}).items()}
        with self._lock:
            if status == 429:
                after = parse_duration(headers.get("retry-after"))
                self._hold_until = max(self._hold_until, self._clock() + (after if after is not None else 30.0))
                if final:
                    self._consecutive_429 += 1
                    if self._consecutive_429 >= MAX_CONSECUTIVE_429:
                        raise DailyBudgetExhausted(
                            f"{self.provider} returned 429 on {self._consecutive_429} requests in a row even "
                            f"after waiting; the limit is lower than configured. Stopping so the key is not "
                            f"blocked. Lower rate_limits.{self.provider} in config/chatbot.yaml, then --resume.")
                return
            if final and status < 400:
                self._consecutive_429 = 0
            # the provider's own count of what is left, when it sends one
            req_left = headers.get("x-ratelimit-remaining-requests")
            tok_left = headers.get("x-ratelimit-remaining-tokens")
            try:
                if req_left is not None and float(req_left) < 1:
                    reset = parse_duration(headers.get("x-ratelimit-reset-requests")) or 60.0
                    self._hold_until = max(self._hold_until, self._clock() + reset)
                if tok_left is not None and self.tpm and float(tok_left) < 0.2 * self.tpm:
                    reset = parse_duration(headers.get("x-ratelimit-reset-tokens")) or 30.0
                    self._hold_until = max(self._hold_until, self._clock() + reset)
            except ValueError:
                pass


_pacers: dict[str, Pacer] = {}


def get_pacer(provider: str) -> Pacer | None:
    """The shared pacer for a provider, or None for one without limits configured."""
    limits = limits_for(provider)
    if not any(limits.values()):
        return None
    if provider not in _pacers:
        _pacers[provider] = Pacer(provider, **limits)
    return _pacers[provider]


def estimate_tokens(payload) -> int:
    """About one token per four characters of the request body: close enough to pace by."""
    return max(len(json.dumps(payload, ensure_ascii=False)) // 4, 1)


def session_requests() -> int:
    """Requests made by this process, for the evaluation's per-question counts."""
    return sum(p.requests_this_session for p in _pacers.values())
