# Rater instructions: which banks a sentence is about

You are labelling sentences for a study of Singapore's three listed banks
(DBS, OCBC, UOB). For each sentence, decide which of the three it is about
as a bank. The rules are the project's (`data/labeled/ner/README.md`,
PLAN section 7, DESIGN decision 18), quoted.

## Rules for this task

- Read only this file and the input file named in your task. Do not open
  any other file in the repository: other files hold labels or model
  predictions for these sentences.
- Judge each sentence yourself. Do not write code to classify, and do not call
  any model, API or search.
- Every row gets an answer.

## The rules

- POSB counts as DBS. Bank of Singapore and Great Eastern count as OCBC.
- UOB Kay Hian and DBS Vickers are brokers: they do NOT count as the bank.
- "Aston Martin DBS" and medical DBS (deep brain stimulation) are not banks.
- A bank named only as a place or a payment rail ("paid via DBS PayNow")
  still counts: this task is about which bank is named, not about relevance.
- A sentence can name none, one, two or all three.

## Output

Write the output file named in your task: one line per input row, in
input order, exactly

{"sentence_id": "<id>", "banks": ["DBS", "OCBC", "UOB"]}

listing only the banks the sentence is about, in that order, or `[]` for
none. No other fields, no commentary lines.
