# Bank NER gold set

For each sentence, write in `gold_banks` which of DBS, OCBC and UOB the
sentence is about as a bank, separated by `;` (e.g. `DBS;UOB`), or leave it
empty if it is about none of them. Then put your role in `annotator`.

Rules (PLAN section 7, DESIGN decision 18):

- POSB counts as DBS. Bank of Singapore and Great Eastern count as OCBC.
- UOB Kay Hian and DBS Vickers are brokers: they do NOT count as the bank.
  If the team decides DBS Vickers should count as DBS, change the `vickers`
  line in `preprocess/bank_ner.py` RESOLUTION and say so in `notes`.
- "Aston Martin DBS" and medical DBS (deep brain stimulation) are not banks.
- A bank named only as a place or a payment rail ("paid via DBS PayNow")
  still counts: this task is about which bank is named, not about relevance.

`case` is the sampling stratum, not a hint about the answer. Don't look at
what any tool predicts before you finish.

Score it with:

    .venv-plp/bin/python3 -m preprocess.bank_ner evaluate --gold data/labeled/ner/gold_sheet.csv
