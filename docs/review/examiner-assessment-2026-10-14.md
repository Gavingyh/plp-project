# Examiner assessment of the report draft (14 Oct 2026)

The `examiner` agent graded `docs/report/report.html` against the module's
requirements (`.project-context/course-content/course-context.md`, section
1). It has no official rubric, so the band is an estimate. The draft was
graded before the afternoon's corrections; the team page "Report Draft
Grading" shows which points have been acted on.

## Band

Credit, high end, as drafted. Sections 2 to 4 at distinction level; held
down by the empty individual contributions (section 7) and the unfinished
conclusions (5) and GenAI declaration (8).

## Required parts at grading

- Business problem (1): present; survey figures unchecked.
- Datasets (2): present; which dataset is submitted undecided.
- Solution approach (3): partly; no architecture figure, no table mapping
  components to course modules.
- Test results (4): present; no evidence from real users for the chatbot.
- Conclusions (5): partly; not yet the team's, "what we'd do differently"
  missing.
- References (6): partly; unverified, not cited in the text, surveys and
  data-source terms missing.
- Individual contributions (7): missing.
- GenAI declaration (8): partly; model versions not named, pros and cons
  written by the tool about itself.

## Analysis and evaluation

Strong (Bloom 4 and 5): 2.1, 2.2, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5. Stops at
description: 3.6 (no reason or sensitivity test for the index's constants),
4.6 (lists checks), 1 (promises trend analysis that no section gives), 4.1
(no error examples or confusion matrix).

## Likely examiner questions, most likely first

1. Is the model just imitating the LLM that made its training labels?
2. Did the test set influence which model was chosen?
3. Does the index agree with anything external (analyst consensus, prices,
   events)?
4. How certain is the DBS and OCBC gap?
5. What did each member do?
6. Were the prompt and checks tuned on the same 32 questions?
7. Why build bank entity recognition and not apply it?
8. Do users trust or use the chatbot?
9. Why one aspect per sentence?
10. Why a news weight of 1.5 and a shrinkage constant of 5?

## Unconvincing, overstated or inconsistent

1. Section 3.5 said the test result could not influence the model choice; the
   rule chose on test macro-F1.
2. Section 4.4 said every bank's all-time score rose; OCBC's fell.
3. Table 8 compared what the model wrote with what the reader sees after
   code removal.
4. Table 8's first column showed advice declined 8 of 8, but the advice
   guard was already code; the prompt alone managed 2 of 7.
5. p = 0.016 treats 15 folds that share rows as independent.
6. Section 4.3's opening was garbled; its reference answers are the LLM
   rater's where the plan promised a human gold set.
7. "A small language model fixed both" overstated the evidence search.
8. "Not distinguishable from chance" should read "not significant".
9. Gemini, verified as a backend, was not in the GenAI table.
10. The LLM judge's failure was not reported.
11. No figures in the report.

All eleven were corrected in the draft on 14 Oct (HANDOFF, "Three
improvements before submission"). Also raised: the "Fine-tuning lead" claim
in `CLAUDE.md` quotes the earlier model's figures (the owner's file).

## Length

About 6,900 words outside the warning boxes at grading, estimated 16 to 17
pages; 19 to 21 pages expected once the team's sections are in. Suggested
cuts of about 1,000 words: the wealth-wording paragraphs in 4.2, the
per-source and aspect-dependence paragraphs in 4.4, the labelling history in
2.2, section 4.6 folded into 2.3, and figures repeated in section 5.
