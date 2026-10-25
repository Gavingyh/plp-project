# Updates for the Word report (plp-final-report.docx)

For the team member editing the master report on SharePoint. Each block below
replaces the named paragraph or table. Every figure comes from the evidence
note named under it. Section numbers and headings are the Word report's.

Net change: about 322 words longer across sections 2.3, 3.7, 4.5 and 5 (1,538
words in place of 1,216), mostly the search-model finding and the fixes. If the
20-page limit is tight, cut first the two sentences on recall and Hit@5 in
"Evidence search" (about 60 words). Not counted: the team boxes and this
file's notes to the team.

---

## 2.3, the paragraph

Replace "The database is distributed as a dated snapshot with a SHA-2…" with:

> The dataset is one file, data.zip, supplied with the project and kept out of the public repository because it holds CNA articles and Reddit posts. It holds the database every figure here was computed from (a dated snapshot), the sentence vectors, the CNA cache and the aspect model's answers. Setup restores it only if the database passes an integrity check, holds the served model's scores and matches the vectors, and checks the three fine-tuned models it downloads against their SHA-256. Every figure in this report comes from a file under docs/evidence/ that names the command that produced it, and a fresh clone installed from the README served the stored index.

Notes for the team (not report text):
- Source: the README ("Run with Docker", "Getting the database"), `docker/bootstrap.py`, `scripts/share_bundle.sh`; the restore was checked on 25 Oct with the setup's own validator (45,844 sentences, 45,844 vectors, six files restored).
- 110 words in place of 59.

## 3.7, first paragraph

Replace "The chatbot answers questions about the three banks … Three layers of code sit around the model." with:

> The chatbot answers questions about the three banks from the index and the stored sentences, and is built so that it cannot quietly make things up. A language model chooses among six tools: a bank's sentiment, a comparison of the three, a trend, data coverage, a search for evidence sentences, and analyst consensus. By default that model is OpenAI's gpt-6-luna. A local model, llama3.1:8b, answers instead when chosen, needs no key or payment, and sorts every question by intent whichever model answers. A hosted model never receives the text of Reddit posts, which members of the public wrote and whose platform restricts passing them on: it sees that such a sentence exists, with its bank, date and sentiment, but cannot quote it. Three layers of code sit around the model.

## 3.7, the paragraph after the numbered list

Replace "Since 18 October these checks run before the answer is returned … Section 4.5 reports results measured before this change." with:

> These checks run before the answer is returned: a draft that fails is rewritten once with the problem named to the model, then cut to the sentences that pass, then withheld, and the reader sees no warning. Two further checks flag a score described in words that no tool returned and a year that no tool returned. Because checks on numbers cannot see what the model says about a correct number, the tools also hand the model the facts it most often misdescribed as finished sentences to copy: the date the data runs to, a bank's rank, the topics lifting and dragging it, and, in a trend, that a recent period holds too few sentences for a figure. Every score and search result states the period it covers, the search takes a 7-day, 30-day or all-time window, and a line under each answer names the days searched. The evidence search keeps the sentences stored under the topic asked about and ranks them by the question's own words, then newest first; for a question that names no topic it ranks by similarity of vectors from all-MiniLM-L6-v2, a small model trained to match sentences by meaning.

## 4.5, first paragraph and Table 8

Replace the paragraph "On the submitted database the chatbot chooses the right tool …" and Table 8 with:

> On the submitted database, with either model, the chatbot chooses the right tool, declines advice, admits missing data and shows the reader no invented citation (Table 8). Both models pass these checks, because the code enforces them whichever model answers; they differ in how they describe correct figures (21 of 21 tries right against 16 of 21, below) and in speed (a median of 6 seconds an answer against 43). The 32 questions were also used while the prompt and checks were improved, so these are not held-out results.

| Check | Local model, before the fixes below | Local model, after | gpt-6-luna, after |
|---|---:|---:|---:|
| Right tool chosen | 24 / 24 | 24 / 24 | 24 / 24 |
| Advice declined, missing data admitted | 8 / 8 | 8 / 8 | 8 / 8 |
| Invented citations the reader sees | 0 / 32 | 0 / 32 | 0 / 32 |
| Answers with a figure no tool returned, in the model's first draft | 2 / 32 | 1 / 32 | 3 / 32 |
| The same, in the answer shown | 0 / 32 | 0 / 32 | 0 / 32 |
| Conversation turns correct | | 9 / 9 | 9 / 9 |
| The seven questions a person rated unfaithful, three tries each: tries right | | 16 / 21 | 21 / 21 |
| Median seconds per answer | 43 | 78 | 6 |

> Table 8. The chatbot on a 32-question gold set over the submitted database. A draft that fails a check is rewritten before it is shown, so the first draft and the answer shown are counted separately. Before the quote check, an earlier version cited evidence no search returned in 11 of 32 answers.

Notes for the team (not report text):
- Source: `docs/evidence/chatbot-fixes-2026-10-24.md`.
- The gpt-6-luna column is the run of 25 Oct on the final code (`data/eval/chatbot_eval_summary_luna_shown_v2.md`, `chatbot_multiturn_summary_luna_shown_mt.md`), which recorded both figure rows as it ran; the three-try row is from 24 Oct. Median 5.9 seconds, run natively; the Docker run took 18, because its question sorter runs on the processor.
- The advice row is the evaluation's own count. Its refusal check first scored two of gpt-6-luna's correct refusals as misses (6 / 8), because it didn't know their wording; it was fixed and every run rechecked on 25 Oct, so no note is needed.
- The two figure rows come from the evaluation's summaries (`data/eval/chatbot_eval_summary_merged_v2.md`, `_fixes_v2.md`, `_luna_fixes_v2.md`). The evaluation used to record only the first draft; the answers shown were checked again on 25 Oct with `python -m chatbot.run_eval --recheck --tag <tag>`, which asks no model. Every flagged first draft (+0.43; 26 and 25; 2023; the 24 of "24 September 2026") was rewritten before it was shown.
- If you keep the older Llama columns (1 Oct to 14 Oct) in a version of this table, their single figure row is both counts: those runs predate the rewrite step, so the first draft was the answer shown.
- The 78 seconds was measured while other jobs shared the laptop's processor, so it can't be compared with the 43. Either drop that cell or keep this caveat.

## 4.5, "What the checks cannot see" and "What a person found"

Replace both paragraphs, and the paragraph after them ("The automated checks flagged none of these seven …"), with:

> **What the checks cannot see.** The checks verify quotes and numbers, not what the model says about a number. One team member rated the local model's 32 answers, before the fixes below, reading each beside the tool results it was built from. Of the 24 answers that report data, 11 (46%) were fully supported and 7 (29%) contained a contradicted fact, and the automated checks flagged none of the 7. Every number in them was one a tool returned; what was wrong was the description. Three gave the data's end date as September 2023 where the tool returned 25 September 2026, two presented another period as the one asked for, one ranked OCBC third where the tool ranked it second, and one named the wrong strongest and weakest topics. The rater knew the system and was the only rater, so there is no agreement figure.
>
> **Fixing the descriptions in code.** The seven faults share a cause: the model was left to work out a date, a rank or a list from raw fields. The tools now give each as a finished sentence, a trend says when a recent period holds too few sentences, and a check flags any year no tool returned. Each of the seven questions was then asked three times. The wrong years, ranks and topics did not recur with either model. The local model still failed 5 of 21 tries, mostly on one kind of question: asked about a topic over the last 7 days when that week holds too few sentences, it fetched the bank's overall score and presented it as the topic's, in two of three tries. gpt-6-luna said there was not enough data in all six such tries. Copying fixed what the model had to copy; what remains is the model's choice of what to fetch, which the larger model makes better. That, with a median answer of 7 seconds against 43, is why gpt-6-luna is the default and the local model is the option that needs no key or payment. Two cautions: the three-try results were read by the AI assistant, not rated by a person, and the seven questions are the ones the fixes target.

Notes for the team:
- Sources: `docs/evidence/human-ratings-2026-10-24.md` and `chatbot-fixes-2026-10-24.md`.
- The Word report counts 24 data-reporting answers. The ratings note counts the 26 the model wrote, two of which are no-coverage replies. Both are right; the text above keeps the report's 24.

## 4.5, "Evidence search" and the paragraph after it

Replace "**Evidence search.** One aspect per sentence made the search …" and "Two further measures agree …" with:

> **Evidence search.** When the chatbot quotes what people say about a bank's topic, the search keeps the sentences stored under that topic and ranks them. The measure is how many of the top five people labelled with the topic asked about (precision at 5, over 28 questions and the 1,277 labelled sentences). The stored aspect does most of the work: 74% of the sentences stored under a topic are on it, so the search as a whole scores 0.82 against 0.10 for five sentences drawn at random from the bank (95% interval for the gain 0.62 to 0.81). Within the topic, ranking by FinBERT similarity made it worse than a random draw (0.70 by the aspect's name, 0.65 by the question, against 0.74). That fits the weakness described in section 4.2: FinBERT's vectors match a sentence's register more than its topic. The search therefore ranks within a topic by the question's own words, then newest first, which scores 0.82. Its gain over a random draw is small (0.08, interval 0.01 to 0.15) and optimistic, since the ordering was chosen on these same questions. Recall at 5 tells the same story: 0.45 against 0.40 for random, below random in 7 of 28 questions, where FinBERT's ordering was below in 13. Hit@5 cannot separate the two, since inside the filter almost any five sentences include a relevant one (0.996 for random order).
>
> **A model built for search.** FinBERT was trained to classify sentiment, not to match sentences by meaning. Three small models trained for matching (all-MiniLM-L6-v2, bge-small-en-v1.5 and bge-base-en-v1.5) were scored against a rule set beforehand. None beat the word ordering within a topic (best 0.80, where 0.85 was required). For a question that names no topic, where FinBERT ranked no better than chance (0.12 against 0.10), all three ranked about two and a half times better (0.29 to 0.31). The search now uses all-MiniLM-L6-v2 for such questions (0.31 over the full corpus), the smallest and fastest of the three, at tens of milliseconds a question on a laptop. The failure therefore lay in FinBERT's vectors, not in ranking by vectors as such; and once the corpus is sorted by topic, plain word matching is the better ranking. The measures rest on 28 questions, and relevance is judged by labels made under the older reading of wealth, so a sentence the later ruling moved counts as a miss.

Notes for the team:
- Source: `docs/evidence/search-models-2026-10-24.md`.
- The old 0.66 and 0.62 were understated: the measure divided by five even when a topic held fewer than five sentences (3 of 28 questions). Corrected, they are 0.70 and 0.65; the comparison with six aspects a sentence is now 0.33 against 0.70.
- `chatbot/retrieval_eval_with_recall.py` has the same division on its precision lines. Its recall figures are unaffected.

## 4.5, the team box "FOR THE TEAM TO DO BEFORE 25 OCTOBER"

In item (3), replace "A rerun of the gold set, the scripted dialogues and the ratings on the chatbot as changed on 18 October" with:

> Done for the gold set: the local model and gpt-6-luna after the fixes (Table 8). Still to do: the scripted dialogues, and a person's check of the three-try answers.

## 5, "General-purpose embeddings failed twice …"

Replace the paragraph with:

> **FinBERT's embeddings failed twice; a language model fixed the first and a model built for search the second.** Similarity between FinBERT embeddings was barely better than a constant guess at assigning aspects (41% against 37%), and no better than random at ranking evidence for a question. The embeddings encode how a sentence is written more than what it is about. Replacing similarity with a local model's reading of the sentence raised aspect agreement to 73%. Used as a filter, its stored aspect also doubled evidence precision, from 0.33 to 0.70. Within the filtered pool, plain word matching ranks best, and for questions that name no topic a small model trained to match sentences ranks two and a half times better than FinBERT did.

## 5, "A language model in a product needs checks …"

Replace its last sentence, "The automated results are therefore a floor for trust, and the changes of 18 October aimed at these faults still have to be measured.", with:

> Giving the model those facts as finished sentences removed the date, rank and topic errors with both models; what remains, with the local model, is choosing which figure to fetch. The automated results are therefore a floor for trust, not a measure of it.

## 8, Table 9 (where generative AI was used)

- Row "Component of the system": add "OpenAI gpt-6-luna, the chatbot's default answer model (never sent Reddit text)" to the tools.
- Row "Alternative chatbot backends": Gemini has been removed from the code, and the product's default is now gpt-6-luna. Reword it to say that Gemini and Groq were tried, and that the product uses gpt-6-luna with the local model as the no-key option.
- Row "Evaluation scoring": add "read the 42 three-try chatbot answers (21 per model) against the tool results".
- Not generative, so not in Table 9: all-MiniLM-L6-v2. If the references list models, add it with Reimers and Gurevych (2019), Sentence-BERT.

## Open items box at the top

Replace "The human evaluation is half done: a second rater, the user study, and a rerun of the chatbot results on the 18 October version (section 4.5)." with:

> The human evaluation is half done: a second rater, the user study, and a person's check of the three-try answers (section 4.5).

Delete "Which dataset is submitted: the snapshot holds text that must stay within the team (section 2.1)." It is settled: the dataset is `data.zip`, given to the assessors with the project (section 2.3).
