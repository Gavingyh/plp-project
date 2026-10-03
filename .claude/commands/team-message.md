---
description: Draft a WhatsApp message to the team about what changed, what to download or upload, and what they must do or decide
argument-hint: "[topic, e.g. new aspect file, decisions due Monday]"
---

Draft a team message about: $ARGUMENTS

- Plain text for WhatsApp: no markdown headers or tables, straight to the point, sub-items as indented points (CLAUDE.local.md).
- Say where things are: code in GitHub (`main`), models in the private Hugging Face repo `plp-bank-sentiment/plp-finbert-absa`, data that can't go in git or Hugging Face in the team's SharePoint folder (with `data/README-teams.md`), the to-do and decision brief (links in CLAUDE.local.md; they open only once shared).
- For files: name each file to upload or replace, its place under `data/`, and whether an older copy is still usable. Check sizes and dates with `ls -la` first.
- Every figure must come from the docs or a command run now. No personal names. No API keys or tokens.
- Show the draft; don't send anything.
