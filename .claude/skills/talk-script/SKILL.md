---
name: talk-script
description: Write or revise the spoken script and slide text for a presenter's section of the project video, so that it fits its time, makes one argument, reaches Bloom level 4 (analyse) in speech and uses only figures the final report states. Use when drafting, timing, tightening or reviewing a video script, speaker notes or a slide's on-screen text.
argument-hint: "[section, slides or script file to write or revise]"
---

Write or revise: $ARGUMENTS

A script is heard once, at speaking pace, by an examiner who cannot scroll
back. Write for the ear. `report-writer` sets the rules for the report;
this skill adapts them to speech. `CLAUDE.md` ("Writing docs") still
applies: every number from a source, plain English, no em dashes, no code
labels.

## 1. Fix the section before writing

Write down, for yourself, one line each:

- **Time and slides.** The section's length and slide range, from the team
  script (`working-folder/v2/BankPulse-Team-Script.docx` while it exists).
- **The one claim.** The sentence the examiner should be able to repeat
  after the section. Every slide supports it; a slide that doesn't is cut.
- **The handover.** The last line of the previous speaker and the first
  line of the next, so the section joins the video without a restart.

## 2. Budget the words

- About 130 spoken words a minute. A demo minute where the screen does the
  work carries about 60 words of narration.
- Give each slide a budget in seconds and words before writing it, and
  report the actual count against it after.
- Over budget: cut a point, not the pauses. Never solve time by speaking
  faster.

## 3. Reach Bloom level 4 in speech

Description ("the chatbot has six tools") is level 1 to 3 and earns little
on its own. Each content slide must do at least one of these, out loud:

| Move | What it sounds like |
|---|---|
| Compare | "Against the local model, the hosted one was about three times faster, but speed alone didn't make it right." |
| Explain why | "The checks missed those answers because they compare numbers, and the error was in how a correct number was described." |
| Name the trade-off | "Stripping an unsupported quote makes the answer safer and sometimes shorter than the user wanted." |
| Say where it fails | "The checks can't judge a paraphrase. That is what the human rating is for." |
| Judge | "So the checks reduce one kind of error; they don't prove an answer is faithful." |

The examples are illustrative; take every figure from the final report and
recheck it before use. The strongest material is usually a failure that
was measured, explained and fixed: it shows analysis and honesty at once.

## 4. Write it to be spoken

- Sentences of 20 words or fewer; one idea each. Read each aloud.
- No brackets, no semicolons that a voice can't carry, no lists read item
  by item.
- No file names, run names, flags or code terms on the voice track
  (`luna_shown_v2`, `strip mode`, `CHATBOT_ENFORCE_EVIDENCE`). Say what the
  thing does instead.
- At most two figures a slide, rounded as people say them ("seven in
  ten", "about three times faster"). The exact figure can sit on the slide.
- Signpost: say where the section is going in one line at the start, and
  what it showed in one line at the end.
- First person and active voice ("I built", "we found"), in the speaker's
  own register. Keep the team script's wording where a teammate refers to
  this section.

## 5. Slides cue, the voice explains

- On-screen text under about 25 words a slide: a claim as the title, then
  the one figure or picture that proves it.
- The script never reads the slide. If the voice and the slide say the same
  sentence, change the slide.
- Every chart or table shown is one the report contains, so the two agree.

## 6. Plan the demo beats

For each live moment, mark in the script:

- `ON SCREEN`: what to type or click, word for word, and where to point.
- `SAY`: the narration over it, within the demo word rate.
- `IF IT FAILS`: the fallback (a pre-recorded clip or a screenshot) and the
  one line that covers the switch.

Choose demo questions whose answers are known from a recent run, and one
that shows a limit working (a declined advice question, a withheld quote).

## 7. Sources

- Every figure spoken or shown must appear in the final report. If it
  isn't there, either add it to the report edits or drop it from the
  script, so the video can't contradict the report.
- After each slide, add a `SOURCE` line (not spoken) naming the report
  section or table.

## 8. Before handing over

- Give the word count for each slide and the total against the budget, and
  the estimated time.
- Mark each content slide with the Bloom move it makes. If none reaches
  level 4, it is not done.
- Read the script as the examiner hears it: without the slides' detail,
  once, at pace. Mark every place a listener would lose the thread.
- Run the `examiner` agent on the script, and list the three questions it
  is most likely to ask about the section, each with a two-sentence answer
  the presenter can give.
