# Diagrams

Twenty Mermaid diagrams of the system, drawn from the code and the database as of
2026-09-26. Each page has the diagram, what it does and doesn't show, and a sources
table naming the file and line every element comes from. `check_sources.py` checks
those lines still say what the table claims.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows
labelled *planned* are decided but not yet built, with the DESIGN.md decision or PLAN.md
section that records them. Shapes marked *not installed* exist in the repository but
aren't running anywhere.

## Index

Core diagrams (01–10) cover the whole system; extended ones (11–20) zoom in on one part.
All twenty are rendered.

| # | diagram | type | question it answers | set |
|---|---|---|---|---|
| 01 | [System context](01-system-context.md) | flowchart | Who uses the system, and which outside services does it depend on? | core |
| 02 | [Runtime: what runs where](02-runtime.md) | flowchart | Which processes run, on which ports, reading and writing which files? | core |
| 03 | [Data model](03-data-model.md) | ER | What are the six tables, their keys, and how do they relate? | core |
| 04 | [Pipeline: from sources to the dashboard](04-pipeline.md) | flowchart | How does text become a sentiment score, stage by stage? | core |
| 05 | [News ingestion, one run](05-news-ingestion.md) | sequence | What happens, in order, during a news pull? | core |
| 06 | [A batch run, from ingestion to the index](06-batch-pipeline.md) | sequence | In what order are the batch steps run, and why is re-running safe? | core |
| 07 | [Chatbot: one turn](07-chatbot-turn.md) | flowchart | Which paths can a question take, and where does code rather than the model decide? | core |
| 08 | [Chatbot: one turn from the dashboard](08-chatbot-sequence.md) | sequence | Which component calls which when an investor asks a question? | core |
| 09 | [Labelling and training](09-labelling-training.md) | flowchart | How do labels become the fine-tuned model, as built and as planned? | core |
| 10 | [Five weeks to submission](10-plan.md) | Gantt | What happens each week to 1 November, and what closes each week? | core |
| 11 | [News filter: what happens to one article](11-news-filter.md) | flowchart | In what order is a news article checked, and why is it dropped? | extended |
| 12 | [How a sentiment index row is computed](12-index-computation.md) | flowchart | How do scored sentences become the index numbers? | extended |
| 13 | [Chatbot through the REST API](13-api-chat.md) | sequence | How does a client hold a conversation through a stateless API? | extended |
| 14 | [Chatbot components](14-chatbot-components.md) | class | Which classes and modules make up the chatbot? | extended |
| 15 | [Conversation state across turns](15-conversation-state.md) | state | How does the chatbot remember which bank and aspect are being discussed? | extended |
| 16 | [One candidate row under version 2](16-label-lifecycle.md) | state | What states does a row go through in the planned labelling? (all planned) | extended |
| 17 | [What each rubric item rests on](17-rubric-map.md) | flowchart | Which component answers each rubric item, and which course module does it draw on? | extended |
| 18 | [Sharing the database as snapshots](18-snapshots.md) | flowchart | How does the database reach a teammate without git? | extended |
| 19 | [What an investor can do in the dashboard](19-dashboard-journey.md) | flowchart | What does each dashboard tab let a reader do? | extended |
| 20 | [How the chatbot is evaluated](20-chatbot-evaluation.md) | flowchart | What does the evaluation check automatically, and what is left to a person? | extended |

## Report shortlist

Suggested for the report; the rest are for the team and the appendix. Use the PNGs in
`img/` (1600px wide, white background) or the SVGs.

| # | diagram | report section |
|---|---|---|
| 01 | System context | Introduction, or the start of system design |
| 03 | Data model | Datasets |
| 04 | Pipeline | Solution approach |
| 07 | Chatbot: one turn | Conversational UI (use 08 instead if the section is about components rather than behaviour) |
| 09 | Labelling and training | Methodology: annotation and model training |
| 10 | Five weeks to submission | Project management |

Also worth considering: 17 for the solution-approach section if the report maps
components to the rubric explicitly, and 20 for the evaluation section.

## Regenerating

After changing the code a diagram describes:

1. Edit `src/NN-name.mmd`.
2. Copy it into the ```` ```mermaid ```` block of `NN-name.md`, and update the sources
   table if an element moved or changed.
3. Render: `docs/diagrams/render_diagrams.sh` (all), or
   `docs/diagrams/render_diagrams.sh 07` (names starting with `07`). It uses the
   Mermaid CLI through `npx`, so it needs Node and a network connection the first time.
4. Check: `.venv-plp/bin/python3 docs/diagrams/check_sources.py`, then
   `.venv-plp/bin/python3 -m pytest -q docs/diagrams/test_diagrams.py`. The test fails
   if a page's diagram differs from its `.mmd` file or a page has no sources table.

`schema-2026-09-26.txt` is the `PRAGMA` dump the data model (03) was drawn from.
