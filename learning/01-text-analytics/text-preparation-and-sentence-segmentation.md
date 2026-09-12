# Text preparation and sentence segmentation

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

The sentence is this system's unit of analysis, so sentence segmentation is
not a preprocessing detail — it is the step that creates the objects
everything else operates on. A bad split produces a fragment that gets
embedded, assigned an aspect, scored, and cited to a user as evidence.

The corpus makes this harder than usual by mixing two registers that need
opposite treatment: Reddit markdown written by people, and PDF-extracted
prose written by corporate communications teams.

---

## 2. The concept (Understand / Apply)

### The order of operations

```
raw document
   → clean (per source)
   → segment into sentences
   → attribute each sentence to a bank
   → drop near-duplicates and fragments
   → sentences table
```

Cleaning comes before segmentation because a URL or a markdown link contains
punctuation that will otherwise be read as a sentence boundary.

### Why a naive splitter fails on financial text

Splitting on `.`, `!`, `?` breaks on:

| text | naive result | why |
|---|---|---|
| `S$1.2b in provisions` | splits after `S$1` | decimal point |
| `Q3 FY25 results` | may split after `Q3` if abbreviated | period in an abbreviation |
| `2.11% NIM, down 4bp p.a.` | splits at `2` and at `p.a.` | both |
| `Mr. Wee said...` | splits after `Mr` | title abbreviation |

The pipeline uses spaCy's statistical model, with explicit tokenizer
exceptions for abbreviations common in bank reporting: `p.a.`, `e.g.`,
`i.e.`, `vs.`, `approx.`, `est.`, `no.`, `Q1.`–`Q4.`, `FY.`, the month
abbreviations, and personal titles.

### Per-source cleaning

A shared cleaner would either under-clean Reddit or over-clean news.

| source | what gets removed |
|---|---|
| Reddit | Markdown links and emphasis, quote lines (`>`), URLs, bot and AutoModerator comments |
| News | NewsAPI's `[+1234 chars]` truncation marker, wire datelines like `(Reuters) - `, URLs |
| Earnings | Non-prose lines filtered during PDF extraction |

Note the bot detection: comments containing "i am a bot", "this action
was performed automatically" or "contact the moderators of this subreddit" are
dropped entirely. Machine-generated text is not opinion, and scoring it would
add noise with a systematic bias.

### Deduplication

Each sentence gets a `norm_hash`: lowercase, strip everything non-word, take a
SHA-256 prefix. Identical normalised text means a duplicate. This catches
syndicated wire copy republished across outlets, and boilerplate repeated
across quarterly PDFs.

### Fragment filters

Two thresholds: at least 15 characters (in `preprocess/segment.py`) and at
least 4 words (in `preprocess/pipeline.py`). Both exist because segmentation
still produces fragments occasionally, even with the abbreviation exceptions.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| spaCy segmentation, abbreviation exceptions, 15-char floor | `preprocess/segment.py` |
| Per-source cleaners, bot detection | `preprocess/clean.py` |
| Orchestration, bank attribution, `norm_hash`, 4-word floor | `preprocess/pipeline.py` |
| PDF prose extraction and its `_is_prose` filter | `ingest/earnings_extract.py` |
| Bank name detection | `ingest/base.py` |

The model is loaded with `disable=["ner", "lemmatizer", "tagger"]`. Only the
sentence boundaries are needed, and disabling the rest makes it materially
faster over 21,924 documents.

---

## 4. Analyze

### Per-sentence bank attribution, and the rule that matters

A document has a bank. A sentence inside it may be about a different one. The
rule:

> **An explicit in-sentence bank mention wins. A document's bank is inherited
> only for short, single-topic sources — news and earnings — never for long
> Reddit threads.**

The reason is empirical: inheriting a Reddit thread's bank pulled unrelated
sentences into that bank's corpus. A thread titled "DBS vs UOB" contains
sentences about each, plus sentences about neither, and inheritance would
assign all of them to whichever bank the thread was tagged with.

This is why `sentences.bank` exists as a column rather than being read through
a join to `documents`. The two genuinely differ.

### What still gets through: 2.6% of the corpus

Measured across all 36,884 sentences with four crude heuristics:

| problem | sentences | share | mostly from |
|---|---|---|---|
| Fewer than 4 real words | 874 | 2.4% | Reddit 605, earnings 269 |
| More than 60% numeric tokens | 79 | 0.2% | earnings 75 |
| Character-spaced text (`I p r h ef a o s r e m`) | 29 | 0.1% | earnings 29 |
| Markdown table fragment | 20 | 0.1% | Reddit 20 |
| **any of the above** | **953** | **2.6%** | |

Rates are almost identical by source: 2.7% of earnings, 2.5% of Reddit. Two
different failure modes converging on the same rate is a coincidence worth
noticing rather than a pattern.

The earnings failures are PDF extraction artifacts: chart axis labels
(`Sep 23 Dec 23 Mar 24 Jun 24`), boilerplate (`PrivateandConfidential`), and
text where the PDF encodes character positions individually so extraction
yields spaced-out letters. The Reddit failures are markdown tables and very
short comments.

**Why this looks worse than it is.** In the clustering output these artifacts
form their own tight clusters and appear to dominate, because clustering
gathers similar things and near-identical junk is highly similar. Measuring
prevalence directly gives 2.6%. Never judge corpus quality from cluster
samples.

### Comparing three segmentation approaches

| approach | handles `S$1.2b`? | handles `Q3 FY25`? | speed | dependency |
|---|---|---|---|---|
| Regex on `[.!?]` | No | No | Fastest | None |
| NLTK `punkt` | Partly, unsupervised abbreviation learning | Partly | Fast | NLTK plus a model |
| **spaCy + explicit exceptions** | Yes | Yes, once listed | Slower, mitigated by disabling pipes | spaCy plus `en_core_web_sm` |

spaCy was chosen for the explicit exception mechanism. `punkt` learns
abbreviations from the corpus statistically, which is elegant and gives you no
direct control when it gets `p.a.` wrong. Here the abbreviation set is small,
known and domain-specific, so stating it explicitly is both simpler and more
reliable.

The cost is honest: spaCy is heavier and slower, and the exception list has to
be maintained by hand. Something not on the list splits wrongly and nothing
warns you.

---

## 5. Evaluate

**The preprocessing design is broadly right.** Per-source cleaning
is clearly correct given the register mix, per-sentence attribution is backed
by an observed failure, and deduplication by normalised hash is cheap and
effective.

**The weakest part is PDF prose extraction.** `_is_prose` is heuristic, and
2.7% of earnings sentences are things that should never have become sentences.
More importantly, the extractor had a bug that made it return **nothing at
all** for months: `text.split("")` raises `ValueError` on every page, and
`pull()`'s per-file exception handling turned a total failure into a silent
no-op. The corpus already held earnings sentences from an earlier working run,
so nothing downstream looked wrong.

What that teaches matters more than the extraction quality itself:
**a step whose failure mode is "silently produces nothing" needs a test that
asserts it produces something.**

**What the evidence does not show.** Segmentation quality is unmeasured. There
is no gold set of correctly-segmented sentences, so nobody knows the split
error rate. The 2.6% figure measures obviously-broken *output*, not incorrect
*boundaries* — a sentence split in the wrong place still looks like a
plausible sentence and would pass all four heuristics.

**When you would do it differently.** If the corpus were only earnings PDFs,
investing in layout-aware extraction (distinguishing body text from tables and
chart labels structurally rather than heuristically) would pay off. At 12,254
earnings sentences with 2.7% junk, it does not.

---

## 6. Create

**Exercise (about ninety minutes).** Build the segmentation gold set the
project lacks.

```python
# .venv-plp/bin/python3
import sqlite3, random
c = sqlite3.connect("data/plp.db")
random.seed(42)

rows = c.execute("""
    SELECT sentence_id, source, text FROM sentences
""").fetchall()

sample = random.sample(rows, 100)
for sid, src, text in sample:
    print(f"{sid}\t{src}\t{text}")
```

Read all 100 and mark each: **good** (a complete sentence), **fragment** (cut
short or starting mid-sentence), or **junk** (not prose at all). Keep a tally
by source.

Then run the four heuristics from
`docs/evidence/extraction-quality-2026-09-11.txt` over your same 100 and build
a confusion matrix: how many of the sentences you marked junk did the heuristics catch, and how
many good sentences did they wrongly flag?

**Expected outcome.** You should find the heuristics have high precision (what
they flag really is junk) and unknown recall (they miss fragments that read as
plausible prose). If your hand-marked junk rate is close to 2.6%, the
heuristics are well calibrated. If it is substantially higher, the automated
figure understates the problem and the report should say so.

**For the report:** your sample size, the hand-marked rate by source, and one
sentence on whether the automated 2.6% is a floor or a fair estimate.

---

## 7. Self-check

1. Why does cleaning run before segmentation rather than after?
2. Give two financial-text examples a regex splitter on `[.!?]` gets wrong.
3. Why is a Reddit thread's document-level bank not inherited by its
   sentences, when a news article's is?
4. What does `norm_hash` catch, and what does it miss?
5. Why is 2.6% junk in the corpus but seemingly much more in the cluster
   output?

<details>
<summary>Answers</summary>

1. Because URLs, markdown links and wire datelines contain punctuation that a
   segmenter will read as sentence boundaries. Removing them first prevents
   spurious splits.
2. `S$1.2b in provisions` splits at the decimal point; `NIM fell 4bp p.a.`
   splits inside the abbreviation. Others include `Q3 FY25` and `Mr. Wee`.
3. Because a Reddit thread is long and covers several topics, so inheriting
   its bank pulls in sentences about other banks or about nothing. News
   articles and earnings releases are short and single-topic, so inheritance
   is safe there.
4. It catches exact duplicates after normalisation — syndicated wire copy
   republished across outlets, and boilerplate repeated across quarterly PDFs.
   It misses near-duplicates that differ by a word, since the hash is exact.
5. Because clustering gathers similar things, and near-identical junk
   (boilerplate, chart axis labels) is highly similar, so it concentrates into
   tight visible clusters while genuine content spreads out. Cluster listings
   over-represent low-variety content.

</details>

---

## 8. Sources

**Repository**

- `preprocess/segment.py` — spaCy, the abbreviation list, the 15-char floor
- `preprocess/clean.py` — per-source cleaners, bot markers
- `preprocess/pipeline.py` — attribution, `norm_hash`, the 4-word floor
- `ingest/earnings_extract.py` — `_is_prose` and the `split("")` regression
- `tests/test_earnings_extract.py` — the test written for that regression
- `docs/DESIGN.md` — "Per-sentence bank attribution"
- `docs/evidence/extraction-quality-2026-09-11.txt` — the 2.6% measurement

**Measured in this repository (2026-09-11)**

- All figures in section 4, over 36,884 sentences.

**External**

- spaCy is documented at https://spacy.io. The installed model is
  `en_core_web_sm` per `requirements.txt`. **Documentation not fetched during
  this pass**; the tokenizer-exception behaviour described here is taken from
  the code in `preprocess/segment.py`, which uses
  `nlp.tokenizer.add_special_case`.

**Not verified**

- Segmentation accuracy. No gold set exists, so the boundary error rate is
  unknown. The exercise in section 6 is designed to produce the first estimate.
- The claim that NLTK `punkt` handles these cases worse. It is a reasonable
  expectation from how the two libraries work and was **not tested here.**
- Whether the 2.6% heuristic figure has good recall. It measures
  obviously-broken output, not wrong boundaries.
