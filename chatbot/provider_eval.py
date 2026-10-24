"""
Runs the chatbot evaluation through Ollama and OpenAI, one after the other,
then writes the comparison report. Groq remains an optional compatible arm.

What it does for each arm (an arm is one provider and model):
  1. Checks it is ready: a key for a hosted arm, a running Ollama with the model
     pulled for the local arm. An arm that is not ready is skipped and named; nothing
     is sent anywhere for it.
  2. Prints what the run will cost against the provider's budget, before any request.
  3. Runs the question sets through `chatbot.run_eval` in a subprocess with that arm's
     settings, each answer saved as it arrives. A hosted run that reaches its budget
     stops with exit code 3; this script stops that arm, goes on to the next, and a
     later `--resume` carries on where it left off.

The Ollama arm goes first: it is free, and its tool-call counts give the best estimate of
how many requests the hosted arms will need.

Keys are read from .env but never printed, and this script never writes to .env.
Groq's key is read from GROQ_API_KEY, or from OPENAI_API_KEY when OPENAI_BASE_URL points
at Groq. OpenAI uses OPENAI_API_KEY and OPENAI_MODEL on the official API endpoint.

USAGE:
  python -m chatbot.provider_eval --dry-run          # readiness and the request budget; no calls
  python -m chatbot.provider_eval                    # run every ready arm
  python -m chatbot.provider_eval --arms openai      # one arm (paid API)
  python -m chatbot.provider_eval --resume           # keep saved answers, ask only the rest
"""

import argparse
import json
import os
import subprocess
import sys

import requests
from dotenv import dotenv_values

from chatbot import provider_report, ratelimit, settings
from chatbot.eval_gold_set import GOLD_SET_V2, MULTI_TURN, MULTI_TURN_SCOPE, SCOPE_SET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"
# Guess at model requests per question when no local run exists to count them: one to call a
# tool, one to answer, and room for a second tool call.
DEFAULT_REQUESTS_PER_ITEM = 4
# Question sets in the order they are run, so a stop costs the least important last.
JOBS = [("v2", False, "v2"), ("scope", False, "scope"), ("multi", True, "v1"), ("multiscope", True, "scope")]


def read_env() -> dict:
    return {k: (v or "") for k, v in dotenv_values(os.path.join(BASE_DIR, ".env")).items()}


def arm_settings(arm: str, env: dict) -> tuple[dict, str | None]:
    """(environment for the arm's subprocess, why it can't run or None)."""
    if arm == "ollama":
        return {}, None
    if arm == "openai":
        if not env.get("OPENAI_API_KEY"):
            return {}, "no OpenAI key: set OPENAI_API_KEY in .env"
        url = env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        if url.rstrip("/") != "https://api.openai.com/v1":
            return {}, "the OpenAI arm requires OPENAI_BASE_URL=https://api.openai.com/v1; use --arms groq for Groq"
        return {"OPENAI_API_KEY": env["OPENAI_API_KEY"], "OPENAI_BASE_URL": url,
                "OPENAI_MODEL": env.get("OPENAI_MODEL") or settings.get("models.openai")}, None
    if arm == "groq":
        key = env.get("GROQ_API_KEY") or (env.get("OPENAI_API_KEY") if "groq" in env.get("OPENAI_BASE_URL", "") else "")
        if not key:
            return {}, ("no Groq key: set GROQ_API_KEY in .env (or OPENAI_API_KEY with "
                        f"OPENAI_BASE_URL={GROQ_URL})")
        return {"OPENAI_API_KEY": key, "OPENAI_BASE_URL": GROQ_URL,
                "OPENAI_MODEL": env.get("GROQ_MODEL") or GROQ_MODEL}, None
    return {}, f"unknown arm {arm}"


def key_problem(arm: str, arm_env: dict, timeout: float = 15.0) -> str | None:
    """None if the provider accepts the key, else why not. Lists models, which sends no prompt and
    uses none of the generation budget, so a wrong key is found before a long run starts."""
    if arm in ("groq", "openai"):
        url, headers = f"{arm_env['OPENAI_BASE_URL']}/models", {"Authorization": f"Bearer {arm_env['OPENAI_API_KEY']}"}
    else:
        return None
    try:
        status = requests.get(url, headers=headers, timeout=timeout).status_code
    except requests.RequestException as e:
        return f"could not reach the provider: {type(e).__name__}"
    if status in (400, 401, 403):
        return (f"the provider rejected the key (HTTP {status}); create a new one "
                f"({'platform.openai.com/api-keys' if arm == 'openai' else 'console.groq.com'}) and update .env")
    return None if status < 400 else f"the provider answered HTTP {status}"


def backend_for(arm: str) -> str:
    return {"ollama": "ollama", "groq": "openai", "openai": "openai"}[arm]


def ollama_ready(model: str | None = None, timeout: float = 3.0) -> str | None:
    """None if Ollama answers and has the model (and the intent model); else why not."""
    url = settings.get("ollama_url")
    try:
        names = {m["name"] for m in requests.get(f"{url}/api/tags", timeout=timeout).json().get("models", [])}
    except (requests.RequestException, ValueError):
        return f"Ollama is not running at {url}"
    wanted = {model or settings.get("models.ollama"), settings.get("models.intent")}
    have = {n.split(":latest")[0] for n in names} | names
    missing = sorted(w for w in wanted if w not in have)
    return f"Ollama is missing {', '.join(missing)} (ollama pull <name>)" if missing else None


def gold_size(key: str) -> int:
    return {"v2": len(GOLD_SET_V2), "scope": len(SCOPE_SET),
            "multi": sum(len(s["turns"]) for s in MULTI_TURN),
            "multiscope": sum(len(s["turns"]) for s in MULTI_TURN_SCOPE)}[key]


def requests_per_item(eval_dir: str = provider_report.EVAL_DIR) -> tuple[float, str]:
    """Hosted requests to expect per question: from the local run's model tool calls when it
    exists (one request per call plus one to answer), else a cautious default."""
    counts = []
    for key in ("v2", "scope"):
        for r in provider_report.single_results("ollama", key, eval_dir):
            counts.append(1 + sum(1 for c in r.get("tool_calls", []) if c.get("by", "model") == "model"))
    if counts:
        return sum(counts) / len(counts), f"measured on {len(counts)} local answers"
    return float(DEFAULT_REQUESTS_PER_ITEM), "a default; no local run to measure"


def plan(arm: str, per_item: float) -> dict:
    """What a full run of the arm would send and how long pacing alone would take."""
    n = sum(gold_size(k) for k, *_ in JOBS)
    est = int(round(n * per_item * 1.15))            # 15% for retries and slower questions
    lim = ratelimit.limits_for(ratelimit.provider_for(backend_for(arm), GROQ_URL if arm == "groq" else None))
    out = {"questions": n, "estimated_requests": est, "rpm": lim["rpm"], "rpd": lim["rpd"], "minutes": None,
           "fits_today": True, "remaining_today": None}
    if lim["rpm"]:
        out["minutes"] = est / lim["rpm"]
    if lim["rpd"]:
        pacer = ratelimit.Pacer(ratelimit.provider_for(backend_for(arm), GROQ_URL if arm == "groq" else None), **lim)
        out["remaining_today"] = pacer.remaining_today()
        out["fits_today"] = est <= out["remaining_today"]
    return out


def save_status(updates: dict, eval_dir: str = provider_report.EVAL_DIR) -> None:
    """Remember each arm's last outcome so the report can say why an arm has no results."""
    path = os.path.join(eval_dir, "provider_eval_status.json")
    status = provider_report.read_status(eval_dir)
    status.update(updates)
    os.makedirs(eval_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=1)


def run_arm(arm: str, env: dict, resume: bool) -> str:
    """Run the arm's sets; 'done', or 'stopped' if the provider's budget ran out."""
    arm_env, _ = arm_settings(arm, env)
    child_env = {**os.environ, **{k: v for k, v in env.items() if v}, **arm_env,
                 "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1"}
    for key, multi, gold in JOBS:
        cmd = [sys.executable, "-m", "chatbot.run_eval", "--backend", backend_for(arm), "--tag", f"{arm}-{key}",
               "--set", gold]
        if multi:
            cmd.append("--multi-turn")
        if resume:
            cmd.append("--resume")
        print(f"[{arm}] {' '.join(cmd[2:])}", flush=True)
        code = subprocess.run(cmd, cwd=BASE_DIR, env=child_env).returncode
        if code == 3:
            print(f"[{arm}] stopped: the provider's budget is spent. Rerun with --resume later.", flush=True)
            return "stopped"
        if code != 0:
            print(f"[{arm}] {key} exited with code {code}; going on to the next set.", flush=True)
    return "done"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arms", nargs="+", default=provider_report.DEFAULT_ARMS, choices=provider_report.ARM_ORDER)
    ap.add_argument("--dry-run", action="store_true", help="check readiness and the budget; send nothing")
    ap.add_argument("--resume", action="store_true", help="keep answers already saved, ask only the rest")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    env = read_env()

    ready, skipped = [], {}
    local_problem = ollama_ready()
    for arm in args.arms:
        _, why = arm_settings(arm, env)
        if arm == "ollama":
            why = local_problem
        elif local_problem:
            # Not fatal: the question still reaches the model, but no intent is found, so the
            # input-guard checks fail for a reason that is not the model's.
            print(f"[{arm}] note: {local_problem}. The intent classifier will not run, so questions that a "
                  f"guard should answer will reach the model and fail the guard check.")
        (skipped.__setitem__(arm, why) if why else ready.append(arm))

    if not args.dry_run:
        for arm in list(ready):
            problem = key_problem(arm, arm_settings(arm, env)[0])
            if problem:
                ready.remove(arm)
                skipped[arm] = problem

    per_item, basis = requests_per_item()
    print(f"\nExpected hosted requests per question: {per_item:.1f} ({basis})")
    for arm in args.arms:
        if arm in skipped:
            print(f"  {arm:7s} NOT READY: {skipped[arm]}")
            continue
        p = plan(arm, per_item)
        if p["rpm"]:
            print(f"  {arm:7s} ready. About {p['estimated_requests']} requests for {p['questions']} questions; "
                  f"paced at {p['rpm']} a minute that is about {p['minutes']:.0f} minutes. "
                  f"Budget left in the last 24 hours: {p['remaining_today']} of {p['rpd']}"
                  f"{'' if p['fits_today'] else '  <- NOT ENOUGH for one pass; it will stop and need --resume'}")
        elif arm == "ollama":
            print(f"  {arm:7s} ready (local, no limit)")
        else:
            print(f"  {arm:7s} ready (paid API; account limits apply). About {p['estimated_requests']} requests for {p['questions']} questions.")
    if args.dry_run or not ready:
        if not ready:
            print("\nNothing is ready, so nothing was run.")
        if not args.dry_run:
            save_status({a: {"state": "skipped", "note": why} for a, why in skipped.items()})
        return 0 if args.dry_run else 2

    outcome = {arm: run_arm(arm, env, args.resume) for arm in ready}
    save_status({**{a: {"state": "skipped", "note": why} for a, why in skipped.items()},
                 **{a: {"state": s, "note": ""} for a, s in outcome.items()}})
    if not args.no_report:
        print("report:", provider_report.write_report(args.arms))
    print("\n" + json.dumps(outcome))
    return 3 if "stopped" in outcome.values() else 0


if __name__ == "__main__":
    sys.exit(main())
