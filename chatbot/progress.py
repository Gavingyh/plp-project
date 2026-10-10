"""
The steps of one chatbot turn, in words a reader can follow while waiting.

A local model takes about a minute to answer (median 47 s on the gold set),
and a spinner says nothing about what it is doing. answer_turn
reports each step it takes to an optional callback (on_step): reading the
question, each tool the model calls with what it asked for and what came
back, writing the answer, and checking it. The dashboard can show these as
they happen, like a model's visible working.

These are the turn's real steps, built from its tool calls; the local model
writes no reasoning of its own to show. Each step is a Step: kind, title
(one line), detail (a short second line or None) and done (False while the
step is still running).
"""

from dataclasses import dataclass

from config import sources as source_config

_WINDOWS = {"7d": "last 7 days", "30d": "last 30 days", "all_time": "all time"}


@dataclass
class Step:
    kind: str                  # "read", "intent", "think", "tool", "check", "done"
    title: str
    detail: str | None = None
    done: bool = True


def _topic(args: dict, result: dict) -> str:
    name = (result or {}).get("topic_name")
    if name:
        return name if name.lower() != "overall" else "overall"
    aspect = args.get("aspect")
    return aspect.replace("_", " ") if aspect and aspect != "ALL" else "overall"


def _window(args: dict, result: dict) -> str:
    return _WINDOWS.get((result or {}).get("window") or args.get("window") or "all_time", "all time")


def _score(r: dict) -> str:
    if not r or r.get("insufficient_data") or r.get("score") is None:
        return "not enough sentences to score"
    reading = r.get("reading")
    text = f"{r['score']:+.2f}" + (f", {reading}" if reading else "")
    return text + (f", {r['n']:,} sentences" if r.get("n") is not None else "")


def describe_call(name: str, args: dict, result) -> Step:
    """One tool call as a step: what was asked for, and in brief what came back."""
    args = args or {}
    r = result if isinstance(result, dict) else {}
    if r.get("error"):
        return Step("tool", f"Tried {name.replace('_', ' ')}", f"It failed: {r['error']}")
    bank = args.get("bank") or r.get("bank") or ""
    if name == "get_sentiment":
        return Step("tool", f"Looked up {bank} sentiment on {_topic(args, r)} ({_window(args, r)})", _score(r))
    if name == "compare_banks":
        banks = r.get("banks") or {}
        detail = "; ".join(f"{b} {_score(v).split(',')[0]}" for b, v in banks.items()) or None
        return Step("tool", f"Compared DBS, OCBC and UOB on {_topic(args, next(iter(banks.values()), {}))} "
                            f"({_window(args, r)})", detail)
    if name == "get_trend":
        detail = r.get("trend_in_words") or r.get("note")
        return Step("tool", f"Checked how {bank} sentiment on {_topic(args, r)} has moved", detail)
    if name == "get_coverage":
        detail = f"{r['n']:,} sentences" if r.get("n") is not None else None
        if detail and r.get("latest"):
            detail += f", the newest from {str(r['latest'])[:10]}"
        return Step("tool", f"Checked what data exists{' for ' + bank if bank else ''}", detail)
    if name == "search_evidence":
        found = r.get("results") or []
        kinds = sorted({source_config.label(x.get("source")) for x in found if x.get("source")})
        detail = (f"{len(found)} sentence{'s' if len(found) != 1 else ''} found"
                  + (f", from {', '.join(kinds)}" if kinds else "")) if found else "nothing found"
        query = args.get("query") or ""
        about = f"what people say about {bank}" if bank else "what people say"
        return Step("tool", f"Searched {about}" + (f": “{query}”" if query else ""), detail)
    if name == "get_analyst_consensus":
        if not r.get("has_data", True):
            return Step("tool", f"Looked up analysts' view of {bank}", "no analyst data")
        parts = []
        if r.get("consensus_rating"):
            parts.append(f"{r['consensus_rating']}" + (f" from {r['n_analysts']} analysts" if r.get("n_analysts") else ""))
        if r.get("target_mean") is not None:
            parts.append(f"average target {r['target_mean']:.2f}")
        return Step("tool", f"Looked up analysts' view of {bank}", ", ".join(parts) or None)
    return Step("tool", f"Used {name.replace('_', ' ')}")


def notify(on_step, step: Step) -> None:
    """Pass a step to the callback; a failing callback never breaks the answer."""
    if on_step is None:
        return
    try:
        on_step(step)
    except Exception:       # the display is optional; the answer is not
        pass
