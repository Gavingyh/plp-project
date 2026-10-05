"""
Broker research PDFs -> documents. Source name: `sgx_research`.

Reads whatever is in data/sgx_research/*.pdf and upserts one document per PDF.
The PDFs come in three shapes, and each needs its own handling before the text
is fit for sentence segmentation:

  1. Text-layer broker reports (DBS Group Research, CGSI). Two-column pages, so
     a plain line-by-line read interleaves the main text with the sidebar. The
     page is split at its column gutter and each column read on its own.
     Some PDFs print every capital letter twice ("SSIINNGGAAPPOORREE"); that is
     collapsed. Everything from the disclaimer onward is dropped, because
     "DBS Bank Ltd" in a disclaimer is the publisher, not the subject.
  2. Scanned reports (no text layer at all): rendered to images and read with
     RapidOCR, then treated like (1). Needs `pip install rapidocr-onnxruntime`.
  3. Printouts of sginvestors.io research pages. The page is wrapped in site
     navigation and ads, and the ads sit between and inside article lines. The
     article body is set in one font at one indent and the ads are not, so lines
     are kept by font and indent instead of by guessing at ad wording.

Not part of the daily batch: the corpus only changes when someone drops files in.

REQUIRES: pip install pdfplumber pypdfium2 rapidocr-onnxruntime wordninja

USAGE:
  python -m ingest.sgx_research_extract
"""

import os
import re
from datetime import datetime, timedelta, timezone

from ingest.base import detect_banks
from ingest.db import make_doc_id, now_iso, upsert_documents
from ingest.earnings_extract import _is_prose

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

SOURCE = "sgx_research"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "data", "sgx_research")

# Reports whose subject is a listed company that is not one of the three banks.
# Their sentences would only ever reach the corpus through a passing mention.
_NOT_ABOUT_THE_BANKS = re.compile(r"Singapore Exchange|Kay Hian Holdings", re.IGNORECASE)

# "UOB Kay Hian" is a broker, not United Overseas Bank. detect_banks() would
# read the first word as UOB, so the broker's name is neutralised in the text.
_BROKER_UOBKH = re.compile(r"UOB[ -]?Kay[ -]?Hian", re.IGNORECASE)

# Where the report stops and the legal text starts. DISCLAIMER must be a whole
# line: DBS prints "Disclaimer: ..." as a footer on every page.
_END_OF_REPORT = re.compile(
    r"^(?:GENERAL\s*DISCLOSURE|DISCLAIMER\s*$|Completed Date:|Above is an excerpt)",
    re.MULTILINE)

# Furniture and non-prose lines of the DBS and CGSI layouts.
_FURNITURE = re.compile(
    r"^(?:DBS Group Research|SINGAPORE EQUITY RESEARCH|Refer to important disclosures|"
    r"Disclaimer: The information|Please refer to Disclaimer|Source[s]?\b|Figure\s*\d|Fig\.?\s*\d|"
    r"Table\s*\d|Note[s]?:|Banks . Singapore|Company Note|Target Price . Ratings History|"
    r"Closing price as of|Last Traded Price|Price Target 12|Watchlist the stock|"
    r"This report is based on content published on|to third parties without our prior|"
    r"or distributed to third parties|Completed Date|Dissemination Date)", re.IGNORECASE)
# Lines carrying an address, an ad or a share button are never report prose.
_NOT_PROSE_LINE = re.compile(r"@|https?://|www\.|\b(?:TikTok|SIGN UP|Sign Up|ADVERTISING|Advertisement)\b|"
                             r"^Like \d+ Share", re.IGNORECASE)

# sginvestors.io: article body font and indent (verified on all 11 printouts).
_SGI_BODY_FONT = "Open-Sans"
_SGI_HEADING_FONT = "Play-Bold"
_SGI_BODY_MIN_X0 = 90
_SGI_URL = re.compile(r"\(\s*https?://[^\s)]*(?:\s[^\s)]*){0,3}\)", re.IGNORECASE)
# Where the article ends and the site's "related reports" furniture starts.
_SGI_END = re.compile(r"Above is an excerpt|\d{4}-\d{2}-\d{2}(?=[A-Z][A-Za-z]+ - )|"
                      r"Listing of research reports|You May Also Like")
_SGI_TITLE = re.compile(r"^(?P<subject>.+?)\s+-\s+(?P<broker>.+?)\s+(?P<date>\d{4}-\d{2}-\d{2}):\s*(?P<title>.*)$",
                        re.DOTALL)

_PRIVATE_USE = re.compile(r"[-]")
_OCR_SCALE = 2.0
_OCR_MIN_SCORE = 0.5


# ----- metadata -----------------------------------------------------------------

def filename_date(filename: str, today: datetime | None = None) -> datetime | None:
    """DDMMYY or DDMMYYYY prefix of SGX's filenames ("300426 CGSI - ...").
    None if the prefix is missing or not a plausible past date: SGX's own
    "070827 DBS - United Overseas Bank..." decodes to 2027-08-07."""
    today = today or datetime.now(timezone.utc)
    for pattern, year_fmt in ((r"^(\d{2})(\d{2})(\d{4})\s", "%d%m%Y"), (r"^(\d{2})(\d{2})(\d{2})\s", "%d%m%y")):
        m = re.match(pattern, filename)
        if not m:
            continue
        try:
            d = datetime.strptime("".join(m.groups()), year_fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if datetime(2020, 1, 1, tzinfo=timezone.utc) <= d <= today:
            return d
    return None


def metadata_date(creation_date: str | None) -> datetime | None:
    """PDF /CreationDate, "D:20260807172933+08'00'" -> 2026-08-07."""
    if not creation_date:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})", creation_date)
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    except ValueError:
        return None


def publication_date(filename: str, creation_date: str | None, title_date: str | None = None) -> str:
    """Best publication date: the sginvestors title date; else the filename date,
    unless the PDF's own creation date disagrees by more than 45 days (a typo
    in the filename); else the creation date; else ingestion time."""
    if title_date:
        return f"{title_date}T00:00:00+00:00"
    from_name, from_meta = filename_date(filename), metadata_date(creation_date)
    if from_name and from_meta and abs(from_name - from_meta) > timedelta(days=45):
        from_name = None
    chosen = from_name or from_meta
    return chosen.strftime("%Y-%m-%dT00:00:00+00:00") if chosen else now_iso()


def subject_bank(text: str) -> str:
    """The bank a report is about, from its filename or title: DBS, OCBC, UOB,
    or MULTI for sector reports and anything naming several or none. A leading
    "DBS - " in a DBS Group Research filename is the publisher, so it is skipped."""
    text = _BROKER_UOBKH.sub("UOBKH", re.sub(r"^\d+\s+(?:DBS|CGSI)\s+-\s+", "", text))
    found = detect_banks(text)
    return found[0] if len(found) == 1 else "MULTI"


# ----- text-layer extraction ----------------------------------------------------

def collapse_doubled_letters(line: str) -> str:
    """Undo "SSIINNGGAAPPOORREE EEQQUUIITTYY" -> "SINGAPORE EQUITY". A token is
    collapsed only if every character is doubled, so real double letters survive."""
    def fix(token: str) -> str:
        if len(token) >= 4 and len(token) % 2 == 0 and token[0::2] == token[1::2]:
            return token[0::2]
        return token
    return " ".join(fix(t) for t in line.split(" "))


def find_gutter(boxes: list[tuple[float, float]], page_width: float) -> float | None:
    """x of the gap between two text columns, or None for a single column.
    boxes are (x0, x1) of words or OCR lines. The gutter is the widest run in
    the middle 40% of the page that at most three boxes (1%) cross, with real text on
    both sides of it."""
    if len(boxes) < 40:
        return None
    lo, hi = int(page_width * 0.3), int(page_width * 0.7)
    best, run = (0, None), None
    for x in range(lo, hi + 1):
        crossing = sum(1 for a, b in boxes if a < x < b) if x < hi else 99
        if crossing <= max(3, len(boxes) // 100):
            run = x if run is None else run
        elif run is not None:
            if x - run > best[0]:
                best = (x - run, run + (x - run) / 2)
            run = None
    width, x = best
    if width < 6:
        return None
    left = sum(1 for a, b in boxes if b <= x)
    right = sum(1 for a, b in boxes if a >= x)
    return x if min(left, right) >= 0.2 * len(boxes) else None


def _page_columns_text(page) -> list[str]:
    words = page.extract_words()
    gutter = find_gutter([(w["x0"], w["x1"]) for w in words], page.width)
    if gutter is None:
        return [page.extract_text() or ""]
    return [page.within_bbox((0, 0, gutter, page.height)).extract_text() or "",
            page.within_bbox((gutter, 0, page.width, page.height)).extract_text() or ""]


def _ocr_page_columns(engine, image) -> list[str]:
    import numpy as np
    result, _ = engine(np.asarray(image))
    items = [(min(p[0] for p in box), max(p[0] for p in box), min(p[1] for p in box), text)
             for box, text, score in (result or []) if float(score) >= _OCR_MIN_SCORE]
    gutter = find_gutter([(a, b) for a, b, _, _ in items], image.width)
    columns = [items] if gutter is None else [[i for i in items if i[1] <= gutter or i[0] < gutter],
                                               [i for i in items if i[0] >= gutter]]
    # a box that straddles the gutter belongs to the left column once
    if gutter is not None:
        left_ids = {id(i) for i in columns[0]}
        columns[1] = [i for i in columns[1] if id(i) not in left_ids]
    return ["\n".join(t for *_, t in sorted(col, key=lambda i: i[2])) for col in columns]


_RUN_TOGETHER = re.compile(r"[A-Z]?[a-z]{12,}")


def split_run_together(line: str) -> str:
    """OCR on tightly set text drops the spaces ("Refertoimportantdisclosures").
    Splits only lowercase runs of 12+ letters, so figures like 3Q24 and SGD3bn
    and ordinary long words are left alone."""
    import wordninja

    def fix(m):
        lead = " " if m.start() and m.string[m.start() - 1].isdigit() else ""
        return lead + " ".join(wordninja.split(m.group(0)))
    return _RUN_TOGETHER.sub(fix, line)


def _clean_lines(text: str, ocr: bool = False, keep_headings: bool = False) -> list[str]:
    lines = []
    for raw in text.split("\n"):
        line = collapse_doubled_letters(_PRIVATE_USE.sub("", raw)).strip()
        if ocr:
            line = split_run_together(line)
        if keep_headings and _END_OF_REPORT.match(line):
            lines.append(line)      # the cut needs to see these
        elif line and not _FURNITURE.match(line) and not _NOT_PROSE_LINE.search(line):
            lines.append(line)
    return lines


def extract_report(pdf_path: str) -> tuple[str, str]:
    """Text of a DBS/CGSI-style report and how it was read ("text" or "ocr")."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        pages = [_page_columns_text(p) for p in pdf.pages]
        has_text = sum(len("".join(cols).strip()) for cols in pages) >= 200
    method = "text"
    if not has_text:
        pages, method = _ocr_pages(pdf_path), "ocr"
    text = "\n".join(col for cols in pages for col in cols)
    # Furniture is stripped line by line first, because the disclaimer's own heading is
    # sometimes printed with doubled capitals or run together by OCR, and the cut must
    # see it as repaired. The cut keeps the lines the furniture filter left.
    lines = _clean_lines(text, ocr=(method == "ocr"), keep_headings=True)
    joined = "\n".join(lines)
    cut = _END_OF_REPORT.search(joined)
    if cut:
        joined = joined[:cut.start()]
    return "\n".join(l for l in joined.split("\n") if _is_prose(l)), method


def _ocr_pages(pdf_path: str) -> list[list[str]]:
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        return [_ocr_page_columns(engine, page.render(scale=_OCR_SCALE).to_pil()) for page in pdf]
    finally:
        pdf.close()


# ----- sginvestors.io printouts -------------------------------------------------

def is_sginvestors(pdf_path: str) -> bool:
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return "sginvestors.io" in (pdf.pages[0].extract_text() or "")


def extract_sginvestors(pdf_path: str) -> tuple[str, dict]:
    """Article text and {"subject", "broker", "date", "title"} from the page's
    own headline ("DBS - RHB Research 2026-05-28: A Core Holding ...")."""
    import pdfplumber
    kept, headline = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages):
            for line in page.extract_text_lines(return_chars=True):
                chars = line["chars"]
                font = max({c["fontname"] for c in chars}, key=lambda f: sum(c["fontname"] == f for c in chars))
                size = round(sum(c["size"] for c in chars) / len(chars), 1)
                text = _PRIVATE_USE.sub("", line["text"]).strip()
                if _SGI_HEADING_FONT in font and size > 20 and pageno == 0:
                    headline.append(text)             # the report's title block
                elif _SGI_HEADING_FONT in font and line["x0"] < _SGI_BODY_MIN_X0 and size <= 16:
                    kept.append(text if text.endswith((".", ":", "?")) else text + ".")
                elif _SGI_BODY_FONT in font and not font.endswith(("Medium", "Bold", "Light")) \
                        and 10.5 <= size <= 12 and line["x0"] >= _SGI_BODY_MIN_X0 \
                        and not _NOT_PROSE_LINE.search(text):
                    kept.append(text)
    body = _SGI_URL.sub("", " ".join(kept))
    cut = _SGI_END.search(body)
    body = body[:cut.start()] if cut else body
    # a long headline wraps inside its own date ("2026-02-" / "04: ...")
    m = _SGI_TITLE.match(re.sub(r"(\d)-\s+(\d)", r"\1-\2", " ".join(headline)))
    meta = {k: re.sub(r"\s+", " ", v).strip() for k, v in m.groupdict().items()} if m else {}
    return re.sub(r"\s+", " ", body).strip(), meta


# ----- documents ----------------------------------------------------------------

def _creation_date(pdf_path: str) -> str | None:
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return (pdf.metadata or {}).get("CreationDate")


def build_document(path: str) -> dict | None:
    fname = os.path.basename(path)
    if _NOT_ABOUT_THE_BANKS.search(fname):
        logger.info(f"{fname}: skipped, subject is not DBS, OCBC or UOB")
        return None
    meta, method = {}, "text"
    if is_sginvestors(path):
        body, meta = extract_sginvestors(path)
        method, doc_type = "sginvestors", "analyst_report_web"
        bank = subject_bank(meta.get("subject", fname))
    else:
        body, method = extract_report(path)
        doc_type = "analyst_report"
        bank = subject_bank(fname)
    body = _BROKER_UOBKH.sub("UOBKH", body)
    if not body.strip():
        logger.info(f"{fname}: no prose extracted")
        return None
    return {
        "doc_id": make_doc_id(SOURCE, fname),
        "source": SOURCE,
        "source_detail": meta.get("broker") or fname,
        "bank": bank,
        "doc_type": doc_type,
        "title": meta.get("title") or fname,
        "body": body,
        "published_at": publication_date(fname, _creation_date(path), meta.get("date")),
        "url": f"file://{path}",
        "ingested_at": now_iso(),
        "raw": {"filename": fname, "read_by": method, "n_chars": len(body), **meta},
    }


def pull() -> list[dict]:
    if not os.path.isdir(PDF_DIR):
        logger.warning(f"No {PDF_DIR} directory found.")
        return []
    docs = []
    for fname in sorted(os.listdir(PDF_DIR)):
        if not fname.lower().endswith(".pdf"):
            continue
        try:
            doc = build_document(os.path.join(PDF_DIR, fname))
        except Exception as e:
            logger.error(f"{fname}: ERROR extracting text - {e}")
            continue
        if doc:
            logger.info(f"{fname[:60]}: {doc['bank']:5s} {doc['published_at'][:10]} "
                        f"{doc['raw']['read_by']:11s} {len(doc['body']):6,d} chars")
            docs.append(doc)
    return docs


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Run started: {datetime.now().isoformat()}")
    docs = pull()
    attempted, inserted = upsert_documents(docs)
    logger.info(f"Documents attempted: {attempted}  |  newly inserted: {inserted}  "
                f"|  already-seen (skipped): {attempted - inserted}")
