# How sure the index's scores are (14 Oct 2026)

**What this is.** The index gives each bank, aspect and time window a score
between -1 and +1, and the report compares those scores. Until now no
interval had been computed for any of them, so the report could not say
which differences are real. This note measures two kinds of uncertainty
separately, on the submitted database: sampling (the corpus is one sample of
what was written) and measurement (a model, wrong on about three sentences in
ten, assigns the labels). It also tests how much the index's own constants
move the headline.

**Result.** Sampling uncertainty is small for the all-time headlines (about
plus or minus 0.01) and large for the recent windows (plus or minus 0.07 to
0.20). UOB's all-time score is lower than both other banks' with sampling
taken into account; DBS's lead over OCBC is not established. The model shows
no significant overall bias against people's labels, but that check is
coarse (plus or minus 0.06 on 399 sentences), so measurement, not sampling,
is the larger uncertainty. Changing the index's constants moves no all-time
headline by more than 0.011 and leaves the three banks in the same order.

Scripts and output: `data/eval/index-uncertainty/` (`intervals.py`,
`results.json`, `output.txt`, `sensitivity.py`, `sensitivity.txt`).

## Sampling: bootstrap intervals

Each score was recomputed on 2,000 resamples of its own sentences, drawn
with replacement, using the index's formula (each sentence +1, 0 or -1,
weighted by the model's confidence and by source, the mean shrunk by
n/(n+5)). The recomputed point scores equal the stored index in all 42
cells checked. The interval is the middle 95% of the resamples.

| Bank | All time | 30 days | 7 days |
|---|---|---|---|
| DBS | 0.143 (0.134 to 0.152), 24,978 sentences | 0.044 (-0.030 to 0.119), 371 | 0.168 (0.026 to 0.323), 90 |
| OCBC | 0.129 (0.113 to 0.145), 7,774 | 0.271 (0.149 to 0.391), 115 | 0.149 (-0.051 to 0.342), 42 |
| UOB | 0.107 (0.095 to 0.118), 13,092 | 0.185 (0.096 to 0.278), 136 | 0.275 (0.142 to 0.411), 60 |

Gaps between banks, with independent resamples for each bank:

| Window | Gap | Point | 95% interval | Share of resamples above zero |
|---|---|---|---|---|
| all time | DBS - OCBC | 0.015 | -0.004 to 0.032 | 94% |
| all time | DBS - UOB | 0.036 | 0.021 to 0.050 | 100% |
| all time | OCBC - UOB | 0.022 | 0.003 to 0.041 | 99% |
| 30 days | DBS - OCBC | -0.227 | -0.362 to -0.084 | 0.1% |
| 30 days | DBS - UOB | -0.141 | -0.255 to -0.022 | 0.9% |
| 30 days | OCBC - UOB | 0.086 | -0.065 to 0.242 | 86% |
| 7 days | every gap | | each interval contains zero | 14% to 57% |

- **All time, UOB is lowest; DBS against OCBC is open.** Both gaps to UOB
  exclude zero. DBS's lead over OCBC does not, and it reversed when the
  sentiment model changed, so the report should not rank the two.
- **Over 30 days, DBS is below both others**, by more than sampling explains.
  That is a statement about the four weeks to 25 Sep 2026 on 371, 115 and
  136 sentences.
- **Seven-day figures are close to uninformative.** Intervals 0.27 to 0.39
  wide on 42 to 90 sentences, and every gap between banks is within them.
- **Per aspect,** intervals run from plus or minus 0.014 (DBS retail
  banking, 9,099 sentences) to plus or minus 0.146 (UOB dividends, 62
  sentences). The small aspect cells can be read for direction at best: OCBC
  on the macro environment, -0.162, has an interval of -0.304 to -0.018.
- **What the bootstrap does not cover.** It treats sentences as independent,
  while sentences from one Reddit thread or one report are not, so the
  intervals are, if anything, too narrow. And it takes the model's labels as
  given; the next section is about that.

## Measurement: the model against people

The index cannot be recomputed with people's labels, because people labelled
only 2,075 sentences. The closest check is on the 399 test sentences people
labelled and no model trained on: the net balance (share positive minus
share negative) by the served model's labels against the same by people's,
with a paired bootstrap of 2,000 resamples.

| Test sentences | n | People | Model | Difference (95% interval) |
|---|---|---|---|---|
| all | 399 | 0.185 | 0.153 | -0.033 (-0.095 to 0.030) |
| Reddit | 184 | 0.011 | 0.011 | 0.000 (-0.103 to 0.103) |
| earnings | 79 | 0.544 | 0.557 | 0.013 (-0.101 to 0.127) |
| broker research | 100 | 0.190 | 0.090 | -0.100 (-0.220 to 0.020) |

- **No significant bias overall.** The model is slightly less positive than
  people (by 0.033) but the interval includes zero.
- **The check is coarse.** Its interval is about plus or minus 0.06 wide,
  six times the sampling interval of an all-time headline. A bias of that
  size would be invisible here and would matter for gaps of 0.01 to 0.04
  between banks. Measurement is therefore the larger source of uncertainty.
- **It would cancel in the gaps if it were the same for every bank.** It
  would differ between banks only through their mix of sources. On Reddit,
  which is 56% of the corpus, the model matches people exactly; the largest
  difference is on broker research (-0.100, interval just including zero),
  which is 641 sentences, 1.4% of the corpus.
- The net balance is not the index's formula (it has no confidence or source
  weights and no shrinkage), so this is an approximation of the index's
  bias, not a measurement of it.

## The index's constants

The index weights a news sentence 1.5 times a Reddit or earnings sentence,
shrinks every score by n/(n+5), and weights each label by the model's
confidence. Each choice was changed in turn:

| Variant | DBS all time | OCBC all time | UOB all time | DBS 30d | OCBC 30d | UOB 30d |
|---|---|---|---|---|---|---|
| as stored | 0.143 | 0.129 | 0.107 | 0.044 | 0.271 | 0.185 |
| every source weighted 1.0 | 0.147 | 0.121 | 0.104 | 0.072 | 0.257 | 0.173 |
| no shrinkage | 0.143 | 0.129 | 0.107 | 0.044 | 0.283 | 0.192 |
| shrinkage 20 | 0.143 | 0.128 | 0.107 | 0.042 | 0.241 | 0.167 |
| no confidence weighting | 0.150 | 0.135 | 0.118 | 0.057 | 0.287 | 0.196 |

- No all-time headline moves by more than 0.011, and the order DBS, OCBC,
  UOB holds in every variant.
- The shrinkage matters only for small cells, as intended: it changes
  nothing at 7,774 sentences and up to 0.042 at 115.
- The news weight moves OCBC and DBS in opposite directions (OCBC has the
  most news relative to its size), by up to 0.028 over 30 days. Its value,
  1.5, is a judgement, not an estimate; the evidence above says the
  conclusions do not depend on it.
