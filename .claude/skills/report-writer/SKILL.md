---
name: report-writer
description: Write or revise prose for the project report (docs/report/), docs, evidence notes, team pages and summaries so that a reader who was not in the session can follow it, nothing is longer than it needs to be, and report sections analyse and evaluate instead of only describing. Use whenever drafting or editing a report section, a brief, a summary for the team, or any doc a person will read.
argument-hint: "[file or section to write or revise]"
---

Write or revise: $ARGUMENTS

The two faults to avoid are opposite, so check for both: text that is longer
than the reader needs, and text that leaves out what the reader needs to
follow it. `CLAUDE.md` ("Writing docs") still applies in full: every number
from a file or a command, plain English, no em dashes, no code labels,
absolute dates.

## 1. Fix the reader before writing

Write down, for yourself, one line each:

- **Who reads it.** For the report: an examiner who knows text mining but has
  never seen this code, this session or the team's chat. For a team page: a
  teammate who missed the last week.
- **What they must know or decide when they finish.** If you can't say it in
  one sentence, the section is not ready to be written.

## 2. Give context first, once

A reader is lost when a paragraph starts with the detail. Open each section
and each paragraph that changes subject with the frame, then the detail:

1. What this is about and why it matters here (one sentence).
2. The finding or decision, with its figure.
3. The reason or evidence.
4. What follows from it.

Checks for missing context:

- Every term, file, dataset, model or number is introduced the first time it
  appears: what it is and where it came from. "The 299 test rows" is unclear;
  "the 299 held-out rows the team labelled by hand, which no model saw in
  training" is not.
- Nothing refers to the session: no "as discussed", "the earlier run", "the
  fix", "the new rule" without saying which.
- A figure never stands alone. Give what it measures, on which rows, and what
  it is compared with.
- The first paragraph of a section could be read on its own and still tell
  the reader what the section concludes.

## 3. Cut what the reader doesn't need

- Say each thing once. Delete a sentence that repeats the heading, the
  previous sentence or the table beside it.
- Lead with the result. Process (what was tried, in what order) goes after
  it, and only as much as the reader needs to trust the result.
- Delete openers and closers that carry nothing: "it is worth noting",
  "in summary", "overall", "this section describes".
- One idea a sentence; a paragraph of more than five sentences is usually
  two paragraphs or a table.
- Put comparisons of three or more items in a table and discuss the pattern
  in the prose, not the cells.
- Don't hedge twice. One "about" or "suggests" where the evidence is weak;
  none where it is measured.
- Leave out the dates on which work was done ("on 12 October the corpus was
  re-scored", "the 6 Oct run"). The reader of a report does not care when a
  task happened. Keep a date only when it is a fact about the data (the
  period a corpus covers, the date a survey was run, the day the data runs
  to) or a deadline the team has to meet. Name a run by what it was, not
  when: "before the code checks", "on the re-scored database".

Cutting must not remove context. After cutting, reread section 2's checks.

## 4. Reach Bloom level 4 (analyse) and above in the report

A report section that only lists what was built and what was measured sits at
levels 1 to 3 and loses marks. Each results, design and discussion section
must analyse (level 4), and the evaluation and conclusion must also evaluate
(level 5).

| Level | What the writing does | Example from this project (figures from `docs/evidence/model-rerun-2026-10-11.md`; recheck before reuse) |
|---|---|---|
| 1 Remember | states a fact | "The model scored 0.670 macro-F1." |
| 2 Understand | explains what it means | "Macro-F1 averages the three classes equally, so a rare class counts as much as a common one." |
| 3 Apply | says what was done with a method | "We fine-tuned FinBERT on (sentence, aspect) pairs and averaged three seeds." |
| **4 Analyse** | breaks the result down, compares, finds the cause | "The gain over base FinBERT (0.571) comes from negative sentences: recall on them rose from 0.21 to 0.59, paid for with neutral recall, which fell from 0.91 to 0.73. Base FinBERT was trained on formal financial news, so it reads most customer complaints as neutral; fine-tuning moves that boundary." |
| **5 Evaluate** | judges against a criterion, weighs limits, justifies a choice | "The lead is real but narrow: on five-fold cross-validation the adapted encoder beat plain fine-tuning by 0.014 (p = 0.016), and the training labels came from an LLM, not people. We chose it because the rule was fixed before the test rows were scored, but a second human-labelled test set would be needed to claim more." |
| 6 Create | proposes something new from the findings | "Since errors concentrate in sarcastic forum posts, the next step with most to gain is a targeted labelling round on those, not a larger model." |

For every result or design choice in the report, the text should answer:

- **Compared with what?** A baseline, an alternative considered, or the
  figure before the change.
- **Where does the difference come from?** By class, source, bank, aspect or
  error type, not only the total.
- **Why?** The cause, with the evidence for it, and say so when the cause is
  a guess.
- **How sure?** Sample size, spread across seeds, a significance test, and
  what could make the result wrong (threats to validity).
- **So what?** What it decided, what it means for the index a user sees, and
  what it does not show.

Use verbs that fit the level: compare, contrast, break down, attribute,
explain why, trace, weigh, justify, judge. "We used", "we built" and "the
result is" on their own are a sign the paragraph stops at level 3.

Conclusions must be no stronger than the data. A modest lead is written as a
modest lead.

## 5. Before handing over

- Read the piece as the reader from step 1, top to bottom, without the
  session in mind. Mark each place you would have to stop and ask; fix those.
- Check each figure against its source file and name the source.
- For a report section, mark each paragraph with its Bloom level. If no
  paragraph in a results or discussion section reaches 4, it is not done.
- State the word count against the section's budget if there is one. Count
  only the text that will be submitted: warning boxes and other notes to
  the team are not part of it.
- For a frozen or published doc, run the `auditor` agent on it; for a report
  section, the `examiner` agent grades it against the module's requirements.
