# A fix for answers that report the wrong period (14 Oct 2026)

**What this is.** One gold-set question, "What is UOB's sentiment on net
interest margin in the last 7 days?", was answered wrongly in every run on
the re-scored database: the 7- and 30-day windows hold too few sentences, the
trend tool fell back to the all-time figure with a note saying so, and the
model reported that figure as the last 7 days'. The quote and figure checks
pass such an answer, because every number in it came from a tool. This note
records the fix, what it did and did not cure, and two related faults found
while testing it.

**Result.** The question is now answered correctly: the chatbot says there is
no 7-day figure and labels the all-time and monthly figures as what they are.
No automated check got worse. Two related faults remain: a "this week"
question about a trend is still answered with a comparison of two months, and
a "past month" question gets the all-time figure, because the sentiment tool
has no time-window option.

## The change

In `chatbot/tools.py`, `chat_get_trend`, when the recent windows are too
thin (the API's `/sentiment/trend` is unchanged):

- The all-time figure moves from the top of the result to a key named
  `all_time_not_recent`.
- The result now opens with `recent_windows`, a sentence that states how
  many sentences the 7- and 30-day windows hold, that there is no figure for
  those periods, and which months the monthly comparison covers, for example
  "The monthly figures below are for February 2026 and August 2025, not for
  the last 7 or 30 days."

The first version did only the first part. In the gold set the model then
reported the latest month's figure (February 2026, -0.03 on 8 sentences) as
the last 7 days'. Naming the months in a sentence placed first is what
worked.

## Testing

Three thin-data questions, asked three times each in fresh conversations
(`data/eval/chatbot_thin_probe_trendfix2.jsonl`), then the full gold set and
the conversations (`data/run/eval-2026-10-14c/run.sh`).

| Question | Before | After, 3 tries |
|---|---|---|
| UOB, net interest margin, "in the last 7 days" | all-time figure given as the week's, every run | says no 7-day figure, 3 of 3 |
| OCBC, management guidance, "trending this week" | a two-month comparison given as "this week" | the same, 3 of 3, though each answer also says there is too little recent data |
| OCBC, dividend policy, "over the past month" (not in the gold set) | not asked before | the all-time figure (138 sentences) given as the past month's, 3 of 3 |

Gold set and conversations, before and after the fix, on the same database:

| | Before the fix (`rescored2`) | After (`trendfix2`) |
|---|---|---|
| Tool selection | 23/24 | 23/24 |
| Behaviour (advice declined, no data said) | 8/8 | 8/8 |
| Citation fabrication flagged | 0/32 | 0/32 |
| Answers with a figure no tool returned | 0/32 | 0/32 |
| Evidence written without a search, removed | 4/32 | 3/32 |
| Multi-turn turns correct | 9/9 | 9/9 |
| Median seconds per question | 40 | 61 |

The one tool-selection miss is still the 7-day question: the gold set
expects the sentiment tool, and the model calls the trend tool. Its answer
is now right. The slower answers are the laptop: this run followed two
other local-model jobs within the hour.

## The two faults that remain

- **"This week" trend questions.** When the recent windows are thin, the
  trend tool falls back to the latest two months. The model opens with
  "trending up this week" and adds that there is too little recent data.
  The figures are right and labelled with their months; the opening phrase
  is wrong.
- **"Past month" questions.** The sentiment tool's schema offers the model
  no time window (`get_sentiment` accepts one in Python, but the model is
  never told), so every sentiment answer is all-time, whatever period was
  asked. This gap has been recorded since September (HANDOFF, "The
  conversation state's time window is never set"; diagram 15) as a decision
  to make: expose a window argument, or stop claiming the chatbot tracks
  the time window. The gold set has no question that tests it.
