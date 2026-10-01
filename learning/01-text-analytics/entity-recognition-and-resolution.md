# Entity recognition and resolution

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [text-preparation-and-sentence-segmentation](text-preparation-and-sentence-segmentation.md).

---

## 1. Why it matters here (Understand)

Every sentence in the index is attributed to a bank. If "UOB Kay Hian
raised its target for OCBC" counts towards UOB, a broker's opinion becomes
UOB's sentiment. Alias matching, which attributes today, can't tell the
bank from things that share its name. Bank entity recognition is the
project's third text-mining task (PLAN D3, DESIGN decision 18).

---

## 2. The concept (Understand / Apply)

**Named entity recognition (NER)** finds spans naming things and gives each
a type (ORG, PERSON, PRODUCT, …). spaCy's `en_core_web_sm` does it with a
statistical model trained on general English.

**Entity resolution** (linking) maps each found span to an entry in a
known list, or to "none of these": here DBS, OCBC, UOB or not the bank.

**An entity ruler** is a list of token patterns placed *before* the
statistical NER: names the ruler marks are kept, and the model labels the
rest. It is how domain knowledge enters a general model without
retraining.

**A gazetteer** is a plain list of names matched in the raw text; here a
fallback for names the tokenizer has glued to punctuation.

**Evaluating at the right unit.** The decision that matters is which banks
a sentence is about, so the gold set is a set of banks per sentence, scored
with micro precision, recall and F1 over (sentence, bank) pairs, plus the
share of sentences whose whole set is right.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| alias matching, the baseline | `ingest/base.py` `detect_banks` |
| ruler, model, resolution table, fallback | `preprocess/bank_ner.py` |
| the blank gold sheet (201 sentences) | `data/labeled/ner/gold_sheet.csv` |
| results so far | `docs/evidence/bank-ner-2026-10-01.md` |

---

## 4. Analyze

**What the pretrained model alone gets wrong on this corpus.** In "UOB Kay
Hian raised its target for OCBC" it tags "Kay Hian" as a PERSON; in "DBS
Vickers charges 0.12%" it keeps only "Vickers"; it misses lowercase "dbs"
in Reddit text. Each failure has a different cure: a ruler pattern for the
first two, case-insensitive patterns for the third.

**Recognition and resolution are separate decisions.** Finding "DBS
Vickers" as one ORG is recognition; deciding it is "not the bank" is
resolution, a policy the team set (PLAN section 7). Keeping the policy in a
table (`RESOLUTION`) means changing it is one line, and the gold set can be
scored under either reading.

**Where it changes attribution.** On all 44,345 sentences, NER and alias
matching name a different set of banks for 714 (1.6%): DBS Vickers 456,
UOB Kay Hian 132 (including "KayHian" and "UOBKH"), POSB 88, Great Eastern
19, Bank of Singapore 9, tickers in portfolio lists 9, Aston Martin 1.

**A failure found by looking at the disagreements.** A first version
dropped 18 OCBC sentences such as "www.ocbc.com" and "OCBC+Sti": the
tokenizer had made one token of the name and its punctuation, so neither
the ruler nor the model saw "OCBC". The gazetteer fallback recovers them.

---

## 5. Evaluate

The design suits the problem: a handful of known confusions, a closed set
of three targets, and no labelled data to train a model. A ruler plus a
resolution table is transparent and testable; a fine-tuned NER model would
need hundreds of span-labelled sentences for little gain on three names.

What the evidence does not yet show: accuracy. The 714 changes are where
the methods disagree, not where NER is right. That needs the gold set,
which is weighted towards the hard cases (so its accuracy will be lower
than on random text, and should be reported per stratum).

The contestable call is DBS Vickers (456 sentences): PLAN groups it with
the brokers, but it carries DBS's name and the annotators treated its
trades as banking. When the opposite rule is right: if the index is meant
to capture sentiment about anything DBS sells, Vickers is DBS.

---

## 6. Create

**Exercise (≈ 60 minutes).** Measure how much attribution policy moves the
headline. Using `data/preview/ner_corpus_diff.csv` (from `python -m
preprocess.bank_ner corpus-diff`), recompute DBS's all-time sentiment from
`aspect_sentiment` with and without the 456 Vickers sentences.

*Expected outcome:* a number for the size of the decision. If the headline
moves by less than its own week-to-week noise, the Vickers call matters
for evidence lists but not for the score.

---

## 7. Self-check

1. Why place the ruler before the statistical NER rather than after?
2. What is the difference between recognising "DBS Vickers" and resolving
   it?
3. Why does the gold set over-sample hard cases, and what must the report
   do because of that?
4. Why was the gazetteer fallback needed, given the ruler?
5. The corpus diff shows 714 changes. Why isn't that an accuracy figure?

<details>
<summary>Answers</summary>

1. So the model sees the names already marked and labels around them;
   after, the model's wrong spans ("Kay Hian" as PERSON) would already exist.
2. Recognition finds the span and its type; resolution decides which
   real-world entity (or none) it refers to.
3. To measure the cases alias matching gets wrong with enough examples;
   the report must give accuracy per stratum, not one overall number
   presented as typical.
4. The tokenizer joins some names to punctuation ("UOB$"), so no token
   equals the name and token patterns can't match.
5. It counts disagreements between two methods; whether NER or alias
   matching is right on each needs the gold set.

</details>

---

## 8. Sources

**Repository**

- `preprocess/bank_ner.py`, `ingest/base.py`, `tests/test_bank_ner.py`
- `docs/evidence/bank-ner-2026-10-01.md`, DESIGN decision 18, PLAN section 7

**Measured in this repository (2026-10-01)**

- The 714-sentence diff and its causes, from `corpus-diff`.

**External**

- spaCy documentation, `EntityRuler` and the `en_core_web_sm` pipeline
  (spacy.io). **Not fetched during this pass.**

**Not verified**

- NER accuracy: the gold set is not yet labelled.
