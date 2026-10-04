---
description: Status of long-running jobs (LLM aspect runs, previews, scoring, training): alive or not, progress, rough time left
argument-hint: "[a log file or job name; empty = all known jobs]"
---

Report on long-running jobs: $ARGUMENTS

1. Find them: `ps -eo pid,etime,command | grep -E "llm_classify|aggregate.preview|sentiment.score|train.finetune|rescore|caffeinate" | grep -v grep`. Check each with `kill -0 <pid>`, not `pgrep -f` (it matches itself).
2. Progress, read-only:
   - LLM aspects: lines in `data/aspect_llm/<model>.<prompt>.jsonl` against 44,345 sentences (`python -c "from aspects.llm_classify import answer_cache_path; print(answer_cache_path('llama3.1:8b'))"` gives the current file).
   - Preview and fine-tuned scoring: the last `scored N/M` line of its log, and the size of `data/preview/scores.*.jsonl`.
   - Anything else: the last lines of its log.
3. Rate: compare two readings a few minutes apart or the log's timestamps. Give time left as a rough estimate ("about two hours"), not to the minute.
4. Flag what slows it: another Ollama job (one at a time), heavy test runs, the Mac on battery or asleep (`pmset -g batt`, `pmset -g assertions | grep -i prevent`).
5. Never stop, restart or start a job without asking.
