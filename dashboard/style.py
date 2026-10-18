"""Presentation themes, side navigation, and shared chart/card builders.
Pure presentation - no data logic lives here."""

from dataclasses import dataclass
import html
from urllib.parse import urlsplit

import altair as alt
import pandas as pd

# Match .streamlit/config.toml so native widgets and custom HTML agree.
BG = "#F5F7FA"
SURFACE = "#FFFFFF"
SURFACE_2 = "#EEF2F6"
LINE = "#E1E7EE"

# Type
INK = "#172B4D"
MUTED = "#526477"

# The single UI accent, and the dark ink used on top of it
ACCENT = "#176B5B"
ON_ACCENT = "#FFFFFF"

# Semantic sentiment colours
POS = "#18734B"
NEU = "#CBD5E1"
NEG = "#B83B4B"

# One colour per bank, used only for data series
BANK_COLORS = {"DBS": "#1769AA", "OCBC": "#7652A5", "UOB": "#966000"}


@dataclass(frozen=True)
class Palette:
    """Passed explicitly to renderers; one user's choice cannot affect another."""

    mode: str
    bg: str
    surface: str
    surface_2: str
    line: str
    ink: str
    muted: str
    accent: str
    on_accent: str
    pos: str
    neu: str
    neg: str
    bank_colors: dict[str, str]
    heat_neg: str
    heat_pos: str


LIGHT = Palette(
    "light",
    BG,
    SURFACE,
    SURFACE_2,
    LINE,
    INK,
    MUTED,
    ACCENT,
    ON_ACCENT,
    POS,
    NEU,
    NEG,
    BANK_COLORS,
    "#F2B8C0",
    "#A8DCC1",
)
DARK = Palette(
    "dark",
    "#111318",
    "#1A1D24",
    "#222630",
    "#3B4350",
    "#E8EAEE",
    "#ABB5C4",
    "#A8E6D8",
    "#0F1B18",
    "#79DBA6",
    "#3B4150",
    "#F28B82",
    {"DBS": "#7CC4FF", "OCBC": "#C9A7F5", "UOB": "#F2C879"},
    "#653138",
    "#24543E",
)

RADIUS = "14px"  # one corner radius: cards, buttons, inputs, nav items
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"


def css(palette: Palette = LIGHT) -> str:
    BG, SURFACE, SURFACE_2, LINE = (
        palette.bg,
        palette.surface,
        palette.surface_2,
        palette.line,
    )
    INK, MUTED = palette.ink, palette.muted
    ACCENT, ON_ACCENT = palette.accent, palette.on_accent
    POS, NEG = palette.pos, palette.neg
    return f"""
<style>
html, body, .stApp,
.stApp :is(p, h1, h2, h3, h4, h5, h6, li, label, button, input, textarea, div, td, th, a) {{
    font-family: {FONT};
}}
.stApp {{ background: {BG}; color: {INK}; color-scheme: {palette.mode}; }}
.stMain {{ background: {BG}; color: {INK}; }}
.block-container {{ padding: 2.6rem 2.5rem 3rem; max-width: 1440px; }}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {{ gap: 1.15rem; }}
header[data-testid="stHeader"] {{ background: transparent; }}
h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -.02em; font-weight: 600; }}
h3 {{ font-size: 1.15rem; }}
[data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p,
.stApp small {{ color: {MUTED}; font-size: .8rem; line-height: 1.5; }}
.stApp [data-testid="stCaptionContainer"] {{ opacity: 1; }}
hr {{ border-color: {LINE}; }}

/* ---------- sidebar navigation ---------- */
section[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
.brand {{ display:flex; align-items:center; gap:10px; font-size: 1.45rem; font-weight: 750; color: {INK}; letter-spacing: -.04em; }}
.brand-mark {{ width:32px; height:32px; display:grid; place-items:center; background:{ACCENT}; color:{ON_ACCENT}; border-radius:10px; }}
.brand-sub {{ color: {MUTED}; font-size: .78rem; margin: .55rem 0 1.5rem; }}
section[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
    width: 100%; padding: 11px 14px; border-radius: 10px; margin: 0;
    color: {MUTED}; transition: background .2s, color .2s; cursor: pointer;
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{ background: {SURFACE_2}; color: {INK}; }}
/* hide the radio circle: the element just before the option's name (Streamlit 1.63 wraps both in one block) */
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] div:has(+ [data-testid="stMarkdownContainer"]) {{ display: none; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{ font-weight: 500; font-size: .95rem; }}
.stApp label[data-testid="stRadioOption"] {{ color: {INK}; }}
.stApp label[data-testid="stRadioOption"] p {{ color: inherit; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {{
    background: {ACCENT}; color: {ON_ACCENT};
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {{
    color: {ON_ACCENT}; font-weight: 600;
}}
.side-label {{ font-size: .65rem; text-transform:uppercase; font-weight:700; color: {MUTED}; margin: 2rem 0 .6rem; letter-spacing: .12em; }}
.side-stat {{ display:flex; justify-content:space-between; gap:12px; padding:.45rem 0; font-size:.9rem;
              color:{INK}; border-bottom:1px solid {LINE}; font-variant-numeric: tabular-nums; }}
.side-stat span:first-child {{ color:{MUTED}; }}

/* ---------- page header ---------- */
.page-heading {{ margin-bottom:.65rem; }}
.heading-top {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; }}
.eyebrow {{ color:{ACCENT}; font-size:.67rem; font-weight:750; letter-spacing:.14em; text-transform:uppercase; }}
.snapshot-badge {{ color:{MUTED}; font-size:.72rem; display:flex; align-items:center; gap:7px; white-space:nowrap; }}
.snapshot-badge::before {{ content:""; width:6px; height:6px; border-radius:50%; background:{ACCENT}; }}
.stApp p.hello {{ font-size: 2.15rem; font-weight: 750; color: {INK}; margin: 0; letter-spacing: -.045em; line-height:1.2; }}
.stApp p.sub {{ color: {MUTED}; font-size: .94rem; margin: .65rem 0 0; max-width: 80ch; line-height: 1.6; }}
.report-meta {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:16px; }}
.report-meta span {{ font-size:.69rem; color:{MUTED}; border:1px solid {LINE}; border-radius:6px; padding:4px 8px; background:{SURFACE}; }}
.section-heading {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin:0 0 2px; }}
.section-heading h3 {{ color:{INK}; font-size:1.05rem; font-weight:700; margin:0; padding:0; letter-spacing:-.025em; }}
.section-heading h3 span {{ font-size:inherit; color:inherit; }}
.section-heading > span {{ color:{MUTED}; font-size:.72rem; }}
.control-description {{ padding:3px 0 0 20px; border-left:1px solid {LINE}; }}
.control-description strong {{ color:{INK}; font-size:.88rem; display:block; margin-bottom:5px; }}
.control-description p {{ color:{MUTED}; font-size:.8rem; margin:0; line-height:1.6; }}
.reading-note {{ padding:12px 14px; background:{BG}; border-radius:8px; color:{MUTED}; font-size:.76rem; line-height:1.6; }}
.reading-note b {{ color:{INK}; }}

/* ---------- surfaces ---------- */
.panel {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS};
          padding: 18px 20px; margin-bottom: 14px; }}
.panel h4 {{ margin: 0 0 .15rem; font-size: 1rem; }}
.panel .hint {{ color: {MUTED}; font-size: .85rem; margin: 0 0 .6rem; line-height: 1.5; max-width: 70ch; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {LINE} !important; border-radius: {RADIUS}; }}
[class*="st-key-panel_"], .st-key-topic_controls, .st-key-trend_controls,
.st-key-evidence_controls, [class*="st-key-topic_card_"], [class*="st-key-trend_window_"] {{
    background:{SURFACE}; border:1px solid {LINE} !important; border-radius:{RADIUS};
    box-shadow:0 3px 12px #0F233B04; padding:20px !important;
}}
.st-key-topic_controls, .st-key-trend_controls, .st-key-evidence_controls {{ padding:16px 20px !important; }}
[class*="st-key-topic_card_"] {{ padding:16px 18px 12px !important; gap:10px; }}
[class*="st-key-topic_card_"] [data-testid="stHorizontalBlock"] {{ gap:8px; }}
[class*="st-key-topic_card_"] .stButton > button {{ min-height:32px; padding:3px 6px; }}
[class*="st-key-topic_card_"] .stButton p {{ font-size:.72rem; }}
.st-key-topic_card_DBS {{ border-left:3px solid {palette.bank_colors['DBS']} !important; }}
.st-key-topic_card_OCBC {{ border-left:3px solid {palette.bank_colors['OCBC']} !important; }}
.st-key-topic_card_UOB {{ border-left:3px solid {palette.bank_colors['UOB']} !important; }}

/* the answer to "so what?", always first on a page */
.takeaway {{ background: {ACCENT}0C; border:1px solid {ACCENT}22;
             border-radius:10px; padding:13px 18px; margin:4px 0 12px; }}
.takeaway .kicker {{ color: {ACCENT}; font-size: .65rem; text-transform:uppercase; letter-spacing:.08em; font-weight: 750; margin-bottom: .25rem; }}
.takeaway .body {{ font-size: .87rem; line-height: 1.6; color: {INK}; }}

/* ---------- bank cards ---------- */
.bank-card {{ background: {SURFACE}; border: 1px solid {LINE};
              border-radius: {RADIUS}; padding: 22px 22px 18px; height: 100%; box-shadow:0 3px 12px #0F233B04; }}
.bank-top {{ display:flex; align-items:center; gap:10px; font-weight:600; font-size:.95rem; }}
.bank-dot {{ width:10px; height:10px; border-radius:50%; }}
.bank-score {{ font-size: 2.65rem; font-weight: 750; letter-spacing: -.055em; line-height: 1.1;
               margin-top: 18px; font-variant-numeric: tabular-nums; }}
.bank-word {{ font-size: .75rem; margin-top: 5px; }}
.bank-meta {{ color: {MUTED}; font-size: .73rem; margin-top: 16px; line-height: 1.8; }}
.spark-label {{ color: {MUTED}; font-size: .65rem; margin-top: .55rem; }}
.bank-card svg {{ float: right; margin-top: -64px; }}
.bank-summary {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
.bank-summary .bank-score {{ font-size:1.85rem; margin:0; }}
.bank-details {{ display:flex; justify-content:space-between; gap:8px; align-items:center; margin-top:6px; margin-bottom:8px; }}
.bank-details .bank-word, .bank-details .bank-meta {{ margin:0; font-size:.72rem; }}
[class*="st-key-topic_card_"] .bank-card {{ padding:0; border:0; background:transparent; border-radius:0; box-shadow:none; }}
.up {{ color: {POS}; }} .down {{ color: {NEG}; }} .flat {{ color: {MUTED}; }}

/* ---------- strengths / weaknesses ---------- */
.sw {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; padding: 16px 18px; height: 100%; }}
.sw .who {{ display:flex; align-items:center; gap:8px; font-weight:600; margin-bottom:.7rem; }}
.sw .row {{ display:flex; justify-content:space-between; gap:12px; padding:.4rem 0;
            font-size:.9rem; border-top:1px solid {LINE}; }}
.sw .row span:last-child {{ font-variant-numeric: tabular-nums; }}
.sw .tag {{ color: {MUTED}; font-size:.75rem; margin-top:.5rem; }}

/* ---------- evidence ---------- */
.quote {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius:12px;
          padding:20px 24px; margin-bottom:10px; box-shadow:0 2px 8px #0F233B03; }}
.quote .text {{ line-height: 1.75; color: {INK}; font-size:.94rem; padding:12px 0 14px; }}
.quote .quote-heading {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
.quote .source-name {{ color:{INK}; font-weight:650; font-size:.78rem; }}
.quote .source-date {{ color:{MUTED}; font-size:.73rem; }}
.quote .meta {{ color: {MUTED}; font-size: .71rem; padding-top:12px; border-top:1px solid {LINE}; display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
.quote .meta a, .quote .meta > span:last-child {{ margin-left:auto; }}
.quote a {{ color: {ACCENT}; text-decoration: none; }}
.quote a:hover {{ text-decoration:underline; }}
.evidence-context {{ display:flex; align-items:center; gap:16px; margin:6px 0; }}
.evidence-context .count {{ color:{INK}; font-size:2rem; font-weight:750; letter-spacing:-.04em; line-height:1; }}
.evidence-context strong {{ color:{INK}; font-size:.91rem; display:block; }}
.evidence-context span {{ color:{MUTED}; font-size:.74rem; }}
.chip {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size:.75rem; font-weight:600; }}
.chip.pos {{ background: {POS}22; color: {POS}; }}
.chip.neg {{ background: {NEG}22; color: {NEG}; }}
.chip.neu {{ background: {SURFACE_2}; color: {MUTED}; }}

/* ---------- native widgets ---------- */
div[data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; padding: 14px 18px; }}
div[data-testid="stMetricValue"] {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.stButton > button {{ border-radius:8px; border: 1px solid {LINE}; background: {SURFACE}; color: {INK};
    transition: border-color .2s, color .2s, transform .1s; }}
.stButton > button:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
.stButton > button:active {{ transform: translateY(1px); }}
.stButton > button:focus-visible {{ outline: 2px solid {ACCENT}; outline-offset: 2px; }}
.stButton > button[kind="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: 600; }}
div[data-baseweb="select"] > div {{ border-radius: {RADIUS}; background: {SURFACE_2}; border: 1px solid {LINE}; }}
div[data-testid="stDataFrame"] {{ border-radius: {RADIUS}; overflow: hidden; }}
details {{ background: {SURFACE}; border: 1px solid {LINE} !important; border-radius:10px; }}
[data-testid="stExpander"] summary p {{ font-size:.8rem; }}
[data-testid="stTabs"] [role="tablist"] {{ border-bottom:1px solid {LINE}; gap:24px; }}
[data-testid="stTabs"] [role="tab"] {{ background:transparent; color:{MUTED}; padding:10px 0 12px; font-size:.82rem; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ color:{ACCENT}; font-weight:700; }}
[data-testid="stTabs"] [role="tab"]:hover {{ color:{ACCENT}; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background-color:{ACCENT}; }}
[data-testid="stChatMessage"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; }}
[class*="st-key-trend_window_"] [data-testid="stMetric"] {{ background: transparent; border: none; padding: 0; }}
[class*="st-key-trend_window_"] {{ border-color: {LINE}; }}

/* Native widgets inherit the session's palette as well as the custom cards. */
.stApp [data-testid="stWidgetLabel"], .stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricValue"], .stApp [data-testid="stExpander"] summary,
.stApp [data-testid="stCheckbox"] label {{ color: {INK}; }}
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div,
.stApp [data-testid="stChatInput"] {{ background: {SURFACE_2}; color: {INK}; }}
.stApp textarea::placeholder, .stApp input::placeholder {{ color: {MUTED}; }}
.stApp [data-testid="stBottomBlockContainer"] {{ background: {BG}; }}
.stApp [role="alert"] [data-testid="stMarkdownContainer"],
.stApp [role="alert"] p, .stApp [data-testid="stAlert"] p {{ color: {INK}; }}
.stApp [data-testid="stButton"] button {{ background: {SURFACE}; color: {INK}; border-color: {LINE}; }}
.stApp [data-testid="stButton"] button[kind="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; }}
.stApp [data-testid="stSelectbox"] [role="group"] {{ background: {BG}; border-color: {LINE}; border-radius:8px; }}
.stApp [data-testid="stSelectbox"] button {{ background: {BG}; color: {INK}; }}
.stApp [data-testid="stWidgetLabel"] p {{ font-size:.76rem; font-weight:600; }}
.stApp [data-testid="stRadio"] [role="radiogroup"] {{ gap:10px; }}
.stApp [data-testid="stRadio"] label p {{ font-size:.78rem; }}
[class*="st-key-trend_window_"] [data-testid="stMetricValue"] {{ font-size:2.15rem; letter-spacing:-.04em; }}
.st-key-disclosure {{ margin-top:12px; padding-top:16px; border-top:1px solid {LINE}; }}
.st-key-disclosure [data-testid="stCaptionContainer"] p {{ font-size:.7rem; }}
[role="listbox"], [role="option"] {{ background: {SURFACE_2}; color: {INK}; }}
[role="option"]:hover, [role="option"][data-focused="true"] {{ background: {LINE}; }}

@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
@media (max-width: 800px) {{
    .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
    .stApp p.hello {{ font-size: 1.65rem; }}
    .bank-score {{ font-size: 2rem; }}
    .bank-card svg {{ display: none; }}
    .heading-top {{ flex-wrap:wrap; }}
    .control-description {{ border:0; padding:0; }}
    .quote {{ padding:16px; }}
    .quote .meta a {{ margin-left:0; }}
}}
</style>
"""


CSS = css()


# ---------- plain-language helpers ----------


def pretty(name: str) -> str:
    """'net_interest_margin' -> 'Net interest margin'."""
    labels = {
        "arctic_shift": "Reddit",
        "cna": "CNA",
        "earnings": "Bank earnings",
        "google_news": "Google News",
        "newsapi": "NewsAPI",
        "sgx_research": "Broker research",
        "yahoo_news": "Yahoo News",
        "capital_liquidity": "Capital & liquidity",
        "dividend_policy": "Dividends",
        "management_guidance": "Management outlook",
        "income_profit_results": "Earnings & profit",
        "wealth_business": "Wealth management",
        "investor_stock_sentiment": "Investor sentiment",
        "retail_banking_sentiment": "Retail banking experience",
        "macro_market_environment": "Macro & market outlook",
        "other": "Other / uncategorised",
    }
    return labels.get(str(name), str(name).replace("_", " ").capitalize())


def score_word(score: float) -> str:
    """What a -1..1 score means in words. Scores here are small, so the bands are too."""
    if score >= 0.15:
        return "Positive"
    if score >= 0.03:
        return "Slightly positive"
    if score > -0.03:
        return "Neutral"
    if score > -0.15:
        return "Slightly negative"
    return "Negative"


def takeaway(kicker: str, body: str) -> str:
    return (
        f'<div class="takeaway"><div class="kicker">{html.escape(kicker)}</div>'
        f'<div class="body">{body}</div></div>'
    )


def section_heading(title: str, detail: str = "") -> str:
    return (
        f'<div class="section-heading"><h3>{html.escape(title)}</h3>'
        f"<span>{html.escape(detail)}</span></div>"
    )


def sparkline(values, color=ACCENT, w=96, h=34) -> str:
    """Inline SVG polyline for a bank card; empty string if too few points."""
    vals = [v for v in values if v is not None and pd.notna(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    # Preserve missing periods as gaps rather than joining their neighbours.
    segments, points = [], []
    for i, value in enumerate(values):
        if value is None or pd.isna(value):
            if points:
                segments.append(" ".join(points))
                points = []
        else:
            points.append(
                f"{i * w / (len(values) - 1):.1f},{h - 3 - (value - lo) / span * (h - 6):.1f}"
            )
    if points:
        segments.append(" ".join(points))
    lines = "".join(
        f'<polyline fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>'
        for pts in segments
    )
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">' f"{lines}</svg>"


def bank_card(
    bank: str,
    score: float | None,
    n: int,
    delta: float | None,
    spark_values,
    *,
    palette: Palette = LIGHT,
    compact: bool = False,
) -> str:
    color = palette.bank_colors.get(bank, palette.muted)
    head = (
        f'<div class="bank-top"><span class="bank-dot" style="background:{color}"></span>'
        f"{html.escape(bank)}</div>"
    )
    if compact:
        value = "—" if score is None else f"{score:+.3f}"
        word = "Not enough data" if score is None else score_word(score)
        return (
            f'<div class="bank-card" style="--bank-color:{color}">'
            f'<div class="bank-summary">{head}<div class="bank-score">{value}</div></div>'
            f'<div class="bank-details"><span class="bank-word" style="color:{color}">{word}</span>'
            f'<span class="bank-meta">Based on {n:,} sentences</span></div></div>'
        )
    if score is None:
        return (
            f'<div class="bank-card" style="--bank-color:{color}">{head}'
            '<div class="bank-score">—</div><div class="bank-word">Not enough data</div>'
            f'<div class="bank-meta">Based on {n:,} sentences</div></div>'
        )
    if delta is None:
        trend = ""
    elif abs(delta) < 0.005:
        trend = '<span class="flat">Last 30 days: in line with all-time</span><br>'
    else:
        cls, word = ("up", "above") if delta > 0 else ("down", "below")
        trend = f'<span class="{cls}">Last 30 days: {abs(delta):.3f} {word} all-time</span><br>'
    spark = sparkline(spark_values, color)
    return (
        f'<div class="bank-card" style="--bank-color:{color}">{head}'
        f'<div class="bank-score">{score:+.3f}</div>'
        f'<div class="bank-word" style="color:{color}">{score_word(score)}</div>'
        f"{spark}"
        + (
            '<div class="spark-label">Mini chart: up to 12 recent months</div>'
            if spark
            else ""
        )
        + f'<div class="bank-meta">{trend}Based on {n:,} sentences</div></div>'
    )


def strengths_card(
    bank: str, best: list, worst: list, *, palette: Palette = LIGHT
) -> str:
    """best/worst are lists of (aspect, score); empty lists mean too little data."""
    color = palette.bank_colors.get(bank, palette.muted)

    def rows(items):
        result = []
        for aspect, score in items:
            tone = "up" if score >= 0.03 else "down" if score <= -0.03 else "flat"
            result.append(
                f'<div class="row"><span>{html.escape(pretty(aspect))}</span>'
                f'<span class="{tone}">{score:+.2f}</span></div>'
            )
        return "".join(result)

    if best or worst:
        body = (
            '<div class="tag">Highest sentiment</div>'
            + rows(best)
            + '<div class="tag" style="margin-top:.9rem">Lowest sentiment</div>'
            + rows(worst)
        )
    else:
        body = '<div class="tag">Not enough sentences per topic yet.</div>'
    return (
        f'<div class="sw"><div class="who"><span class="bank-dot" style="background:{color}">'
        f"</span>{html.escape(bank)}</div>{body}</div>"
    )


def quote_card(text, source, published, url, label=None, confidence=None) -> str:
    chip = ""
    confidence_text = ""
    if label:
        key = {"positive": "pos", "negative": "neg"}.get(str(label).lower(), "neu")
        chip = f'<span class="chip {key}">{html.escape(str(label).capitalize())}</span>'
        if confidence is not None and pd.notna(confidence):
            confidence_text = f"<span>Model confidence: {confidence:.0%}</span>"
    try:
        valid_url = bool(url) and urlsplit(str(url)).scheme.lower() in ("http", "https")
    except ValueError:
        valid_url = False
    link = (
        f'<a href="{html.escape(str(url))}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>'
        if valid_url
        else "<span>Source link unavailable</span>"
    )
    return (
        '<div class="quote"><div class="quote-heading">'
        f'<span class="source-name">{html.escape(pretty(source))}</span>'
        f'<span class="source-date">{html.escape(str(published)[:10])}</span></div>'
        f'<div class="text">{html.escape(str(text))}</div>'
        f'<div class="meta">{chip}{confidence_text}{link}</div></div>'
    )


def sentiment_cmap(*, palette: Palette = LIGHT):
    """A red-neutral-green scale matching the selected palette."""
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list(
        "sentiment", [palette.heat_neg, palette.bg, palette.heat_pos]
    )


# ---------- charts ----------


def _themed(chart, height, palette: Palette = LIGHT):
    MUTED, LINE, INK = palette.muted, palette.line, palette.ink
    return (
        chart.properties(height=height, background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor=MUTED,
            titleColor=MUTED,
            gridColor=LINE,
            domainColor=LINE,
            tickColor=LINE,
            labelFont="Arial",
            titleFont="Arial",
            labelFontSize=14,
        )
        .configure_legend(
            labelColor=INK,
            titleColor=MUTED,
            labelFont="Arial",
            orient="top",
            title=None,
            symbolType="circle",
            labelFontSize=14,
        )
    )


def _bank_scale(banks, palette: Palette = LIGHT):
    present = [b for b in palette.bank_colors if b in set(banks)]
    return alt.Scale(domain=present, range=[palette.bank_colors[b] for b in present])


def comparison_chart(frame: pd.DataFrame, *, palette: Palette = LIGHT):
    """Compare stored topic scores on the full sentiment scale; retain missing rows."""
    frame = frame.copy()
    frame["display"] = frame.score.map(
        lambda score: "No score" if pd.isna(score) else f"{score:+.3f}"
    )
    base = alt.Chart(frame).encode(
        y=alt.Y(
            "bank:N",
            title=None,
            sort=["DBS", "OCBC", "UOB"],
            axis=alt.Axis(
                domain=False, ticks=False, labelPadding=14, labelFontWeight=600
            ),
        ),
        x=alt.X(
            "score:Q",
            title=None,
            scale=alt.Scale(domain=[-1, 1]),
            axis=alt.Axis(
                values=[-1, -0.5, 0, 0.5, 1],
                format="+.1f",
                gridDash=[2, 5],
                domain=False,
                tickSize=0,
                labelPadding=12,
            ),
        ),
        color=alt.Color("bank:N", scale=_bank_scale(frame.bank, palette), legend=None),
        tooltip=[
            alt.Tooltip("bank:N", title="Bank"),
            alt.Tooltip("display:N", title="Score"),
            alt.Tooltip("n:Q", title="Sentences", format=","),
        ],
    )
    bars = base.mark_bar(size=16, cornerRadius=4, opacity=0.25)
    dots = base.mark_circle(size=130, opacity=1)
    labels = (
        base.mark_text(align="left", dx=14, fontSize=15, fontWeight=700)
        .encode(
            text="display:N",
            color=alt.value(palette.ink),
            x=alt.X("label_position:Q", scale=alt.Scale(domain=[-1, 1])),
        )
        .transform_calculate(label_position="isValid(datum.score) ? datum.score : 0")
    )
    zero = (
        alt.Chart(pd.DataFrame({"zero": [0]}))
        .mark_rule(color=palette.muted, strokeDash=[4, 4], opacity=0.55)
        .encode(x="zero:Q")
    )
    return _themed(bars + dots + labels + zero, 235, palette)


def _zero_rule(palette: Palette = LIGHT):
    return (
        alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(color=palette.muted, strokeDash=[4, 4])
        .encode(y="y:Q")
    )


def _plot_data(df):
    """Split each series at missing/thin periods so paths cannot bridge gaps."""
    df = df.sort_values((["bank"] if "bank" in df.columns else []) + ["period"]).copy()
    if "sufficient" in df.columns:
        df["score"] = df["score"].where(df["sufficient"])
    if "bank" in df.columns:
        df["_segment"] = df.groupby("bank")["score"].transform(
            lambda s: s.isna().cumsum()
        )
    else:
        df["_segment"] = df["score"].isna().cumsum()
    return df


def area_chart(df, height=320, color=None, *, palette: Palette = LIGHT):
    """One series: area + line with a soft gradient fill."""
    color = color or palette.accent
    df = _plot_data(df)
    base = alt.Chart(df).encode(
        x=alt.X(
            "period:N",
            title=None,
            scale=alt.Scale(domain=sorted(df.period.unique())),
            axis=alt.Axis(labelAngle=0, grid=False, labelOverlap=True),
        ),
        y=alt.Y("score:Q", title=None, axis=alt.Axis(gridDash=[3, 3])),
        detail=alt.Detail("_segment:N"),
        tooltip=[
            alt.Tooltip("period", title="Period"),
            alt.Tooltip("score:Q", format="+.3f", title="Score"),
            alt.Tooltip("n:Q", title="Sentences"),
        ],
    )
    area = base.mark_area(
        line={"color": color, "strokeWidth": 2},
        interpolate="monotone",
        color=alt.Gradient(
            gradient="linear",
            x1=1,
            x2=1,
            y1=1,
            y2=0,
            stops=[
                alt.GradientStop(color=palette.bg + "00", offset=0),
                alt.GradientStop(color=color + "55", offset=1),
            ],
        ),
    )
    return _themed(
        area + base.mark_circle(color=color, size=36) + _zero_rule(palette),
        height,
        palette,
    )


def trend_chart(df, height=300, *, palette: Palette = LIGHT):
    """df: period, bank, score, n. One line per bank."""
    df = _plot_data(df)
    base = alt.Chart(df).encode(
        x=alt.X(
            "period:N",
            title=None,
            scale=alt.Scale(domain=sorted(df.period.unique())),
            axis=alt.Axis(labelAngle=0, grid=False, labelOverlap=True),
        ),
        y=alt.Y("score:Q", title=None, axis=alt.Axis(gridDash=[3, 3])),
        detail=alt.Detail("_segment:N"),
        color=alt.Color("bank:N", scale=_bank_scale(df.bank, palette)),
        tooltip=[
            "bank",
            "period",
            alt.Tooltip("score:Q", format="+.3f"),
            alt.Tooltip("n:Q", title="Sentences"),
        ],
    )
    return _themed(
        base.mark_line(strokeWidth=2.5, interpolate="monotone")
        + base.mark_circle(size=34)
        + _zero_rule(palette),
        height,
        palette,
    )


def history_chart(df, color, *, palette: Palette = LIGHT):
    """Aligned sentiment and volume panels; straight segments preserve observed buckets."""
    frame = _plot_data(df)
    periods = sorted(frame.period.unique())
    x = alt.X(
        "period:N",
        title=None,
        scale=alt.Scale(domain=periods),
        axis=alt.Axis(labels=False, ticks=False, grid=False),
    )
    base = alt.Chart(frame).encode(
        x=x,
        y=alt.Y(
            "score:Q",
            title="Sentiment score",
            scale=alt.Scale(zero=True),
            axis=alt.Axis(
                gridDash=[3, 3],
                gridColor=alt.condition(
                    "datum.value === 0",
                    alt.value(palette.muted),
                    alt.value(palette.line),
                ),
            ),
        ),
        detail=alt.Detail("_segment:N"),
        tooltip=[
            alt.Tooltip("period:N", title="Period"),
            alt.Tooltip("score:Q", title="Score", format="+.3f"),
            alt.Tooltip("n:Q", title="Scored sentences", format=","),
            alt.Tooltip("period_status:N", title="Coverage"),
        ],
    )
    # Keep each vconcat child a unit chart. Streamlit can then fit both panels
    # to the container; a nested layer triggers its overflowing 'pad' sizing.
    line = base.mark_line(
        color=color,
        strokeWidth=2.5,
        interpolate="linear",
        point=alt.OverlayMarkDef(filled=True, size=48),
    ).properties(height=230)
    volume = (
        alt.Chart(frame)
        .mark_bar(
            color=color, opacity=0.45, cornerRadiusTopLeft=2, cornerRadiusTopRight=2
        )
        .encode(
            x=alt.X(
                "period:N",
                title=None,
                scale=alt.Scale(domain=periods),
                axis=alt.Axis(labelAngle=0, labelOverlap=True, grid=False),
            ),
            y=alt.Y("n:Q", title="Sentences", axis=alt.Axis(tickCount=3, grid=False)),
            tooltip=[
                alt.Tooltip("period:N", title="Period"),
                alt.Tooltip("n:Q", title="Scored sentences", format=","),
                alt.Tooltip("period_status:N", title="Coverage"),
            ],
        )
        .properties(height=65)
    )
    return (
        alt.vconcat(line, volume, spacing=12)
        .resolve_scale(x="shared")
        .properties(background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor=palette.muted,
            titleColor=palette.muted,
            gridColor=palette.line,
            domainColor=palette.line,
            tickColor=palette.line,
            labelFont="Arial",
            titleFont="Arial",
            labelFontSize=13,
            titleFontSize=13,
        )
    )


def mix_chart(df, height=190, *, palette: Palette = LIGHT):
    """df: bank, label (Positive/Neutral/Negative), share (0..1), mid (segment centre, 0..1), pct (text), count, order.
    100% stacked bars."""
    INK, BG, POS, NEU, NEG = (
        palette.ink,
        palette.bg,
        palette.pos,
        palette.neu,
        palette.neg,
    )
    order = ["Positive", "Neutral", "Negative"]
    base = alt.Chart(df).encode(
        y=alt.Y(
            "bank:N",
            title=None,
            axis=alt.Axis(grid=False, labelColor=INK, labelFontSize=14),
        ),
        x=alt.X(
            "share:Q",
            title=None,
            stack="normalize",
            axis=alt.Axis(format="%", grid=False),
        ),
        color=alt.Color(
            "label:N", scale=alt.Scale(domain=order, range=[POS, NEU, NEG]), sort=order
        ),
        order=alt.Order("order:Q"),
        tooltip=[
            "bank",
            "label",
            alt.Tooltip("share:Q", format=".0%"),
            alt.Tooltip("count:Q", format=",", title="Sentences"),
        ],
    )
    bars = base.mark_bar(cornerRadius=4, height=26)
    text = (
        alt.Chart(df)
        .mark_text(fontWeight=600, fontSize=14)
        .encode(
            y=alt.Y("bank:N"),
            x=alt.X("mid:Q", scale=alt.Scale(domain=[0, 1])),
            text="pct:N",
            color=alt.condition(
                alt.datum.label == "Neutral", alt.value(INK), alt.value(BG)
            ),
        )
    )
    return _themed(bars + text, height, palette)


def source_chart(df, height=300, *, palette: Palette = LIGHT):
    """df: bank, source, score, n. Grouped bars: one cluster per source."""
    df = df.assign(source=df.source.map(pretty))
    base = alt.Chart(df).encode(
        x=alt.X("source:N", title=None, axis=alt.Axis(labelAngle=0, grid=False)),
        xOffset="bank:N",
        y=alt.Y("score:Q", title=None, axis=alt.Axis(gridDash=[3, 3])),
        color=alt.Color("bank:N", scale=_bank_scale(df.bank, palette)),
        tooltip=[
            "bank",
            "source",
            alt.Tooltip("score:Q", format="+.3f"),
            alt.Tooltip("n:Q", title="Sentences"),
        ],
    )
    return _themed(base.mark_bar(cornerRadius=3) + _zero_rule(palette), height, palette)


def heatmap_chart(df, height=None, *, palette: Palette = LIGHT):
    """Topic scores and counts; gaps have dashes and small samples are faded."""
    INK, BG = palette.ink, palette.bg
    df = df.assign(
        topic=df.aspect.map(pretty),
        thin=df.n < 30,
        display_score=df.score.map(lambda s: "—" if pd.isna(s) else f"{s:+.2f}"),
        volume=df.n.map(lambda n: f"n={int(n):,}"),
    )
    base = alt.Chart(df).encode(
        x=alt.X(
            "bank:N",
            title=None,
            axis=alt.Axis(
                orient="top", labelAngle=0, labelColor=INK, labelFontSize=13, grid=False
            ),
        ),
        y=alt.Y(
            "topic:N",
            title=None,
            axis=alt.Axis(labelColor=INK, labelFontSize=13, labelLimit=230, grid=False),
        ),
    )
    cells = base.mark_rect(cornerRadius=6, stroke=BG, strokeWidth=3).encode(
        color=alt.Color(
            "score:Q",
            legend=alt.Legend(title="Sentiment score", orient="bottom"),
            scale=alt.Scale(
                domain=[-1, 0, 1],
                range=[palette.heat_neg, palette.surface, palette.heat_pos],
                clamp=True,
                interpolate="rgb",
            ),
        ),
        opacity=alt.condition(alt.datum.thin, alt.value(0.35), alt.value(1)),
        tooltip=[
            alt.Tooltip("topic", title="Topic"),
            "bank",
            alt.Tooltip("score:Q", format="+.3f"),
            alt.Tooltip("n:Q", title="Sentences"),
        ],
    )
    background = base.mark_rect(
        cornerRadius=6, color=palette.surface_2, stroke=BG, strokeWidth=3
    )
    text = base.mark_text(fontSize=14, fontWeight=600, color=INK, dy=-7).encode(
        text="display_score:N"
    )
    counts = base.mark_text(fontSize=11, color=palette.muted, dy=13).encode(
        text="volume:N"
    )
    return _themed(
        background + cells + text + counts,
        height or max(180, df.topic.nunique() * 54),
        palette,
    )
