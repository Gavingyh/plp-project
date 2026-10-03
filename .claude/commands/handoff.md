---
description: End of session: log the session in docs/HANDOFF.md, update the team pages, check the docs, then commit and push by path
argument-hint: "[anything to stress in the entry]"
---

Close the session. $ARGUMENTS

1. `git status --short` and `git log --oneline origin/main..HEAD`: list what changed this session and what isn't pushed.
2. Add one dated entry at the end of `docs/HANDOFF.md` in its existing style: what was done (with commits), what was measured (numbers only from files or commands run this session), what changed for the team, and **Needs a human** items. Plain names, no codes; absolute dates.
3. Team pages: if anything changed what the team must do or decide, edit the to-do and decision-brief sources in the scratchpad, copy them to `docs/briefs/`, and republish both to their existing links (CLAUDE.local.md). Every issue found this session that isn't fixed must be on the to-do or the brief, or it isn't "known".
4. If code changed, run `/sync-docs` first. Run `HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q` and say the result.
5. Commit by path (never `git add -A`, never `data/logs/plp.log`), one commit per finished piece of work, messages that say what changed and why, ending with the attribution line. Push only completed, tested work.
6. Report: commits, test result, links republished, and what is waiting for whom.
