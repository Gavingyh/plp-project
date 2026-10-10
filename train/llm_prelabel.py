"""
LLM-assisted pre-labelling of data/labeled/candidates.csv, per the workflow
described in docs/annotation-guideline.md: a local model proposes a label and
a short rationale for each (sentence, aspect) pair, a human then corrects it.
This fills the `llm_prelabel` / `llm_rationale` columns only - it never
writes to `label`, which stays reserved for human judgement.

MODEL CHOICE: default is llama3.2:3b, not a larger "reasoning" model. Tested
both on the same case (a rising NPL ratio, which the annotation guideline's
own worked example labels `negative`): llama3.2:3b answered correctly in
3-5 seconds; qwen3:4b took 65-97 seconds AND answered `positive`, while its
own rationale described the same fact as "worsening risk exposure" and
"a negative signal" - its chain-of-thought reasoning contradicted its final
answer. Larger/slower was not more reliable for this task.

RESUMABILITY: every result is appended to a JSONL progress file immediately
after the model responds, and the row is merged into candidates.csv
periodically as the run proceeds. If the process is killed at any point,
re-running this script skips every (sentence_id, aspect) pair already in the
progress file rather than re-querying it. A prior unattended run in this
project was lost in full because it had no checkpointing; this is the fix.

USAGE:
  python -m train.llm_prelabel                  # all unlabelled rows
  python -m train.llm_prelabel --limit 10        # smoke test
  python -m train.llm_prelabel --model qwen3:4b  # override
"""

import argparse
import json
import os
import sys

import pandas as pd
import requests

from config.logging_config import get_logger, setup_logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
PROGRESS_PATH = os.path.join(BASE_DIR, "data", "labeled", "llm_prelabel_progress.jsonl")

DEFAULT_MODEL = "llama3.2:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"
REQUEST_TIMEOUT = 60
MERGE_EVERY = 20  # rows between incremental CSV merges, so progress is visible without waiting for the whole run

logger = get_logger(__name__)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "rationale": {"type": "string"},
    },
    "required": ["label", "rationale"],
}

# Mirrors docs/annotation-guideline.md's core question and decided edge
# cases, condensed for a single-turn prompt.
_SYSTEM_PROMPT = """You label financial sentiment for a retail-investor sentiment dashboard.

For each (bank, aspect, sentence) you are given, decide the sentiment toward the bank \
AS AN INVESTMENT on that specific aspect only - not the writer's general mood, and not \
sentiment toward something else that happens to share the sentence.

Rules:
- A factual statement with clear valence is not neutral. "NPL ratio rose to 1.4%" is \
negative on asset_quality even with no opinion words - the fact itself carries the valence.
- Label sarcasm by its intended meaning, not its literal words.
- Forward-looking guidance that raises expectations is positive on management_guidance \
even if current-quarter numbers were flat.
- Label a quoted analyst's stated view, not your own assessment of whether they are right.
- If the bank is mentioned only incidentally (e.g. a payment method, a product name) and \
the sentence has nothing to do with the bank as an investment, still choose the closest \
label rather than refusing - a human will correct this later.

Respond with a "rationale" of one short sentence, then the "label"."""


def _build_prompt(row: pd.Series) -> str:
    return f"Bank: {row['bank']}. Aspect: {row['aspect']}. Sentence: {row['text']}"


def classify(model: str, row: pd.Series) -> dict:
    """One Ollama call. Raises on failure - the caller decides how to handle it."""
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(row)},
            ],
            "format": _RESPONSE_SCHEMA,
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    parsed = json.loads(content)
    if parsed.get("label") not in ("positive", "neutral", "negative"):
        raise ValueError(f"model returned an invalid label: {parsed.get('label')!r}")
    return parsed


def _load_progress() -> dict[tuple[str, str], dict]:
    """Keyed by (sentence_id, aspect). Missing file means nothing done yet."""
    if not os.path.exists(PROGRESS_PATH):
        return {}
    done = {}
    with open(PROGRESS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done[(rec["sentence_id"], rec["aspect"])] = rec
            except (json.JSONDecodeError, KeyError):
                continue  # a partially-written last line from a killed process - skip it, not fatal
    return done


def _append_progress(record: dict) -> None:
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())  # survive a hard kill, not just a normal exit


def merge_into_csv(df: pd.DataFrame, progress: dict[tuple[str, str], dict]) -> pd.DataFrame:
    if "llm_rationale" not in df.columns:
        df["llm_rationale"] = ""
    for idx, row in df.iterrows():
        rec = progress.get((row["sentence_id"], row["aspect"]))
        if rec and rec.get("status") == "ok":
            df.at[idx, "llm_prelabel"] = rec["label"]
            df.at[idx, "llm_rationale"] = rec["rationale"]
    df.to_csv(CANDIDATES_PATH, index=False)
    return df


def run(model: str = DEFAULT_MODEL, limit: int | None = None) -> dict:
    if not os.path.exists(CANDIDATES_PATH):
        raise FileNotFoundError(
            f"{CANDIDATES_PATH} not found. Run `python -m preprocess.export_candidates` first."
        )
    df = pd.read_csv(CANDIDATES_PATH, keep_default_na=False)
    progress = _load_progress()

    # A row whose last attempt failed is tried again: a failure recorded as done
    # would leave its llm_prelabel empty for good.
    todo = df[~df.apply(lambda r: progress.get((r["sentence_id"], r["aspect"]), {}).get("status") == "ok",
                        axis=1)]
    if limit:
        todo = todo.head(limit)

    logger.info("candidates: %d total, %d already done, %d to process (model=%s)",
                len(df), len(progress), len(todo), model)

    stats = {"processed": 0, "ok": 0, "failed": 0}
    for i, (_, row) in enumerate(todo.iterrows()):
        try:
            result = classify(model, row)
            record = {"sentence_id": row["sentence_id"], "aspect": row["aspect"],
                      "status": "ok", "label": result["label"], "rationale": result["rationale"],
                      "model": model}
            stats["ok"] += 1
        except Exception as e:
            logger.warning("failed on %s/%s: %s", row["sentence_id"], row["aspect"], e)
            record = {"sentence_id": row["sentence_id"], "aspect": row["aspect"],
                      "status": "failed", "error": str(e), "model": model}
            stats["failed"] += 1

        _append_progress(record)
        progress[(row["sentence_id"], row["aspect"])] = record
        stats["processed"] += 1

        if stats["processed"] % MERGE_EVERY == 0:
            merge_into_csv(df, progress)
            logger.info("progress: %d/%d (%d ok, %d failed)",
                        stats["processed"], len(todo), stats["ok"], stats["failed"])

    merge_into_csv(df, progress)
    logger.info("done: %s", stats)
    return stats


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None, help="process at most N new rows (smoke test)")
    args = parser.parse_args()
    run(model=args.model, limit=args.limit)
