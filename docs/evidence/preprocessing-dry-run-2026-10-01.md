# Preprocessing: how much of the text is debris?

A dry run of a filter for extraction debris, to answer whether better
preprocessing would improve the sentiment model. Run 2026-10-01 on the
44,345-sentence corpus and the 1,277 labelled rows. Nothing was changed.

```bash
.venv-plp/bin/python3 -m preprocess.fragments
```

## Answer: very little, and the obvious rules remove real sentiment

Rules tried on the labelled rows before settling on the filter:

| rule | corpus flagged | labelled rows flagged | labelled rows carrying sentiment |
|---|---|---|---|
| fewer than 6 words | 2,832 | 34 | **18** (4 negative, 14 positive) |
| at least as many number tokens as words | 152 | 4 | 3 positive |
| over half the tokens one or two letters long | 42 | 0 | — |

"Fewer than 6 words" would delete "Cards were strong at 17%." and "bought DBS
at $37.3 this morning": short is not the same as empty. The two looser rules
caught ordinary sentences ("I thought my $2m+ in DBS is a problem.") and
Reddit users' own arithmetic ("SSB 3.3% $200k = $6.6k, UOB 4% $150k = $6k,
$150k T-bills 3.74% = $5,610.").

## The filter kept (`preprocess/fragments.py`)

Only PDF-extracted text (`earnings`) is checked, sentences under 8 tokens are
never flagged, and a sentence is flagged when:

- **garbled**: more than 40% of its tokens are single letters
  ("T ra n s itio n a l fin a l B a s e l III re fo rm s"), or
- **table**: it has at least 1.5 number tokens per word
  ("Transaction services1 451 473 (5) 456 (1) Fee and commission income 2,007 1,939 4").

| | sentences | flagged | share |
|---|---|---|---|
| corpus | 44,345 | **98** (69 table, 29 garbled), all earnings | 0.22% |
| labelled | 1,277 | **2** (one positive, one neutral) | 0.16% |

One of the two labelled rows is a table row with a headline fused in ("9M23
Core net profit up … all-time high fee income", labelled positive), so even
this filter would cost a little signal.

## What it means for the model

Debris is about 1 in 450 sentences and 2 labelled rows, so removing it can't
move macro-F1 measurably. The model's errors are elsewhere: neutral sentences
read as positive or negative, implicit sentiment missed, and Reddit
(`finetune-fixes-2026-10-01.md`). Two preprocessing steps remain worth
having for the corpus, not the model: this filter applied before scoring
(0.22% fewer junk rows in the index), and the "not about the bank" relevance
question (PLAN decision O5), which this dry run doesn't address.
