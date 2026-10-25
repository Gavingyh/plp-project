# News filter: what happens to one article

The order of decisions `ingest/news_filter.py` makes for each news article, and the reason recorded at each exit. For the report's data-cleaning section and for anyone auditing `data/news_flagged.csv`.

```mermaid
flowchart TB
  accTitle: News filter decisions
  accDescr: An article already stored is skipped. Otherwise non-bank phrases are masked; an article naming no bank is rejected; a duplicate is rejected, unless the article has full text and the only earlier copy is a bare headline; otherwise it is kept, with flags for masked phrases and possible bank commentary.

  a(["News article"])
  stored{"Already stored,<br/>or kept earlier this run?"}
  skip["Skipped, not logged:<br/>counted as already stored"]
  mask["Mask phrases that aren't the bank:<br/>market notes, brokers, venues,<br/>research desks, rating calls"]
  named{"Still names DBS,<br/>OCBC or UOB?"}
  why{"Were phrases masked?"}
  r1["Rejected: false_positive_only"]
  r2["Rejected: no_bank_mention"]
  dup{"Same URL, or a headline 90% similar<br/>within 3 days?"}
  r3["Rejected: duplicate"]
  fuller{"This one has full text,<br/>and every earlier copy<br/>is a bare headline?"}
  f3["Flagged, kept:<br/>kept_full_text_over_headline"]
  keep["Kept: bank set from the text,<br/>MULTI if more than one"]
  f1["Flagged, kept:<br/>kept_with_false_positive_phrase"]
  f2["Flagged, kept:<br/>kept_possible_bank_commentary"]
  ins(["Inserted into documents"])

  a --> stored
  stored -- yes --> skip
  stored -- no --> mask --> named
  named -- no --> why
  why -- yes --> r1
  why -- no --> r2
  named -- yes --> dup
  dup -- yes --> fuller
  fuller -- no --> r3
  fuller -- yes --> f3 --> keep
  dup -- no --> keep --> ins
  keep -. "if a phrase was masked" .-> f1
  keep -. "if the headline credits the bank<br/>at the end, e.g. ': UOB'" .-> f2
```

Rendered for the report: [SVG](img/11-news-filter.svg) · [PNG](img/11-news-filter.png)

## What this shows and doesn't show

Every rejection and every flagged keep writes a row to `data/news_flagged.csv` with its reason,
so nothing is dropped silently. Masking comes first so that "UOB Kay Hian upgrades DBS"
counts as a DBS article rather than being rejected or counted as UOB. Market notes (a
currency or macro headline ending in a bank's name) and rating calls are masked unless the
headline also mentions the bank's own results, an award or a launch. The two flags don't
stop an article being kept; they mark it for a person to look at. A full-text article
(CNA) is kept even when Google News already stored the same story, because Google News
stores the headline alone; the headline isn't counted twice, because preprocessing drops
any sentence whose normalised text is already stored. The rules are described
in full, with counts, in [../news-data.md](../news-data.md).

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| already stored | `ingest/news_filter.py:273` | `if d["doc_id"] in index.doc_ids:` |
| mask, then find banks | `ingest/news_filter.py:276` | `banks, phrases = mentioned_banks(doc_text(` |
| masking function | `ingest/news_filter.py:139` | `def mask_false_positives(text: str)` |
| market notes masked first | `ingest/news_filter.py:145` | `found.append("market note")` |
| exemptions for the bank's own news | `ingest/news_filter.py:144` | `and not _OWN_PERFORMANCE.search(text) and not _MARKET_NOTE_EXEMPT.search(text)):` |
| brokers, venues, research, rating calls | `ingest/news_filter.py:76` | `FALSE_POSITIVES = [` |
| no bank: which reason | `ingest/news_filter.py:282` | `reason = "false_positive_only" if phrases else "no_bank_mention"` |
| duplicate check | `ingest/news_filter.py:288` | `dup = index.find_duplicate(` |
| full text over a bare headline | `ingest/news_filter.py:290` | `# Full text beats a headline-only copy, unless a fuller copy is also stored.` |
| flag: full text kept | `ingest/news_filter.py:294` | `"reason": "kept_full_text_over_headline"` |
| headline not counted twice | `preprocess/pipeline.py:121` | `if h in seen_hashes:` |
| 90% headline similarity | `ingest/news_filter.py:56` | `TITLE_SIMILARITY = 0.90` |
| within 3 days | `ingest/news_filter.py:57` | `DUP_WINDOW_DAYS = 3` |
| bank from the text, MULTI | `ingest/news_filter.py:302` | `d = {**d, "bank": banks[0] if len(banks) == 1 else "MULTI"}` |
| flag: masked phrase | `ingest/news_filter.py:306` | `"reason": "kept_with_false_positive_phrase"` |
| flag: possible commentary | `ingest/news_filter.py:309` | `"reason": "kept_possible_bank_commentary"` |
| every decision logged | `ingest/news_filter.py:314` | `_append_flagged(flagged)` |
