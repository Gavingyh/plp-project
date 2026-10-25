# Documentation map and current figures

Read this first if you are writing the report or the slides from this
repository. It says which documents describe the project as it is now,
which are dated records, and which are superseded, and it gives the current
headline figures with the file each comes from.

## Which documents to trust

| Kind | Files | How to read them |
|---|---|---|
| **Current** | [README.md](../README.md), [STATUS.md](STATUS.md), [RUNBOOK.md](RUNBOOK.md), [model-card.md](model-card.md), [api-integration.md](api-integration.md), [spec/](spec/), [annotation-guideline.md](annotation-guideline.md), [diagrams/](diagrams/), [briefs/team-todo.html](briefs/team-todo.html) | Describe the system as built. If one of them disagrees with the code or the database, the code and the database win; please report it. |
| **The report** | Not in this repository: the master is a Word file on the team's SharePoint. [report/word-report-updates.md](report/word-report-updates.md) holds replacement text for it; [report/conversation-design.md](report/conversation-design.md) is source text for the conversational UI section | Take the report's figures from the table below and the current documents, not from an old copy of the report. |
| **Decision log** | [DESIGN.md](DESIGN.md), [PLAN.md](PLAN.md) | Each decision keeps the reasoning of its day. A later decision can supersede an earlier one; the top of DESIGN.md says what holds now. |
| **Dated records** | [evidence/](evidence/), [validation/](validation/), [review/](review/), [HANDOFF.md](HANDOFF.md), [verification-ledger.md](verification-ledger.md), [data-viability.md](data-viability.md), [news-data.md](news-data.md), [briefs/decisions-2026-10-02.html](briefs/decisions-2026-10-02.html), [briefs/model-comparison-2026-10-12.html](briefs/model-comparison-2026-10-12.html) | True for the date in their name or heading. A later note on the same topic supersedes an earlier one. Quote a figure from them only if the table below or a current document agrees. |
| **Study notes** | [learning/](../learning/) | Concepts explained on this project's data as it was between 11 Sep and 11 Oct 2026. Use them for the ideas, not for current figures. |
| **Superseded** | [archive/](archive/) | Earlier report drafts, briefs and checklists. Kept for the record; do not quote them. |

## Current figures

Each figure below was read from the file or the database named beside it.
The database is `data/plp.db` (restored from `data/data.zip`; see the
[README](../README.md)).

### Corpus

| Figure | Value | Source |
|---|---|---|
| Documents, sentences | 28,852 documents, 45,844 sentences | `documents`, `sentences` tables |
| Period | posts and articles published up to 25 Sep 2026; nothing later was collected (25 broker research reports added on 4 Oct and 825 older Reddit posts on 11 Oct were all published earlier) | newest `sentences.published_at`; `documents.ingested_at` |
| Sentences by source | Reddit 25,533 (22,630 posts and comments) · earnings reports 12,254 · Google News 5,447 · CNA 1,599 · broker research 641 · Yahoo News 344 · NewsAPI 26 | `sentences` grouped by `source` |
| Sentences by bank | DBS 24,978 · UOB 13,092 · OCBC 7,774 | `sentences` grouped by `bank` |

### Sentiment model

| Figure | Value | Source |
|---|---|---|
| Model in use | `finbert-adapted-finetuned-2026-10-11-3seed-m0`: FinBERT further pretrained on the corpus, fine-tuned on (sentence, aspect) pairs, three seeds averaged | [config/model_version.py](../config/model_version.py) |
| Stored scores | the model in use and base FinBERT (`finbert-base-zeroshot-v1`) side by side, 45,844 rows each; the API serves only the model in use | `aspect_sentiment` grouped by `model_version` |
| Training labels | 1,563 sentence-aspect pairs labelled by an LLM rater, not by people | [model-card.md](model-card.md), Training |
| Test, 299 first-round sentences labelled by people | macro-F1 0.670 for the three seeds averaged (accuracy 0.716) against base FinBERT's 0.571 (0.699); each seed 0.628, 0.657, 0.662 (mean 0.649, sd 0.018) | [model-card.md](model-card.md), Evaluation |
| Where the gain is | negative recall 0.21 to 0.59 and positive 0.53 to 0.73, paid for with neutral recall 0.91 to 0.73; accuracy difference not significant (exact McNemar p = 0.65) | the same |
| Test, 100 broker research sentences | 0.770 against 0.687 | the same |
| How it was chosen | candidates compared by a rule fixed before the test rows were scored: test macro-F1 over three seeds, cross-validation as the tie-breaker | the same, Training |

### Aspects

| Figure | Value | Source |
|---|---|---|
| Method | one aspect a sentence, chosen by `llama3.1:8b` from 10 aspects plus `other` (`assignment_method: llm`) | [config/aspects.yaml](../config/aspects.yaml) |
| Agreement with people | 73.9% on the 1,277 sentences people labelled | [evidence/wealth-definition-trial-2026-10-12.md](evidence/wealth-definition-trial-2026-10-12.md) |

### Index (all time, model in use)

| Rows | DBS | OCBC | UOB | Source |
|---|---|---|---|---|
| All sources | +0.143 (24,978 sentences) | +0.129 (7,774) | +0.107 (13,092) | `sentiment_index`, `aspect = 'ALL'`, `source = 'ALL'` |
| Reddit only | +0.058 | -0.009 | +0.058 | the same, `source = 'arctic_shift'` |
| Earnings reports only | +0.276 | +0.343 | +0.332 | the same, `source = 'earnings'` |

A score runs from -1 to +1. Earnings text, management describing its own
results, scores far higher than Reddit for every bank, so compare banks on
one source at a time.

### API and chatbot

| Figure | Value | Source |
|---|---|---|
| API | 20 paths, 21 operations | [api/openapi.json](api/openapi.json) |
| Chatbot answer model | OpenAI `gpt-6-luna` by default; `llama3.1:8b` through Ollama when `CHATBOT_BACKEND=ollama` (no key needed) | [config/chatbot.yaml](../config/chatbot.yaml) |
| Question classifier | `llama3.1:8b`, local, on every turn | the same |
| Text a hosted model may receive | news, earnings-report, CNA and broker research sentences, the question and the tools' figures; never Reddit text, nor text from a source not listed | `hosted_model` in [config/sources.yaml](../config/sources.yaml) |
| Data updates | the dashboard's Data Management page runs the pipeline (import, prepare, aspects, sentiment, index) through the API's `/pipeline` endpoints; the same steps run by hand from the RUNBOOK | [manual-pipeline.md](manual-pipeline.md), [pipeline/runner.py](../pipeline/runner.py) |
| Evidence search | within a topic: the question's words, then the newest; with no topic: `all-MiniLM-L6-v2` vectors | [chatbot/retrieval.py](../chatbot/retrieval.py) |
| Gold set, 32 questions, `gpt-6-luna`, the final code | right tool 24/24 (23/24 in two earlier runs); advice declined and missing data admitted 8/8; a figure no tool returned in 3 first drafts and 0 answers shown; conversation turns 9/9; median 5.9 seconds an answer | [evidence/chatbot-fixes-2026-10-24.md](evidence/chatbot-fixes-2026-10-24.md), "A run on the final code" |
| Gold set, 32 questions, `llama3.1:8b`, after the description fixes (before CNA and broker research were cleared for hosted models, which does not affect a local model) | right tool 24/24; 8/8; 1 first draft and 0 answers shown with a figure no tool returned; conversation turns 9/9 | the same, first table |
| Seven questions a person rated unfaithful, asked three times each | right in 21 of 21 tries on `gpt-6-luna`, 16 of 21 on `llama3.1:8b`, as read by the AI assistant, not rated by a person; the seven are the questions the fixes targeted, so this is not a held-out result | the same, "Result" |
| Human rating | one person rated 32 answers by `llama3.1:8b` on the re-scored database, before the description fixes: 7 of the 26 the model wrote were unfaithful to the tool data, and the checks flagged none | [evidence/human-ratings-2026-10-24.md](evidence/human-ratings-2026-10-24.md) |

An answer is checked before it is shown: a draft with a figure no tool
returned, or a quote no search returned, is rewritten, then trimmed. The
checks cannot judge paraphrase or relevance; a person rated those
([evidence/human-ratings-2026-10-24.md](evidence/human-ratings-2026-10-24.md)).

### Sharing

| Item | Where |
|---|---|
| Dataset | `data/data.zip`, built by [scripts/share_bundle.sh](../scripts/share_bundle.sh); not in git |
| Model weights | Hugging Face `plp-bank-sentiment/plp-finbert-absa` (public) |
| Setup | Docker (`compose.yaml`) or natively; see the [README](../README.md) |
