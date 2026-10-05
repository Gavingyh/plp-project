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
to, and a search for a bank also returns that bank's score (for the topic
searched, or overall, named as such) with that date; evidence skips repeated wordings and takes at most two results from one
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
   Ollama's own timings on three questions, against `main`, measured two
   parts (see Speed): reading the longer tool results, 2.5 to 12 seconds
   more per answer, and, whenever the prompt wasn't cached, reading the
   longer prompt again, 14 to 26 seconds.
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

Eight validations of the branch (`docs/validation/2026-10-04-chatbot-answers*.md`
and `docs/validation/2026-10-05-chatbot-answers-*-check.md`) each found gaps
the change had opened in the checks, or old ones it had not closed. The
checks as they stand after the eighth:

- **Quotes** are found by two detectors together, as each catches shapes the
  other misses. A pattern first finds a quote in curly or angle marks by its
  own marks. A straight mark, or a closing mark used to open a quote (»...«,
  ”...”), can also stand elsewhere, so for those the pattern looks at what
  stands next to the marks: such a quote opens only where no letter or digit
  stands before its mark, and closes only where none follows. So an inch
  mark ('a 6" phone') opens nothing and a stray or missing mark never moves
  the quotes after it, while a bracket, a table bar or other punctuation
  beside the marks ('"..."(Reddit)', '|”...”|') hides nothing. A quote holds
  no other double quote mark, except that a straight quote may hold whole
  curly quotes and a curly quote whole straight ones; such a quote ('“I
  asked them "..." and they said ...”') is checked whole. A quote closed
  with a curly or angle mark may hold an inch mark ('“my 6" phone ...”'); in
  one closed with a straight mark, an inch mark after its first ten
  characters reads as the close. Then, in the text between the pattern's
  quotes, each paragraph's marks are paired in order, as a reader pairs
  them, whatever stands around them: a space inside the marks, a letter
  against one. A mark opens a quote only where it reads as an opening one: a
  low-9 mark („...“) like “, a closing mark (” or ») only before a letter or
  digit ('»...»'), and an opening mark typed to close ('...for sure“ ok')
  not at all. A pair around fewer than ten characters with no space just
  inside either mark ('"buy"', '"Tier 1"') is a word in quote marks, not a
  quote, whatever follows its closing mark ('"DBS"and', '"buy-now"s'); only
  where a citation, or a mark that reads as a closing one (no letter or
  digit right after it, an inch mark too), follows ten or more characters
  on does that closing mark open a quote ('"x"OCBC will cut ... for sure"').
  A mark left without a partner opens a quote that runs to the end of its
  line, or to the next quote, stopping before a citation. The words right
  after a quote's closing mark that has a letter from A to Z or a digit
  right after it ('... Another wrote ”OCBC will ...') may be a quote, as that
  mark may be the next quote's opening one: they are checked after a quote
  no search returned, or one too short to check, and wherever a citation or
  a mark that reads as a closing one ends them; after a quote a search
  returned they are otherwise the model's own words ('One user: “...”DBS
  also scored 0.31.'). Last, a passage in single marks (' ‘ ’) counts from
  six words, or from three after a verb of saying among the three words
  before it ("said", "say", "says", "wrote", "write", "writes",
  "complained", "complain", "complains", "posted", "commented", "tweeted",
  "replied", "added", "asked", "claimed", "stated", "quoted", or "put it",
  "call it", "calls it", "called it"), after a speaker and a colon ("One
  user: '...'", "Another: '...'"), or before a citation or a source tag
  ("(Reddit)"). A noun ("report", "note", "post") or a label's colon
  ("Note: '...'") cues none, and other short ones are terms or scare quotes
  ('customer first digital approach'). An apostrophe inside a word
  ("OCBC's") neither opens nor closes one, and a passage in single marks
  holding a quote in double marks is checked whole.
- **A quote mark the checks can't place**, a double mark that is not a mark
  of a quote found, not inside one, not around a word in quote marks, not an
  inch mark, not a stray straight mark after a space before a few words at
  the end of a paragraph, and not a stray mark at the end of its line right
  after a quote's closing mark or a citation right after one ('"..."
  [DBS, ...]."', '"...""'), may belong to a quote the detectors missed. It
  flags the answer in every mode, and strip mode removes its line, with the
  line's citation.
- **Strip mode** after a search removes each line holding such a mark, read
  before anything else is removed, then each quote, link and sentence id no
  search returned, and the words between two removed quotes on one line when
  no kept quote stands between them. Words glued to a closing mark that read
  as a quote where the model wrote them go too, though the line of a mark
  that may close them went first. It runs again on its result until
  nothing changes, at most ten times, and whatever is left is flagged.
  Without a search, a line holding such a mark goes like a line holding a
  quote, in the first paragraph too.
- **A quote is compared** with what the searches returned piece by piece, cut
  at an ellipsis, each piece of three or more words without the punctuation
  and spaces at its ends, so a sentence quoted with a comma inside the
  closing mark ('"...night,"') is the sentence returned.
- **Numbered markers** the model writes ("[2]", "[2, 3]", "[12-45]") are
  dropped only after the checks have read the model's own text and removed
  any unretrieved quote or link; a drop that leaves a new marker ("[1[2]]"
  leaves "[1]") is repeated, the figures of every dropped marker are still
  checked, and "[0, 1]" is left as written. At display, a marker inside a
  quote stays only if the quoted sentence has it (one stored sentence has a
  "[1]" footnote). Through the API, history drops the markers and the list
  of sources the reader saw.
- **A date without its year** is skipped by the figure check only when a
  tool's date field (`data_runs_to`, an evidence item's date) has that month
  and day. After a month, such a day, ordinal or not, is a date only where it
  clearly reads as one: after "on", "as of", "as at", "the", "dated" or "runs
  to" (a range also after "from" or "between"), or before a line end,
  punctuation other than "%", a comma or an opening bracket (a dash only when
  no digit follows it), "and", "&", "to" or "/" not followed by a number, an
  article or determiner, or one of "until", "till", "through", "when",
  "while", "after", "before", "since", "during" and "as". Before a comma it
  is a date only when no number follows in the rest of its clause (to the
  next full stop, semicolon, colon, "!", "?" or line end), or just one, right
  after the comma ("September 25, 45 posts"); before an opening bracket, (
  or [, only when no number follows in the rest of its clause and no "of"
  stands inside the bracket. Anywhere else it is a figure to check: with
  data to 25 September, "In September 25 customers complained", "September
  25th sentences", "In September 25, 31 and 40 posts", "In September 25 (out
  of 40) posts" and "September 25 for DBS against 40 for UOB" are counts to
  check, and "Data runs to September 25 for DBS" a date. A share after the
  day ("25 per cent", "25 to 30% of posts") means both numbers are checked,
  and so are both ends of a range not read as a date. A day followed by a
  decimal, a thousands group or "%" is never a date. A date in the model's
  own search query, a link or a quoted sentence vouches for nothing, and
  "may" in lower case is the verb.
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
5. The fifth: the pairing broke on one missing or stray mark. A quote left
   open, or an inch mark ('a 6" phone'), took the next quote's opening mark
   and hid that quote from strip mode, unflagged, where the pattern had
   caught it. Quotes in single marks or opened with a closing mark (»...«)
   were never checked; a count equal to a returned day ("In September 25
   sentences") was hidden; "[1[2]]" crashed the turn; and "Sept 25-26" and a
   neutral share the model worked out were flagged, as the evidence search
   gave no neutral share. The pattern and the pairing were combined, and the
   search now gives the neutral share.
6. The sixth (5 Oct): the fifth's change had stopped a curly quote holding a
   straight mark, so in '“I asked them "..." and they said ...”' the words
   after the inner quote went unchecked; a quote left open before a
   '"..."(Reddit)' quote kept the invented one, unflagged, and removed the
   real one (also on `main`); a scare quote in single marks ("DBS's 'customer
   first digital approach'") was removed as invented; a quote opened with a
   closing mark beside a table bar or bracket ('|”...”|') went unchecked; and
   with data to 25 September, "September 25 to 30% of posts" hid the 25 while
   "Data runs to September 25 for DBS" was flagged. It also found figures on
   this page from comparisons nobody had saved; they are gone. The fix
   (7446c89) let the pattern's straight quotes and those opened with a
   closing mark open and close beside any punctuation and straight and curly
   quotes hold each other, counted single quotes from six words, and took a
   returned day for a date unless a count or a share followed it. Checking
   it showed one more gap from the fifth's: a curly quote holding an inch
   mark ('“my 6" phone ...”') went unchecked, where `main` flagged it, so
   quotes were let hold an inch mark.
7. The seventh (5 Oct): 7446c89's date rule hid a count before any word not
   on its list ("In September 25 customers complained", "25 or so posts"),
   and an ordinal day was always a date ("September 25th sentences"); a
   curly or angle quote holding an inch mark ran on to the next quote's
   opening mark, so an invented quote after it ('“my rate went up to 5" in
   one post. Another wrote ”...”') stayed, unflagged, after strip; a
   single-quoted invented quote of five words went unchecked after "wrote";
   „...“ marks were not read, and a real quote with a comma inside its
   closing mark was removed as invented (both also on `main`); a quote
   holding two quotes of the other style was removed whole, a real one
   inside it too; and the replay comparison on this page rested on a
   snapshot kept only in a session's scratch folder. The changes are the
   rules above: a mark the checks can't place takes its line, the words
   between two removed quotes go with them, strip runs until nothing
   changes, low-9 marks are read, single quotes count from three words with
   a cue, a quote is compared without its end punctuation, a returned day is
   a date only where it reads as one, and `scripts/replay_checks.py
   --against <commit>` compares with any commit's checks. Checking these
   changes on made-up answers with several odd shapes at once found more
   ways for one quote to take another's mark: a quote's closing mark read as
   a pair with an inch mark after it, an opening mark typed to close, the
   next quote's opening mark taken as a quote's close, and a quote holding a
   real one whose closing mark, after punctuation, was read as a stray mark.
   Each is now caught; and so that real quotes in mixed marks ('»...»',
   '"...“') don't lose their line, those are read as pairs.
8. The eighth (5 Oct): 31c7e98's date rule still hid a count before a
   comma, a bracket or "for" ("In September 25, 31 and 40 posts were
   negative", "In September 25 (out of 40) posts", "September 25 for DBS
   against 40 for UOB"). Its quote rules removed correct text in four
   shapes: the model's own words glued to a real quote's closing mark ('One
   user: “...”DBS also scored 0.31.'), a word in quote marks with a letter
   right after it ('"DBS"and "OCBC" both rose.', which lost its whole line),
   a term in single marks after a noun or a label ("Users report 'long queue
   times'", "Note: 'fees are high' is the theme"), and a correct line with a
   stray mark after its quote's citation. And the replay comparison on this
   page counted five results runs kept out of git, so a checkout printed
   other lines. The changes are the rules above: a comma or a bracket after
   a returned day ends a date only with no number later in its clause (or
   one right after the comma), and "for" no longer does; a word in quote
   marks keeps both its marks whatever follows; the words glued to a quote's
   closing mark are checked after an unverified quote, or where a citation
   or a closing mark ends them; single quotes are cued by verbs of saying
   and a speaker's colon only; a stray mark at the end of its line after a
   quote or its citation is placed; and `scripts/replay_checks.py` reads
   only the results files git tracks unless asked. Checking these changes
   against 31c7e98 on generated answers, invented quotes and correct ones in
   many combined shapes, found invented quotes that 31c7e98 caught and a
   first draft of these rules missed: glued words ended by an inch mark, by a
   mark on the next line, or by a closing mark that a stray mark after a
   citation paired with. Each is now caught. The only invented quotes
   31c7e98 caught that pass now are glued words with nothing after them that
   could end a quote (Known limits), and no correct answer it kept as
   written is changed now.

Each finding has a test, in `tests/test_validate_chatbot_*.py` or, for two of
the fifth's ("Sept 25-26" read as a date, and the neutral share), in
`tests/test_chatbot_reader.py`. One, the seventh's merged nested quotes, stays
marked as expected to fail, as a recorded limit (below). The gaps found while
checking the sixth's, the seventh's and the eighth's changes are tested in
`tests/test_chatbot_harness.py` (dates in `tests/test_chatbot_reader.py`, the
replay's choice of files in `tests/test_replay_checks.py`).

`scripts/replay_checks.py` re-runs the citation check, the figure check and
strip mode over every answer recorded in the results files under
`data/eval/` that git tracks, compares each gold-set run's flags with those
recorded when it was made, and counts the answers holding a quote mark the
checks can't place. Its first line says how many results files it read and
how many of those git doesn't track. With `--against <commit>` it also
compares every answer's checks with that commit's: it extracts the commit's
files into a temporary folder and runs its code there over the same results
files, changing nothing in the repository. On 5 Oct, after the eighth
validation's fixes, `HF_HUB_OFFLINE=1 .venv-plp/bin/python3
scripts/replay_checks.py --against 31c7e98` printed:

```
Results files read: 36; not tracked by git: 0
Gold-set runs, flags now against those recorded when the run was made:
  defaults_v2: 26 answers; figure flags changed none; citation flags changed none
  reader_v2: not tracked by git, so not read (--include-untracked reads it)
  reader2_v2: not tracked by git, so not read (--include-untracked reads it)
  reader3_v2: not tracked by git, so not read (--include-untracked reads it)
  final_v2: not tracked by git, so not read (--include-untracked reads it)
  final2_v2: 25 answers; figure flags changed none; citation flags changed none
  mix_v2: not tracked by git, so not read (--include-untracked reads it)
  llama3b_v2: not compared (recorded before the model's own text was kept)
  llama3b_v2_strip: not compared (recorded before the model's own text was kept)
  llama8b_v2: not compared (recorded before the model's own text was kept)
  llama8b_v2_aspectquery: not compared (recorded before the model's own text was kept)
  llama8b_v2_idle: not compared (recorded before the model's own text was kept)
  llama8b_v2_intent: 25 answers; figure flags changed [('consensus-1', ['6%', '41%', '47%', '6%'], [])]; citation flags changed none
  llama8b_v2_intent_strip: 26 answers; figure flags changed [('consensus-1', ['6%', '41%', '47%', '6%'], [])]; citation flags changed none
  llama8b_v2_strip: not compared (recorded before the model's own text was kept)
  qwen3_4b_nothink_v2: not compared (recorded before the model's own text was kept)
Every recorded answer: 540
  holding a quote mark the checks can't place: 0
  differing from the checks of 31c7e98: 1
    llama3.2_3b_harness_t0.2/lookup-3: quotes
```

Five of the seven runs in the tables (`reader_v2`, `reader2_v2`, `reader3_v2`,
`final_v2` and `mix_v2`) are kept out of git because they quote CNA text, and
`--include-untracked` adds them on the team's machine that has them: there
the same command printed `Results files read: 41; not tracked by git: 5` and
`Every recorded answer: 670`, none holding a mark the checks can't place, the
same one answer differing from 31c7e98's checks, and one flag changed in
those five runs since they were made: round 1's false alarm on "September
25th" (`reader_v2`, `thin-2`), cleared because a tool had returned that date.
So the seven runs flag what they flagged when they were made, but for that
false alarm, and the tables above stand. Two runs outside the tables no
longer flag one answer's analyst shares (`consensus-1`): since 4 Oct the
figure check works them out from the counts per rating. Against 31c7e98's
checks one answer changes, and none of its flags: in
`llama3.2_3b_harness_t0.2/lookup-3`, two source names of three words in
single quotes after "cite_as:" ('DBS analyst report') no longer count as
quotes, as a label's colon no longer cues one (as on 7446c89); that answer,
written without a search, is flagged and stripped as before. Against
7446c89, with `--include-untracked`, four answers differ, all from the
seventh's changes: in `llama3.1_8b/evidence-1` and `llama3b_v2/evidence-2`
two quotes no search returned stand on one line, and the words between them
now go with them (in the second, a line of JSON the model wrote); in
`llama8b_v2/lookup-8` and `llama8b_v2_aspectquery/lookup-8` a sentence a
search returned is quoted with two links in it that no search returned as
links, and strip, which once left the quote that removing the links had
altered, flagged, now runs again and removes it too.

**Known limits.** No check that reads quote marks can promise to find every
quote. What is left:

- A quote is checked through its pieces of three or more words, so after a
  search a quote of two words passes unchecked; without a search it counts
  as invented.
- A single quote mark is also an apostrophe. A passage in single marks of
  three to five words is checked only after one of the verbs of saying above
  among the three words before it, after a speaker and a colon, or before a
  citation or a source tag; with none of these it is not checked, so after
  another verb ("noted", "reported", "mentioned"), a noun or a label's colon
  ("Note:") an invented quote of three to five words passes, and nor is one
  of one or two words, one that opens on a digit or one that holds a plural
  possessive ("the banks' fees") checked. A
  single-quoted quote holding another in single marks hides the words after
  the inner one, and single marks never count as marks the checks can't
  place.
- A quote holding another of ten or more characters is checked whole when
  one is straight and the other curly, or one in single marks and the other
  in double. With other marks the words after the inner quote are not read
  as part of the quote: in double marks the outer quote's closing mark is
  then left over, which flags the answer and takes the line in strip mode,
  even for a real sentence quoted whole ('"What do you think of "DBS Robot
  app" with the fees?"'). A quote checked whole is removed whole, so a real
  quote inside it goes with it (the seventh's merged nested quotes), and a
  real sentence quoted with quote marks its source doesn't have is removed
  too.
- In a quote closed by a straight mark, an inch mark after its first ten
  characters ('"the screen is 6" wide ..."') is read as the close, and the
  words after it are not checked: if the quote's own closing mark follows on
  the line, it is left over, which flags the answer and takes the line in
  strip mode, but if the quote was also left open, the words after the inch
  mark pass. A straight quote left open with an inch mark in its first ten
  characters ('"my 6" phone is ...', never closed) reads as a word in quote
  marks, like '"Tier 1"', and the words after it pass.
- A line holding a quote mark the checks can't place goes whole in strip
  mode, correct text and real quotes on it included.
- Words glued to a closing mark, with no space between ('"x"OCBC will
  ...', or '“...”OCBC will ...' after a quote a search returned), are the
  model's own words unless a citation or a mark that reads as a closing one
  ends them. So an invented quote written so, with nothing after it that
  could close it, passes, and the model's own words written so before a
  citation or a stray closing mark ('"buy"by most analysts [DBS, ...]',
  '“...”DBS fell 5" ok') are removed.
- A quote left open runs to the end of its line, so a real quote that lost
  its closing mark is removed with the words after it on that line.
- Marks other than " “ ” « » „ ‟ and ' ‘ ’ (for example ‹...›, ‚...‘ or
  「...」) are not read, and several odd shapes at once can still hide a
  quote: '"unclosed and ” <invented> " ok', with a quote left open, a closing
  mark used to open, spaces inside the marks and a few words after, passes.
- A marker range the model writes ("[12-45]") is dropped from what the
  reader sees; its figures are still checked.
- After a month, a returned day is checked unless it reads as a date in one
  of the ways above, so a real date before any other word is flagged ("Data
  covers September 25 in all three banks", "Sept 25/26"), and so is one
  before "for", a comma or a bracket with a number later in its clause and
  no "on", "as of", "the" or "runs to" before it ("Data covers September 25
  for DBS", "By September 25, DBS scored 0.31", "September 25 (45 posts)").
  A count written where a date reads naturally is taken for the date
  ("Based on September 25 posts"), and so is one before a comma with a
  single number right after it ("In September 25, 31 posts were negative"
  checks only the 31). A day before its month ("25 September") is always a
  date when a tool returned it.

Whether the Grounded chatbot claim keeps "never", or names what is checked and
cites this list, is a team decision on the team to-do
(`docs/briefs/team-todo-2026-10-02.html`, "Word the Grounded chatbot claim to
match what the checks can promise").

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
branch, because the results are longer. The answers were not longer
overall: the branch's were shorter on two of the three questions (205
against 387 tokens, 74 against 99) and longer on one (169 against 94), and
answers were written at about 5 to 11 tokens a second across that day's
runs. Asked alternately, the
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
runs don't say how much of the 26-second gap, between the before run's
average of about 35 seconds an answer and the kept version's median of 61,
each part makes up. The block run and the window run below used the trimmed version (shorter prompt,
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
