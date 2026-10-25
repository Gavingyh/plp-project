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

The before run was not timed per answer: its 16 minutes are its span in the
evaluation's log, `data/logs/plp.log` on 4 Oct (since rotated, on this Mac,
to `data/logs/plp.log.3` by 6 Oct; git doesn't track the rotated files). Its
first question was logged at 13:14:23 and its results written at 13:30:09,
946 seconds; by the times each question was logged, the 26 answers the model
wrote took 935 of them, about 36 seconds each on average and 29 at the
median, and the six fixed replies 12.

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

Eleven validations of the branch (`docs/validation/2026-10-04-chatbot-answers*.md`,
`docs/validation/2026-10-05-chatbot-answers-*-check.md`,
`docs/validation/2026-10-06-chatbot-answers-tenth-check.md` and
`docs/validation/2026-10-06-chatbot-answers-eleventh-check.md`) each found gaps
the change had opened in the checks, or old ones it had not closed. After the
ninth, the project owner chose to stop chasing quote shapes: strip mode, the
default, now shows only quotes a search returned, whatever the detectors miss
(DESIGN decision 26). The tenth found gaps at that design's edges: citations
left on words that lost their quote marks, line endings, marks glued to the
word before them, and figures in retrieved text. The eleventh found the reach
of a citation too wide in one place and too narrow in others, and figures
vouched for by common words. The owner then made the round of fixes after it
the last: what it leaves is under Known limits below. The checks as they
stand:

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
  quote. A mark left without a partner opens a quote that runs to the end of
  its line, or to the next quote, stopping before a citation. Last, a
  passage in single marks (' ‘ ’) counts from six words, or from three after
  a verb of saying among the three words before it ("said", "say", "says",
  "wrote", "write", "writes", "complained", "complain", "complains",
  "posted", "commented", "tweeted", "replied", "added", "asked", "claimed",
  "stated", "quoted", or "put it", "call it", "calls it", "called it"),
  after a speaker and a colon ("One user: '...'", "Another: '...'"), or
  before a citation or a source tag ("(Reddit)"). A noun ("report", "note",
  "post") or a label's colon ("Note: '...'") cues none. An apostrophe inside
  a word ("OCBC's") neither opens nor closes one, and a passage in single
  marks holding a quote in double marks is checked whole.
- **Words glued to a closing mark**, with no space between, are never read
  as a quote by strip mode: they are the model's own words, and the marks
  around them come off (below). The detectors' other reading of them, as a
  quote after a quote no search returned or one too short to check
  ('... Another wrote ”OCBC will ...', where that mark may be the next
  quote's opening one), or wherever a citation or a mark that reads as a
  closing one, an inch mark too, ends them ('"x"OCBC will cut ... for
  sure"'), now decides only which numbered markers inside a quote stay and
  what the replay counts: off mode flags what strip mode changes (below).
- **Strip mode** first removes the quotes the detectors find that no search
  returned, each with the citation right after it, the links and sentence ids
  no search returned, and the words between two removed quotes on one line
  when no kept quote stands between them; it runs again on its result until
  nothing changes, at most ten times, and a note says evidence was removed. A
  removed quote that wraps a line leaves its line break and what opens the
  next line ("1. ", "- ", "> "). Where a reader may read a removed quote's
  mark as opening the words after it, no citation is left to vouch for them:
  the opening mark of a quote left open that the detectors end at the next
  quote stays, for the next step to take off; after a closing mark with words
  glued to it, the citation that ends them on that line goes with the quote;
  and so does a citation after the words of a passage that one of the removed
  quote's marks delimits but that runs on outside it ("'One user said ‚...‘
  invented words', [DBS, ...]", where the detectors end the quote at ‘). The
  words stay. Without a search, if the answer cites evidence no earlier search
  returned, it removes the evidence section, any later line holding a quote,
  link or sentence id, and any quote, link or id in the first paragraph. Then
  it takes the quote marks off everything else a search doesn't vouch for,
  keeping the words: every double mark, every single mark but an apostrophe
  ("OCBC's") or a possessive after an s ("the banks' fees"), and every
  blockquote ">". A left-hand mark (‘) is neither; a straight or right-hand
  one between two letters is an apostrophe unless it opens a quote glued to
  the word before: a capital after it and two letters before it
  ("wrote'OCBC"), or no contraction or possessive ending after it and a mark
  later in its paragraph, on its line or the next, that closes three or more
  words ("wrote'the bank will cut its dividend next year'"); one letter before a capital is a name's ("Côte
  d'Ivoire"). The marks it reads are those Unicode lists as quotation marks ("
  “ ” « » „ ‟ ' ‘ ’ ‚ ‛ ‹ › 「 」 ＂ and the like), the quotation mark ornaments
  (❝ ❞ ❛ ❜ ❮ ❯ and the like) and the double primes (″ ‶), each also written as
  a character reference ("&quot;", "&#8220;"). It keeps the marks of a quote
  the detectors find that one search result, this turn's or an earlier turn's,
  holds piece by piece, cut at an ellipsis, in order, pieces of any length but
  each as whole words ("... impressive" is no piece of "unimpressive"), or
  that is a reading or a real topic name a tool returned; of two marks around
  such text that the detectors read as two quotes ('„What do you think of "DBS
  Robot" with the 0.5% fees?“'); of a word or two in matching marks with no
  space just inside them ('rated "buy"', '„Tier 1“', '»DBS«', "'hold'"),
  unless a citation vouches for them (below); of an inch mark; and of an aside
  ("> **Note:** ..."). A mark between two words gives way to a space
  ("wrote'OCBC" becomes "wrote OCBC"), and a line left holding nothing goes.
  Then it reads the answer as a reader pairs the marks, in order, in each line
  and in each paragraph (markdown shows a paragraph's lines as one): double
  marks first with second, third with fourth, an inch mark aside unless it
  closes a word or two opened with a straight mark ('"Tier 1"'); single marks
  alike, a possessive only closing a passage open before it; a mark left over
  opening a passage to the end; and each family of marks that look alike (" “
  ” „, or ‹ ›) also on its own. A line where that shows a passage of three or
  more words no search returned loses all its quote marks but inch marks,
  apostrophes and possessives, a blockquote line whose blockquote, with the
  lines markdown joins to it, shows such a passage loses its ">", and the
  whole runs again until nothing changes. Then it cuts each citation that
  would vouch for words no search returned. A citation (as cite_as writes it,
  a numbered marker such as "[1]" or "[E1]", another bracket naming a sentence
  id, an id written bare, or a link: '(https://...)', '[post](https://...)'),
  or a run of them, vouches for its own sentence, back to the citation before
  it there and on to the one after it. A sentence ends at a full stop, "!" or
  "?" (not an ellipsis, nor the full stop of an abbreviation such as "vs." or
  "e.g."), with any closing marks after it, before a space or a line break and
  anything but a lower-case letter; at a semicolon before a space; and where a
  paragraph or block starts: a list item, a heading, a table row, a blockquote
  after a line outside one. A line break inside a paragraph ends none, as
  markdown shows the paragraph's lines as one. Where only a label ("Source:")
  stands before a citation in its sentence ('... for sure. [DBS, ...]'), it
  vouches for the sentence before it in its paragraph too. The citation goes
  where its sentence holds words that a reader saw in quote marks or a
  blockquote, in the answer as the model wrote it, in what strip mode's first
  step left or in its result, or words before a mark taken off that opens no
  words ('... for sure” [DBS, ...]'), and they are no text a search returned,
  a returned word or two or a returned quote beside them excusing nothing; or
  where it holds a word or two in quote marks no search returned, which then
  lose their marks. After a citation that doesn't introduce the words after
  it, only words that stood in quote marks count there, three or more of them:
  a word or two is a term or a scare quote ('Users complain the app is slow at
  night [DBS, ...], despite the "super app" label.' keeps its citation), and a
  line a blockquote joins to the citation's line its attribution ('>
  "..." [DBS, ...]', then a line naming the Reddit user who wrote it). A
  citation introduces the words after it where at most four words stand
  before it in its sentence ('According to [DBS, ...], ...', 'In one post
  [DBS, ...], ...'), labels and
  a list item's lead aside, and no quote mark right before it; where "to",
  "per", "by", "from", "in", "on", "via", "see" or "cf" stands right before it;
  or where a colon follows it. A citation goes with brackets or a label left
  holding nothing ("(Source: ...)", ", see ...") and with an attribution at
  its sentence's start and the comma after it ('According to [DBS, ...], one
  user called OCBC "a scam".' shows "one user called OCBC a scam."): 'One user
  called OCBC "a scam" [DBS, ...]' shows "One user called OCBC a scam", while
  '"slow" [DBS, ...]' stays as written when a search returned "slow". The
  words are read on strip mode's result, with where each one stood in what
  strip mode read, and with the answer as the model wrote it matched word by
  word, so nothing taken off on the way is missed (the first step also cuts a
  citation whose sentence holds such words, before it removes the quotes);
  this and the steps above run in turn until nothing changes, and no note is
  added when only a citation goes. So after strip mode every passage of three
  or more words a reader sees in quote marks is text a search returned, word
  for word, or the tools' own wording, and no citation vouches for words that
  stood in quote marks and are not, with the exceptions just given;
  `tests/test_chatbot_strip_property.py` checks both on 3,000 made-up answers,
  after a search and without, with a fixed seed (other seeds by hand,
  `STRIP_PROPERTY_SEEDS=1-60`), and `tests/quote_marks.py` reads them as a
  reader does, written apart from the code it checks. The flag strip mode
  returns, whether a link, a sentence id or a passage shown is still
  unverified, has nothing left to raise.
- **Line endings**: every check reads a carriage return, alone or before a
  line feed, as a line feed, as markdown does, and, to be safe, so the other
  characters Python breaks a line at (U+2028, U+2029, \x0b, \x0c, \x85 and
  \x1c to \x1e); strip mode returns line feeds, and off mode returns the
  answer as written (the tenth validation: a blockquote after a lone carriage
  return passed both, unflagged).
- **Off mode** changes nothing. It flags exactly what strip mode would
  change, and no more: a link or sentence id no search returned, a quote no
  search returned (without a search this turn, any quote an earlier turn's
  search didn't return), an evidence marker with no search made, quote marks
  strip mode would take off and a citation it would cut. Line endings,
  character references and bare numbered markers, which strip mode also
  rewrites, raise nothing, and nor do a word or two in quote marks that no
  citation vouches for, an inch mark, an apostrophe, a quote a search
  returned (in a blockquote with its citation too: the eleventh validation
  found that flagged) and a reading or topic name. A double mark the
  detectors can't place, which until the ninth validation flagged the answer
  and took its line in strip mode, is now only counted by the replay.
- **A quote is compared** with what the searches returned piece by piece,
  cut at an ellipsis, each piece of three or more words without the
  punctuation and spaces at its ends, so a sentence quoted with a comma
  inside the closing mark ('"...night,"') is the sentence returned. To keep
  its marks in strip mode every piece, of any length, must stand in one
  retrieved text, in order, as whole words.
- **Numbered markers** the model writes ("[2]", "[2, 3]", "[12-45]") are
  dropped only after the checks have read the model's own text and removed
  any unretrieved quote or link, and before strip mode takes quote marks
  off; a drop that leaves a new marker ("[1[2]]" leaves "[1]") is repeated,
  the figures of every dropped marker are still checked, and "[0, 1]" is
  left as written. At display, a marker inside a quote stays only if the
  quoted sentence has it (one stored sentence has a "[1]" footnote).
  Through the API, history drops the markers and the list of sources the
  reader saw. An evidence marker ("[E1]", "[E1][E2]", "[E1, E2]") with no
  search made this turn points at nothing a search returned: strip mode
  removes it with the other unsearched evidence, and off mode flags it (the
  eleventh validation found runs and lists of them kept, unflagged).
- **A figure in retrieved text** vouches only for itself, written with the
  sentence's words around it: the figure check takes a figure for a
  retrieved sentence's own where at least two of the three words nearest it
  on either side, in its sentence and not across an ellipsis, are among the
  three nearest the same figure in one retrieved sentence, common words
  skipped in both ("the", "of", "a", "an", "in", "on", "at", "to", "for",
  "and", "or", "per", "cent", "percent", "is", "was", "were", "are", "by",
  "with", "from", "about", "around"): in "the payment was due on 17th" those
  of 17th are "due" and "payment". It also takes one inside a quote of that
  sentence holding two or more other words, common words aside. Any other
  figure must match a numeric field, or a value worked out from them as
  before (the tenth validation: with "I paid 37 dollars in fees" retrieved,
  "DBS had 37 negative posts" passed; the eleventh: with "Around 37% of the
  bank's profit came from wealth" retrieved, "37% of the posts about DBS were
  negative" passed, three words in a row, "37% of the", being enough). A word
  or two in quote marks ('"37"') vouches for nothing.
- **A date without its year** is skipped by the figure check only when a
  tool's date field (`data_runs_to`, an evidence item's date) has that month
  and day. After a month, such a day, ordinal or not, is a date only where it
  clearly reads as one, and never after "in" ("in early", "in mid" and "in
  late" too): "in September" names the month, so a number after it is a
  count. Otherwise it is a date after "on", "as of", "as at", "the", "dated"
  or "runs to" (a range also after "from" or "between"), or before a line
  end, punctuation other than "%", a comma or an opening bracket (a dash
  only when no digit follows it), "and", "&", "to" or "/" not followed by a
  number, an article or determiner, or one of "until", "till", "through",
  "when", "while", "after", "before", "since", "during" and "as". Before a
  comma it is a date when no number follows in the rest of its clause, or
  just one, right after the comma ("September 25, 45 posts"); and after
  "by", "up to", "through", "until", "till", "to", "since", "ends", "ended",
  "covers" or "covering" when no number follows the comma ("By September 25,
  DBS scored 0.31"). Before an opening bracket, ( or [, it is a date only
  when the bracket holds no digit and no word of approximation ("approx.",
  "about", "or so") and its clause ends right after the closing bracket ("The
  latest post is September 25 (the end of the data)."), or, after one of
  those words, a comma follows the bracket with no number right after it. A
  clause ends at a line end, or at ".", ";", ":", "!" or "?" before a line
  end or before a space and a capital or a digit, never at the full stop of
  an abbreviation ("vs.", "approx.", "i.e.", "e.g.", "etc.", "incl.", "cf.",
  "no.", "ca." and a few more). Anywhere else it is a figure to check: with
  data to 25 September, "In September 25 customers complained", "September
  25th sentences", "In September 25, 31 and 40 posts", "September 25, vs. 40
  in August", "In September 25 (out of 40) posts", "September 25 (approx.)."
  and "September 25 for DBS against 40 for UOB" are counts to check, and
  "Data runs to September 25 for DBS" a date. "September 25 (45 posts)." is
  checked too: there the day is a date, flagged as a false alarm the checks
  accept, as a bracket holding a digit may hold a count (Known limits). A
  share after the day ("25 per cent", "25 to 30% of posts") means
  both numbers are checked, and so are both ends of a range not read as a
  date. A day followed by a decimal, a thousands group or "%" is never a
  date. A date in the model's own search query, a link or a quoted sentence
  vouches for nothing, and "may" in lower case is the verb.
- **Tool wording**: a reading or a real topic name in quote marks is not a
  quote, and keeps its marks in strip mode; a topic name the model set by
  passing its own text as the aspect is not exempt.
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
   snapshot kept only in a session's scratch folder. The changes (31c7e98):
   a mark the checks couldn't place took its line, the words between two
   removed quotes went with them, strip ran until nothing changed, low-9
   marks were read, single quotes counted from three words with a cue, a
   quote was compared without its end punctuation, a returned day was a
   date only where it read as one, and `scripts/replay_checks.py --against
   <commit>` compared with any commit's checks. Checking these changes on
   made-up answers with several odd shapes at once found more ways for one
   quote to take another's mark (a quote's closing mark read as a pair with
   an inch mark after it, an opening mark typed to close, the next quote's
   opening mark taken as a quote's close, and a quote holding a real one
   whose closing mark, after punctuation, was read as a stray mark), each
   then caught; and so that real quotes in mixed marks ('»...»', '"...“')
   didn't lose their line, those were read as pairs.
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
   other lines. The changes (f511f83): a comma or a bracket after a returned
   day ended a date only with no number later in its clause (or one right
   after the comma), and "for" no longer did; a word in quote marks kept
   both its marks whatever followed; the words glued to a quote's closing
   mark were checked after an unverified quote, or where a citation or a
   closing mark ended them; single quotes were cued by verbs of saying, a
   speaker's colon or a citation after them; a stray mark at the end of its
   line after a quote or its citation was placed; and
   `scripts/replay_checks.py` read only the results files git tracks unless
   asked. Checking these changes against 31c7e98 on made-up answers found
   invented quotes that a first draft of them missed (glued words ended by
   an inch mark, by a mark on the next line, or by a closing mark that a
   stray mark after a citation paired with), which f511f83 then caught.
   Those made-up answers were not saved, so that comparison can't be re-run;
   since the ninth validation a committed property test with a fixed seed
   checks strip mode on made-up answers instead (above).
9. The ninth (5 Oct): f511f83's rule for a stray mark hid a mark at the end
   of a line after a real quote or its citation, and with it the invented
   quote that mark opened on the next line; words glued to the closing mark
   of a real quote or of a word in quote marks ('“...”OCBC will cut its
   dividend next year for sure.', '"x"OCBC will ...') passed strip mode
   unflagged; the full stop of an
   abbreviation ended a date's clause, so "In September 25, vs. 45 in August,
   posts were negative" hid the 25, as did "approx.", "i.e." and "(approx.)";
   ordinary dates were flagged ("By September 25, DBS scored 0.31.",
   "September 25 (45 posts).", "The latest post is September 25 (the end of
   the data)."); and a word in quote marks glued to words an inch mark ended
   ('"DBS"and OCBC rose 5" in the chart.') lost its line in strip mode. It
   also found that this page's claim that no correct answer kept as written
   was changed rested on made-up answers saved nowhere, that the before
   run's 16 minutes were not cited to their source, and that the HANDOFF
   entry left out the citation cue for single quotes; all three are fixed.
   The owner then changed the design (decision 26): strip mode removes the
   quotes no search returned as before, then takes the quote marks off
   whatever a search doesn't vouch for, and the rule that removed a line
   holding a mark the checks couldn't place, and the stray-mark rule, went.
   So the mark at the end of the line and the marks around the glued words
   come off, the invented words standing outside quote marks, and the
   correct line keeps its marks. The date changes are the rules above: a
   clause ends only before a capital, a digit or a line end, never at an
   abbreviation; a comma after "by", "up to", "through" and the like ends a
   date when no number follows it; a bracket ends one only where it holds no
   digit and no word of approximation and its clause ends right after it;
   and after "in" a returned day is always checked. Checking the new design
   on made-up answers, before it was committed, found shapes a first draft
   of it left in quote marks, unflagged, each then handled: marks such as
   ‹...›, 「...」, ❮...❯ and "&quot;", lines markdown joins to a blockquote,
   a blockquote in a nested list item, the model's own copy of the harness's
   heading, and a piece of a quote found inside a longer word ('"OCBC's
   results are ... impressive"' when the source says "unimpressive").
10. The tenth (6 Oct): a cited word or two in quote marks that no search
   returned ('One user called OCBC "a scam" [DBS, ...]') passed strip and off
   mode unflagged, and read as a cited quote once numbered (also on `main`);
   an invented passage that lost its marks kept a real citation after a full
   stop, a comma, a dash, a bracket or "one user wrote" ('One user: ‹...›.
   [DBS, ...]', from 03dc631), and read as sourced prose; a blockquote after
   a lone carriage return ('He said\r> ...') passed strip mode and
   `answer_turn` unchanged, and off mode didn't flag it (also on `main`); an
   opening mark glued to the word before was read as an apostrophe
   ("wrote‘the bank will ...’", "wrote'the bank ...'"); and a number in any
   retrieved sentence vouched for the same number used as a count ("I paid
   37 dollars in fees" for "37 negative posts", also on `main`). It also
   found this page comparing a mean with a median, calling "September 25 (45
   posts)" both a count and a date, and quoting the replay without a line it
   prints, and the RUNBOOK and HANDOFF out of date; all are fixed. The
   changes are the rules above: every line ending read as a line feed, a
   left-hand mark never an apostrophe, a straight one between two letters a
   quote's opening where a mark later on its line closes three or more
   words, a citation cut where it would vouch for words no search returned,
   and a figure in retrieved text vouching only for itself among its words.
   Checking them on made-up answers (the property test, extended to these
   shapes, at its fixed seed and at seeds 1 to 60) found more ways for a
   citation to keep vouching for invented words, each then handled: a quote
   kept inside a passage left open before it, a possessive read as closing a
   passage, a mark taken off in a later pass, a removed quote that took a
   line break or a list marker with it, and a removed quote whose mark also
   opened the words after it. They are tested in `tests/test_chatbot_harness.py`
   (after the tenth validation) and `tests/test_chatbot_strip_property.py`.
11. The eleventh (6 Oct): a word or two in quote marks that no search
   returned kept its source, unflagged, when a link cited it ('One user
   called OCBC "a scam" (https://...)') or a citation stood before it
   ('According to [DBS, ...], one user called OCBC "a scam".'), also on
   `main`; a scare quote in the sentence before cut a correct citation ('DBS
   markets it as a "super app". Users complain the app is slow at night
   [DBS, ...].'), and off mode flagged it (from f7a90fb); a returned word in
   quote marks shielded invented words that lost their marks before it ('One
   user: ‹...›, "slow" [DBS, ...]', from 03dc631); a figure in a retrieved
   sentence vouched for a share of posts through common words ("37% of the");
   a quote glued to the word before kept its opening mark when its closing
   mark stood on the next line; a returned blockquote lost its citation to a
   de-marked line above it; evidence markers with no search ("[E1][E2]",
   "[E1], [E2]", "[E1, E2]") passed both modes; and off mode flagged a
   returned blockquote with its citation, which strip mode kept (also on
   `main`). It also found diagram 07 describing the old exception for a word
   or two in quote marks, DESIGN's costs leaving out the figure false alarms
   the tenth's changes brought, and this page quoting one answer's figure in
   another's words; all are fixed. The changes, in the last round of fixes,
   are the rules above: a citation vouches for its own sentence, a link
   cites, off mode flags exactly what strip mode changes, a glued opening
   mark looks for its closing mark to the end of its paragraph, an evidence
   marker with no search goes, and a figure vouches for itself through two of
   its nearest words that are not common ones. Checking them found three more
   things, each then handled: on made-up answers (the property test, extended
   to links, sentences ending in "!" or a semicolon, citations after an
   attribution, a short introduction or a full clause, and glued quotes
   across a line break), citations whose sentence grew once strip mode took
   out a full stop, a semicolon or a blockquote's ">" between them and words
   a removed quote's mark had opened, and a passage whose marks paired
   otherwise once a removed quote's marks went, so the answer as the model
   wrote it is now read too; a first draft that counted every line a
   blockquote joins cut a correct quote's citation before its attribution
   line ('> "..." [DBS, ...]', then a line naming the Reddit user who wrote
   it); and counting the three words on either side of a figure in a row,
   common ones too, flagged four more recorded answers that give a retrieved
   sentence's figure, three of them copying the sentence ("was due on
   17th"), where skipping common words flags none of them and clears the
   seven. They are tested in `tests/test_chatbot_harness.py` (after the
   eleventh validation) and `tests/test_chatbot_strip_property.py`, which
   passes at its fixed seed and at seeds 1 to 60.

Each finding has a test, in `tests/test_validate_chatbot_*.py` or, for two of
the fifth's ("Sept 25-26" read as a date, and the neutral share), in
`tests/test_chatbot_reader.py`. Two stay marked as expected to fail, as
recorded limits (below): the seventh's merged nested quotes, and three of the
ninth's ordinary dates ("September 25 (45 posts).", "Data covers Sept 25-26
for DBS.", "Data to Sept 25 for all three banks."); every test of the tenth's
and the eleventh's passes. Since decision 26 a test
of an invented quote passes when the quote is removed, flagged, or no longer
in quote marks (`tests/quote_marks.py`); the earlier validations' tests whose invented words
now stand outside quote marks say so in a comment, as do the tests of
correct answers whose term of three or more words in quote marks now loses
its marks. The gaps found while checking the sixth's, the seventh's and the
eighth's changes, and the new design's rules, are tested in
`tests/test_chatbot_harness.py` (dates in `tests/test_chatbot_reader.py`, the
replay in `tests/test_replay_checks.py`), and its guarantee in
`tests/test_chatbot_strip_property.py`. Some tests of earlier rounds now
expect what this round's rules do instead: a citation after a returned quote
goes when invented words that lost their marks stand earlier in its sentence,
a figure the model copies with two of its nearest words is no longer flagged
("One user paid 37 in fees."), and off mode no longer flags glued words that
an inch mark ends, which a reader sees outside quote marks ('"x"OCBC will
cut ... by 5"'); each says so in a comment.

`scripts/replay_checks.py` re-runs the citation check, the figure check and
strip mode over every answer recorded in the results files under
`data/eval/` that git tracks, compares each gold-set run's flags with those
recorded when it was made, counts the answers holding a quote mark the
detectors can't place and those in which strip mode takes quote marks off
words it keeps, and names them. Its first line says how many results files
it read and how many of those git doesn't track. With `--against <commit>`
it also compares every answer's checks with that commit's: it extracts the
commit's files into a temporary folder and runs its code there over the same
results files, changing nothing in the repository; on a machine holding
results files git doesn't track, a line on stderr says how many it left
out. On 6 Oct, after the eleventh validation's fixes,
`HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/replay_checks.py --against
f7a90fb` printed, on this Mac, which holds five such files (the line in
brackets on stderr):

```
Results files read: 36; not tracked by git: 0
(5 results files here are not tracked by git and were not read; --include-untracked reads them)
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
  holding a quote mark the detectors can't place: 0
  where strip mode takes quote marks off words it keeps: 2
    phi4-mini_latest/lookup-2
    phi4-mini_latest/lookup-4
  differing from the checks of f7a90fb: 5
    llama3.1_8b_rerun/evidence-1: figures ['17'] -> []; strip_figures ['17'] -> []
    llama3.2_3b_10aspects_2026-09-30/evidence-2: figures ['20%'] -> []; strip_figures ['20%'] -> []
    llama3b_v2/evidence-2: figures ['20%'] -> []; strip_figures ['20%'] -> []
    llama3b_v2_strip/evidence-2: figures ['20%'] -> []; strip_figures ['20%'] -> []
    llama8b_v2_strip/evidence-2: figures ['2.1%'] -> []; strip_figures ['2.1%'] -> []
```

Against f7a90fb's checks five answers change, each in its figure flags and
nothing else: no strip result, citation flag or quote changes in any of the
540, and the two answers strip mode takes quote marks off are the same two
as before (`phi4-mini` answers written as JSON without searching, where an
empty pair, `"aspect": ""`, loses its marks). The five are the false alarms
the tenth validation's figure rule brought, as the same command against
03dc631 printed on 6 Oct after those fixes: each gave a figure from a
retrieved sentence in other words, "due on the 17th" for "due on 17th"
(`llama3.1_8b_rerun/evidence-1`), "(20% of lending portfolio)" for "About
20% of UOB’s lending portfolio" (`llama3.2_3b_10aspects_2026-09-30/evidence-2`
and `llama3b_v2/evidence-2`), "approximately 20% of its lending portfolio"
for the same sentence (`llama3b_v2_strip/evidence-2`; until the eleventh
validation this page quoted it as the other two), and "The NPL ratio at UOB
is at 2.1%" for "NPL ratio at 2.1%" (`llama8b_v2_strip/evidence-2`). Each
figure now has two of its nearest words, common ones skipped, round it in
the sentence too ("due" and "payment"; "lending" and "portfolio"; "npl" and
"ratio"), so the check takes it for the sentence's own again.

Five of the seven runs in the tables (`reader_v2`, `reader2_v2`, `reader3_v2`,
`final_v2` and `mix_v2`) are kept out of git because they quote CNA text, and
`--include-untracked` adds them on the team's machine that has them: there
the same command printed `Results files read: 41; not tracked by git: 5`,
`Every recorded answer: 670`, none holding a mark the detectors can't place,
the same two answers changed by strip mode, and seven answers differing from
f7a90fb's checks: the five above, and the two false alarms of these runs
that f7a90fb brought, a results report's figure in other words, a
non-performing loan ratio that "was at 0.9%" (`reader_v2`, `lookup-2`) and
a "16% increase" in wealth income (`reader2_v2`, `lookup-6`), now cleared.
Against the flags recorded when they were made, those five runs differ only
in round 1's false alarm on "September 25th" (`reader_v2`, `thin-2`),
cleared because a tool had returned that date. So with today's checks the
tables' row of answers with a figure flagged would read 3 for round 1
instead of 4, and every other row stands as recorded. Two runs outside the
tables no longer flag one answer's analyst shares (`consensus-1`): since 4
Oct the figure check works them out from the counts per rating.

As no real answer shows more, here is what strip mode now does with
made-up answers from the tests, after a search that returned "the app is
slow to load at night" (cited as `[DBS, ...]`):

| the model wrote | strip mode shows |
|---|---|
| `One user: "the app is slow to load at night" [DBS, ...]. Another: "OCBC will cut its dividend next year for sure" [DBS, ...]` | `One user: "the app is slow to load at night" [DBS, ...]. Another:` and the note that evidence was removed, as before |
| `“the app is slow to load at night”OCBC will cut its dividend next year for sure.` | the same: the real quote keeps its marks, and the glued words stand outside them |
| `"the app is slow to load at night" [DBS, ...] "`, and on the next line `OCBC will cut its dividend next year for sure` | the same without the mark at the end of the first line and, since the twelfth round, without the citation: the invented words stood in quote marks in its sentence |
| `"x"OCBC will cut its dividend next year for sure" [DBS, ...]` | `x OCBC will cut its dividend next year for sure`: the marks go, and the citation that vouches for the words (until the tenth validation `"x"` kept its marks) |
| `One user called OCBC "a scam" [DBS, ...]` | `One user called OCBC a scam` |
| `One user called OCBC "a scam" (https://...).` | `One user called OCBC a scam.` |
| `According to [DBS, ...], one user called OCBC "a scam".` | `one user called OCBC a scam.` |
| `DBS markets it as a "super app". Users complain the app is slow at night [DBS, ...].` | the same: the citation vouches for its own sentence |
| `Users complain the app is slow at night [DBS, ...], despite the "super app" label.` | the same: a word or two after a citation that ends a clause is a term |
| `One user: ‹OCBC will cut its dividend next year for sure›. [DBS, ...]` | `One user: OCBC will cut its dividend next year for sure.` |
| `One user: ‹OCBC will cut its dividend next year for sure›, "slow" [DBS, ...]` | `One user: OCBC will cut its dividend next year for sure, "slow"` |
| `Users call the app "slow" [DBS, ...].` | the same: a search returned "slow" |
| `Users report 'long queue times' at branches.` | `Users report long queue times at branches.` |
| `Rated "buy" by most; a 6" phone; the banks' fees.` | the same |

**Known limits.** Strip mode's guarantee covers quote marks: what a reader
sees in them is text a search returned. The twelfth round was the last round
of fixes, by the owner's decision on 6 Oct, so what is left stays as listed
here:

- An invented quote whose marks come off stays as the model's own words,
  often after "One user wrote", where a reader may still take it for a
  quote; the citation that vouches for it goes, the sentence stays. The
  checks don't read paraphrase: words the model gives a source without
  quote marks pass, as on `main`.
- A citation vouches for its own sentence, so it goes for more than the
  words right before it: a correct paraphrase's citation goes when a word or
  two in quote marks that no search returned stands before it in its
  sentence ('Users call the app "clunky" and slow [DBS, ...].' shows "Users
  call the app clunky and slow."), a real quote's citation goes when words
  that stood in quote marks, three or more, follow it in its sentence ('"the
  app is slow to load at night" [DBS, ...] and ‹OCBC will cut ...›.'), and a
  citation between two sentences ('... ‹...›. [DBS, ...] The app is slow.')
  goes for either. The other way, a word or two in quote marks after a
  citation that ends a clause or a quote is read as a term, so 'Users
  complain the app is slow at night [DBS, ...], and one user called OCBC "a
  scam".' keeps its citation, which a reader may take to cover the whole
  sentence; whether a citation introduces the words after it is read from
  the words before it, so a longer introduction ('According to one long-time
  DBS customer [DBS, ...], OCBC is "a scam".') reads as a clause the citation
  ends, and keeps it; a citation before a colon that ends its line vouches
  for nothing in the list items after it ('Two points [DBS, ...]:', then '-
  ‹...›'); and sentences end only at the marks above, so an abbreviation not
  on the list joins two sentences into one reach, and a sentence end strip
  mode takes out joins two (the last step then reads the answer as the model
  wrote it, matching its words in order; in a long answer whose removed
  quotes repeat its other words the match may misplace some). When a citation
  goes, an attribution at the sentence's start goes with it and the sentence
  then starts in lower case ("one user called OCBC a scam."). Words written
  after a quote's citation without quote marks are not read: the citation
  stays when invented words follow it unquoted.
- A term of three or more words in quote marks that no search returned loses
  its marks in strip mode ("DBS's 'customer first digital approach'" becomes
  "DBS's customer first digital approach"), and flags the answer in off
  mode.
- The reader the guarantee assumes pairs marks in order, whatever their shape,
  so an opening mark that comes while a passage is open closes it ('"...
  fees?_“UOB will ...' closes at “, leaving the words after it, and a citation
  after them, outside quote marks). It reads a straight mark after a digit as
  an inch mark ('5"') unless it closes a word or two; a straight or right-hand
  single mark between two letters as an apostrophe, unless a capital follows
  with two letters before it ("wrote'OCBC") or no contraction ending follows
  and a mark later in its paragraph closes three or more words ("wrote'the
  bank will ...'"); a left-hand mark (‘) never as one; and a single mark after an s
  as a possessive. So two inch marks around words ('by 5" ... to 6"') are no
  quote to it; a correct line with such a mark before a closing mark three or
  more words on loses its marks ("ma'am, the banks' fees are high" shows "ma
  am, the banks fees are high"); a quote glued to a one-letter word and
  opening with a capital ("a'The bank ...'") reads as a name's apostrophe
  ("Côte d'Ivoire"); and a left-hand mark typed for an apostrophe ("don‘t")
  comes off ("don t"). Words are runs of letters and digits, a Chinese or
  Japanese character counting as one. A blockquote line that opens with an
  aside's label ("> **Note:** ...") keeps its ">". Characters that only look
  like quote marks and are none (a modifier letter such as ʺ or ʼ, the Hebrew
  gershayim ״, a prime ′) are not read as quote marks: words between them keep
  them, unflagged.
- A quote cut at an ellipsis keeps its marks when each piece stands in one
  returned text, in order, as whole words, so an ellipsis can drop words
  that change its sense ("the results are not impressive" quoted as '"the
  results are ... impressive"').
- A quote a search returned is not matched with the citation after it: a
  real quote cited to another search result keeps its marks and that
  citation, and the source list numbers it.
- Off mode's flag says only that strip mode would change the answer: it is
  raised as much for a term of three or more words in quote marks, or for a
  correct citation strip mode would cut as above, as for invented evidence.
- The detectors' own gaps decide what strip mode removes rather than
  unquotes: after a search a quote of two words passes unchecked (without a
  search it counts as invented); a single-quoted passage of three to five
  words is a quote only after one of the cues above, else a term; a quote
  checked whole is removed whole, so a real quote inside an invented one
  goes with it (the seventh's merged nested quotes), and so does a real
  sentence quoted with quote marks its source doesn't have; and a quote left
  open runs to the end of its line, so a real quote that lost its closing
  mark is removed with the words after it on that line. Off mode flags
  whatever strip mode would change, so the same gaps decide nothing there
  but how the flag comes about.
- A marker range the model writes ("[12-45]") is dropped from what the
  reader sees; its figures are still checked.
- A figure in a retrieved sentence vouches for itself where two of the three
  words nearest it on either side, common words skipped, are among those
  round it in that sentence. So a figure the model rewords with fewer shared
  words ("Fees of 37 hit one user." for "I paid 37 dollars in fees") is
  flagged, a false alarm; the seven recorded answers f7a90fb's rule flagged
  so are no longer flagged, and no other recorded answer's figure flags
  changed (the replay above). And a figure moved onto
  another subject passes where two such words happen to match ('DBS fees: 37
  posts were negative.' with "I paid 37 dollars in fees at DBS" retrieved):
  the check doesn't read what a figure counts. A currency written before a
  number ("S$1.12") counts its letter as one of the words.
- After a month, a returned day is checked unless it reads as a date in one
  of the ways above, so a real date is flagged before any other word ("Data
  covers September 25 in all three banks", "Sept 25/26", "Data covers Sept
  25-26 for DBS", "Data to Sept 25 for all three banks"), after "in" ("In
  September 25, DBS scored well"), before a bracket holding a digit
  ("September 25 (45 posts).") or one its clause goes on after ("September
  25 (Thursday) was the last day of data."), and before a comma with a
  number later in its clause and none of the words above before it
  ("September 25, DBS had 45 posts."). A count written where a date reads
  naturally is taken for the date ("Based on September 25 posts", "By
  September 25, 45 posts."), and so is one before a comma with a single
  number right after it and no "in" before the month ("September 25, 31
  posts were negative." checks only the 31). A day before its month ("25
  September") is always a date when a tool returned it.
- Found by the twelfth validation (6 Oct, after 174c77d), left as recorded
  limits, each a strict expected failure in
  `tests/test_validate_chatbot_off_mode_and_nearest_words_review_findings.py` or
  `tests/test_validate_chatbot_off_mode_and_nearest_words_probes.py`:
  - A citation behind a source note in the next sentence ('One user called
    OCBC "a scam". (Reddit, [DBS, ...])', and 'A Reddit post [DBS, ...].',
    'Source: a Reddit thread [DBS, ...]') doesn't read the quote in the
    sentence before it, so a word or two in quote marks that no search
    returned keeps its marks and the citation, unflagged. 174c77d made this
    so; f7a90fb cut it.
  - Words in backticks are not read as quote marks: 'One user wrote `OCBC
    will cut its dividend next year` [DBS, ...].' keeps its citation in both
    modes (as at f7a90fb).
  - The figure rule above also lets a retrieved figure vouch for the same
    number counting something else when two subject words match ("the DBS
    app had 30 minutes of downtime" for "The DBS app had 30 negative posts.";
    "DBS raised fees by 45 dollars" for "45 posts about DBS fees").
  - A returned blockquote whose citation stands on its own '>' line loses
    that line's '>' in strip mode, so off mode flags the correct answer (as
    at f7a90fb).
- Found by the thirteenth, final validation (6 Oct, after 420ea79), all also
  on `main`, left as recorded limits with strict expected failures in
  `tests/test_validate_chatbot_invented_counts_review_findings.py`:
  - An invented quote that strip mode removes leaves its citation when
    anything but a space stands between them: a dash ('"..." — [DBS, ...]'),
    a closing bold or emphasis mark, a closing bracket, a comma, a table
    bar, or a line break. The citation then sits beside the model's own
    claim. Only '"..." [DBS, ...]' and '("..." [DBS, ...])' lose it.
  - The figure check skips some numbers by design: a whole number from 1990
    to 2100 written without a comma (read as a year, so "2045 negative
    posts" passes), a number before day, week, month or year ("negative
    for 37 days"), and numbers under 10.
  - A count written as a share in words ("45 per cent of DBS posts", also
    "percent" and "pct") is checked as a plain number, so a returned count
    of 45 vouches for it; "45%" is checked as a share.
  - A figure written without its leading zero (".87") is not read. No
    recorded answer writes one.

On 6 Oct the owner reworded the Grounded chatbot claim in `CLAUDE.md` to what
the checks prove, citing this list: in strip mode, every passage of three or
more words shown in quote marks is text a search returned (or the tools' own
wording, such as a reading or a topic name), a citation stays only where its
sentence's quoted words were returned, and every figure is checked as above.
The team to-do records the decision (`docs/briefs/team-todo.html`).

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
questions. Before, the 32 questions took 16 minutes: about 36 seconds on
average for each answer the model wrote, 29 at the median (the run's log,
under Results); the kept version's answers took 62 on average
(`data/run/overnight/times_mix_v2.jsonl`).

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
runs don't say how much of the gap between the before run and the kept
version, a median of about 29 seconds an answer against 61 (on average 36
against 62), each part makes up. The block run and the window run below used the trimmed version (shorter prompt,
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

## Live check after the last round (6 Oct)

On 6 Oct, at commit a6f3cdc (the checks of 174c77d), the 32-question gold set,
the multi-turn conversations and seven dashboard questions were run again with
`llama3.1:8b` through Ollama, using the scripts in `data/run/overnight/`
(`timed_eval.py final3_v2`, `timed_eval.py final3_mt --multi-turn`,
`ui_questions.py`). Against the mix run of 4 Oct
(`data/eval/chatbot_eval_summary_mix_v2.md`,
`data/run/overnight/times_mix_v2.jsonl`):

| | mix run, 4 Oct | live check, 6 Oct |
|---|---|---|
| Tool selection | 23/24 | 23/24 |
| Behaviour (advice declined, no data said) | 7/8 | 8/8 |
| Answers with a figure no tool returned | 1/32 | 0/32 |
| Citation fabrication flagged | 0/32 | 0/32 |
| Evidence written without a search, removed | 6/32 | 3/32 |
| Median seconds per question | 60 | 47 |
| Scores stated, with their scale | 13 of 19 | 13 of 20 |
| Answers giving a share in % | 13 | 14 |
| Multi-turn turns correct | | 9/9 (4/4 conversations) |

Sources: `data/eval/chatbot_eval_summary_final3_v2.md`,
`data/eval/chatbot_multiturn_summary_final3_mt.md`,
`data/run/overnight/times_final3_v2.jsonl` (median 46.85 s, mean 44.0 s,
23.4 minutes in all) and `readability.py` over both results files. The one
miss in tool selection is still thin-1. The gold-set results file quotes CNA
text and is kept out of git with the earlier runs; its summary and the
multi-turn results are committed.

Of the seven dashboard questions (`data/run/overnight/ui_final3.json`), one
answer was flagged: asked whether UOB's net interest margin sentiment had
changed, the model gave the month's change as +0.17 where the tool returned
0.158, and the figure check marked it. Two errors the checks don't read were
also seen: an answer said its two quotes came from "bank results reports and
a Reddit post" when both were results reports, and one called topics with
"slightly positive" scores the ones "dragging down" the bank. The checks read
quotes and figures, not the model's own descriptions.
