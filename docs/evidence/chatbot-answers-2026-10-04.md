# The chatbot's answers for a retail investor: before and after, 4 Oct 2026

On 4 Oct the project owner tried the chatbot in the dashboard and found the
answers hard to read and of no help to a retail investor. This page records
what was wrong, what was changed (DESIGN decision 25, branch
`fix/chatbot-answers`) and how the change was measured, including the
rounds that made things worse before they got better.

All runs: `llama3.1:8b` through Ollama on this Mac (M1, 16 GB), as both the
intent classifier and the chatbot model, with the default settings (strip
enforcement, aspect query), at temperature 0.2, one run per configuration.

## Before: seven questions in the dashboard

Asked on the Ask page, on `main`, early in the afternoon of 4 Oct. The
answers and times were read off the page in a browser and not saved to a
file; times are from sending the question to the answer appearing, and two
were not timed. The figures match the database, and the same questions put
through `main`'s code later gave the same kind of answer: "0.122 out of 1",
"No specific quotes or articles were found", UOB's dividend score called
"slightly negative", and for the trend "there isn't enough recent data".

| question | time | what came back |
|---|---|---|
| What is the overall sentiment on DBS? | 16 s | right figures (+0.122, 24,431 sentences), as "0.122 out of 1", under four labelled sections, with "No specific quotes or articles were found" |
| And OCBC? | 28 s | the same shape; the follow-up resolved |
| Compare DBS, OCBC and UOB on dividends. | not timed | right scores, but UOB's +0.1242 called "slightly negative" |
| Has sentiment on UOB's net interest margin changed recently? | not timed | "the trend is not available due to insufficient recent data", though 66 months had enough sentences to score (of 72 months with any) |
| Show me evidence about OCBC's asset quality. | about 100 s | results-report boilerplate (segment descriptions, table notes), cited by 24-character ids |
| What do analysts think of UOB? | about 40 s | useful figures (hold, 16 analysts, $43.30 target) under the same headings, with a filler caveat |
| Should I buy DBS shares now? | 3 s | the fixed reply, which reads well |

The causes, in the code:

- The prompt asked for "direct answer first, then supporting evidence with
  citations, then the sample size and time window, then any caveats"; the
  model turned it into four headings, and a separate rule made it write
  that no quotes were found whenever it hadn't searched.
- The tools returned bare scores and counts. Nothing told the model the
  scale, so it read the numbers itself, and once read a positive score as
  negative.
- `get_trend` sent the monthly series only when the 7- and 30-day windows
  (counted back from when the index was last built, 30 Sep) both had enough
  sentences. The 7-day window had fewer than 5 for 13 of the 33 bank-topic
  pairs (10 of the 30 named topics), UOB's net interest margin (3) among
  them, and those questions got the all-time score alone.
- Evidence search ranked results-report prose highest, and the same report
  sentence appeared once a quarter with only the quarter changed.

## What changed

DESIGN decision 25 has the full list. In short: a guide to writing for a
retail investor replaces the fixed format; the chatbot's own versions of
the tools add each score's reading in words, the shares of positive and
negative sentences, where a bank ranks among the three, its strongest and
weakest topics, one sentence stating a trend, and the date the data runs
to; evidence skips repeated wordings and takes at most two results from one
source; the reader sees numbered citations with a source list; and the
model is given fewer fields (no separate id field or raw counts, though an
id still travels inside the citation it copies). The API's results are
unchanged.

## How it was measured

The 32-question gold set and the four multi-turn conversations, with the
evaluation's own checks:

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --set v2 --tag <tag>
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --multi-turn --tag <tag>
```

Tags: `defaults_v2` (before, on `main`), then `reader_v2`, `reader2_v2`,
`reader3_v2`, `final_v2`, `final2_v2` (trimmed) and `mix_v2` (kept) on the
branch, and `*_mt` for their conversations. Per-question times came from wrapping `answer_turn` with a
timer in a script outside the repository; the evaluation itself doesn't
time answers. Readability was counted over the answers the model wrote
itself (not the six fixed replies), with the harness's notes, warnings and
source list cut off:

```python
LABEL = re.compile(r"^\W*(supporting evidence|sample size|time window|caveats?|sources?)\b[^\n]{0,40}:",
                   re.IGNORECASE | re.MULTILINE)
FILLER = re.compile(r"no (specific )?(quotes|articles|evidence)[^.]{0,40}(were|was) found", re.IGNORECASE)
SCORE = re.compile(r"[-+−]?0\.\d{2,}")
# labelled sections: LABEL found; "out of 1": the phrase; raw id: [0-9a-f]{24} in the shown answer;
# score with its scale: SCORE found and "scale", "-1" or "−1" in the same answer; share: a "%".
```

## Results

Seven runs of the 32 questions, in order. "Mix" is the version kept on the
branch.

| | before | round 1 | round 2 | round 3 | final | trimmed | mix |
|---|---|---|---|---|---|---|---|
| right tool (of 24) | 22 | 22 | 18 | 23 | 23 | 20 | 23 |
| behaviour (of 8) | 8 | 7 | 8 | 8 | 8 | 8 | 7 |
| answers citing evidence no search returned | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| answers with a figure no tool returned (flagged) | 0 | 4 | 1 | 1 | 2 | 1 | 1 |
| evidence written without a search, removed | 9 | 3 | 4 | 5 | 7 | 9 | 6 |
| backend errors | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| conversation turns right (of 9) | not run | 9 | 9 | 8 | 9 | 9 | 9 |

Readability, over the answers the model wrote (26 in each run; 25 in the
trimmed run, where one question timed out):

| | before | round 1 | round 2 | round 3 | final | trimmed | mix |
|---|---|---|---|---|---|---|---|
| with labelled sections | 23 | 0 | 0 | 0 | 0 | 1 | 0 |
| "out of 1" | 6 | 1 | 0 | 3 | 2 | 2 | 2 |
| "no quotes were found" | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| raw sentence id shown | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| score given with its scale | 0 of 17 | 13 of 16 | 11 of 13 | 17 of 18 | 11 of 17 | 8 of 17 | 13 of 19 |
| a share in % | 5 | 19 | 15 | 19 | 20 | 11 | 13 |
| words, median | 72 | 65 | 70 | 62 | 68 | 71 | 64 |
| seconds per answer, median | not timed | 27 | 66 | 60 | 68 | 41 | 61 |
| minutes for the 32 questions | 16 | 14 | 29 | 27 | 28 | 22 | 27 |

What the kept version does better than before: no labelled sections, no
"out of 1", no filler, no raw ids, and most scores read with their scale and
shares; tool choice and grounding are no worse (citations 0, conversations
9 of 9). What it does worse: it is slower, and the model still works out a
figure of its own now and then, which the figure check flags; the
behaviour miss is the Standard Chartered question, which the intent
classifier lets through and the model answered with talk of data rather
than "I only have data on DBS, OCBC and UOB".

## What each round found

Each round was one run of the same 32 questions; what it showed was fixed
before the next.

1. **Round 1** (the first version). Readability changed at once: no
   labelled sections, shares in 19 answers. But four answers carried a
   figure no tool returned. Two were invented: asked about DBS's capital,
   the model called only `get_coverage` and gave shares it never fetched,
   and asked for evidence on OCBC's wealth business it searched and then
   made up a score and shares; the writing guide had pushed it to give
   them. One was a sign error on a monthly score (August's +0.2185 written
   as "-0.2185"). One was a false alarm: "September 25th" was read as a
   figure, because the check skipped dates only with their year.
2. **Round 2.** The right tool fell to 18 of 24. Told to filter evidence by
   sentiment for complaints, the model treated "how do people feel about"
   and "how is it being discussed" as evidence questions, searched only
   negative (or positive) sentences, and judged the overall mood from them
   ("The market has expressed negative sentiment towards DBS's management
   guidance"). The trend tool also gave two comparisons at once (the last
   week rising, the last month falling) and the model blended them.
3. **Round 3.** The right tool back to 23 of 24, and 17 of 18 scores with
   their scale. The seven dashboard questions, asked in the browser at this
   point, showed what the checks can't see: asked about DBS alone, the model
   said DBS ranked above OCBC, and asked about OCBC, that OCBC ranked below
   both; OCBC is the highest. Those answers were not saved, and the browser
   test turned out to be running the round-1 code the dashboard had loaded
   when the Ask page was first opened. With each bank's score now carrying
   the other two, the seven questions were asked again in Python (the
   rankings right, though one aside in the OCBC answer called DBS's +0.12
   "slightly more positive" than OCBC's +0.14), and a reading the model put in quote marks was removed
   as an invented quote, leaving "with a reading of." in the answer.
4. **Final.** One bank's score now came with the other two and the
   ranking, and a quoted reading or topic name was not taken for evidence.
   Every check held; the two flagged figures were the model's own errors
   (5,232 sentences written as "2,232", and "over 20,000 sentences for each
   bank" when OCBC has 6,379). But answers took a median of 68 seconds.
   Ollama's own timings on three questions, against `main`, showed why
   once the branch's prompt was cached: the tool results the model reads
   are longer (see Speed).
5. **Trimmed.** The model was given fewer fields (no links, no separate id
   field, no raw counts; six months of history instead of twelve) and a prompt a quarter
   shorter asking for 50 to 100 words. The median fell to 41 seconds, but
   the right tool fell to 20 of 24 (one a time-out) and scores with their
   scale to 8 of 17; in the dashboard questions the model reused topic
   scores from earlier answers without fetching them and worked out its own
   month-on-month change ("a 44% increase in positive sentiment"), all
   flagged.
6. **Mix, kept.** The project owner chose the fuller writing guide of the
   final round with the trimmed fields: median 61 seconds, right tool 23 of
   24, scale with 13 of 19 scores, one flagged figure.

   After this run the full test suite showed the trimmed fields had opened a
   privacy gap: the hosted backends' filter recognises a Reddit post that came
   through a news feed only by its reddit.com link, and with links hidden
   such text reached Gemini in `tests/test_validate_gemini_reddit_privacy.py`.
   Links went back into what the model reads; nothing was sent to a hosted
   model in practice, since every run here used the local one. So the kept
   version shows each evidence result's link again, which the mix run didn't:
   its evidence answers read a little more than measured.

## After validation

Four validations of the branch (`docs/validation/2026-10-04-chatbot-answers*.md`)
each found gaps the change had opened in the checks, or old ones it had not
closed. The checks as they stand after the fourth:

- **Quotes** are found by pairing each paragraph's quote marks in order,
  first with second and third with fourth, as a reader pairs them, whatever
  stands around them: '"..."(Reddit)', a table cell '|"..."|', a space inside
  the marks, mixed straight and curly marks, « ». A pair around fewer than ten
  characters ('"buy"') is a word in quote marks, not a quote. A mark left
  without a partner opens a quote that runs to the end of its line, stopping
  before a citation. Single quotes are left out, as they are mostly
  apostrophes.
- **Numbered markers** the model writes ("[2]", "[2, 3]", "[12-45]") are
  dropped only after the checks have read the model's own text and removed
  any unretrieved quote or link; the figures of a dropped marker are still
  checked, and "[0, 1]" is left as written. At display, a marker inside a
  quote stays only if the quoted sentence has it (one stored sentence has a
  "[1]" footnote). Through the API, history drops the markers and the list
  of sources the reader saw.
- **A date without its year** is skipped by the figure check only when a
  tool's date field (`data_runs_to`, an evidence item's date) has that month
  and day, and a day followed by a decimal, a thousands group or "%" is
  never a date. A date in the model's own search query, a link or a quoted
  sentence vouches for nothing, and "may" in lower case is the verb.
- **Tool wording**: a reading or a real topic name in quote marks is not a
  quote; a topic name the model set by passing its own text as the aspect is
  not exempt.
- **The trend sentence** says it's too close to call when the printed scores
  point another way from the change before shrinkage, and the model is then
  not given that change.

What each validation found, in short:

1. The first: the first date pattern hid figures ("0.45 may"); a topic name
   the model chose let it quote its own text; markers and sources went back
   to the model through the API's history; the trend sentence could
   contradict its figures.
2. The second: flagging any bare marker flagged real quotes, and in strip
   mode an invented quote beside a "[2]" survived; more date edges.
3. The third: the patched date patterns read counts as dates ("July 18" on
   one line, "21 Oct tweets"), which `main` had checked, and dropping a marker
   before the checks could leave '"..."-', which no longer read as a quote.
   Dates were then grounded in tool results and the checks moved before the
   marker drop.
4. The fourth: the grounded date rule let a returned date swallow a figure
   ("September 25.7%" when data ran to 25 September), and dates in the
   model's own search query counted; and quotes in shapes the pattern never
   matched ('"..."(Reddit)', table cells), also unchecked on `main`. The
   pairing of quote marks replaced the pattern.

Each finding has a test in `tests/test_validate_chatbot_*.py`, none of them
now marked as expected to fail. Re-run over the recorded answers of all
seven runs, the figure and citation checks flag exactly what they flagged
before, except round 1's false alarm on "September 25th", cleared because a
tool had returned that date; so the tables above stand.

## The seven questions again, after

The kept version, asked in one conversation through the `Conversation` the
Ask page uses, at about 18:00:

| question | time | what came back |
|---|---|---|
| What is the overall sentiment on DBS? | 60 s | "slightly positive, with a score of +0.12 on a scale from -1 (all negative) to +1 (all positive)", 22.4% positive and 10.3% negative of 24,431 sentences, second of the three banks behind OCBC, the topics lifting and dragging it, the date the data runs to |
| And OCBC? | 66 s | the same shape, OCBC first of the three; one wrong aside ("There isn't enough data on UOB") |
| Compare DBS, OCBC and UOB on dividends. | 72 s | right scores, readings, shares and ranking; no scale |
| Has sentiment on UOB's net interest margin changed recently? | 65 s | August +0.38, September +0.55, up; it added a change of its own (+0.17), flagged by the figure check (the tool's, before shrinkage, is 0.158) |
| Show me evidence about OCBC's asset quality. | 82 s | a relevant line from OCBC's results report, quoted word for word and named as such ("Asset quality resilient, NPL ratio steady at 0.9%"); no numbered citation, as the model didn't copy the citation |
| What do analysts think of UOB? | 57 s | hold from 16 analysts, a $43.30 target, about 1.9% upside, the data's date |
| Should I buy DBS shares now? | 3 s | the fixed reply |

## Speed

Answers are slower than before on this Mac: the kept version's median is
61 seconds per answer, and 57 to 82 seconds in the seven dashboard
questions. Before, the 32 questions took 16 minutes, about 35 seconds for
each answer the model wrote.

Ollama's own timings, on three questions asked through `main` and through
the final round's version (the fuller prompt, every field), show what the
change costs once its prompt is cached: reading the tool's result before
answering took about 3.5 to 8.5 seconds on `main` and 6 to 17 on the
branch, because the results are longer. The answers were not longer: the
branch's were shorter on two of the three questions (205 against 387 tokens,
74 against 99), and answers were written at about 5 to 11 tokens a second
across that day's runs. Asked alternately, the
per-question times were 20 against 46 seconds (DBS overall), 34 against 63
(a trend) and 82 against 84 (a comparison, where `main`'s answer ran to 387
tokens). Much of those gaps was the branch re-reading its whole prompt on
every first call, 14 to 26 seconds more than `main` each time (55% of the
first gap, 87% of the second, and more than all of the third). Why
`main`'s prompt was read from Ollama's cache in that run and the branch's
was not isn't known: with one slot, alternating should have evicted both.
So the slowdown has two measured parts, reading the longer tool results
(2.5 to 12 seconds more per answer in that run) and, whenever the prompt
isn't cached, reading the longer prompt again (14 to 26 seconds); these
runs don't split the 26-second gap between the medians before and after
between them. The block run and the window run below used the trimmed version (shorter prompt,
fewer fields), started at 16:33: asked as a block, it re-read its prompt
only for the first question (37.9 seconds, then 0.6 and 0.5).

The mix run's median, 61 seconds, against the final run's 68, can't be put
down to the fields left out: it is one run each, within the load noise
below, and the committed version (links back in) was not timed. A shorter
prompt (the trimmed run) gave 41 seconds, with less complete answers.
Ollama ran one slot with a 4,096-token window (`-c 4096 -np 1` on the
runner's command line, read with `ps` on 4 Oct and not saved); an
8,192-token window didn't make it faster: all three questions were slower
than in the block run.

Run times move with the Mac's load (the same first question took between 32
and 108 seconds across the rounds), so the minutes in the table are a guide,
not a measurement of the change alone.

## Caveats

- One run per configuration at temperature 0.2: a difference of one or two
  questions is not evidence of a change.
- The prompt was revised after each round's results on these same 32
  questions, so the later rounds are partly tuned to them. New questions,
  written apart from the prompt, would measure it fairly.
- The figure check can't see a wrong comparison written in words ("ranks
  above OCBC"); the invented rankings were found by reading the answers.
- Evidence is still ranked by FinBERT embeddings, which favour report
  prose; it is better, not good.
- The dashboard keeps the chatbot code it first loaded: after a change to
  `chatbot/`, restart it (`scripts/stop.sh dashboard`, then
  `scripts/start.sh dashboard`). The final seven questions were asked
  through the same `Conversation` the Ask page uses, in Python, because the
  Chrome tab used for the test stopped responding while in the background.
- Results files that contain CNA text are kept out of git, under the rule
  that CNA text stays within the team: the 32-question results of round 1,
  round 2, round 3, final and mix
  (`data/eval/chatbot_eval_results_{reader,reader2,reader3,final,mix}_v2.jsonl`).
  Their summaries are committed, as are the results of the before and
  trimmed runs and of every conversation run, which hold no CNA text.
