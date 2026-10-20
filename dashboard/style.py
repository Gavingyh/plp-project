"""Presentation themes, side navigation, and shared chart/card builders.
Pure presentation - no data logic lives here."""

from dataclasses import dataclass
import html
from urllib.parse import quote, urlsplit

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
    brand_icon = quote(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
        f'<path d="M2 13h5l3-8 4 15 3-9h5" stroke="{ON_ACCENT}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>',
        safe="",
    )
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
/* Share the top row with Streamlit's native, accessible collapse control. */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{ position:relative; height:36px; min-height:36px; margin:16px 0 -36px; z-index:1; pointer-events:none; }}
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {{ margin:0; pointer-events:auto; }}
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button {{ color:{MUTED}; }}
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button :is(span,svg) {{ color:inherit; }}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding-top:0; padding-bottom:20px; }}
/* Grow the spacer on tall screens; let the entire sidebar scroll when needed. */
.st-key-sidebar_layout {{ min-height:calc(100dvh - 36px); }}
.st-key-sidebar_layout > [data-testid="stLayoutWrapper"] {{ flex-shrink:0; }}
.st-key-sidebar_layout > [data-testid="stLayoutWrapper"]:has(> .st-key-sidebar_utilities) {{ margin-top:auto; }}
.st-key-sidebar_utilities {{ gap:12px; }}
.st-key-sidebar_brand {{ gap:0; }}
.stApp .st-key-brand_home button {{ display:flex; align-items:center; justify-content:flex-start; gap:10px;
    width:calc(100% - 40px); min-height:36px; padding:0; border:0; border-radius:8px;
    background:transparent; color:{INK}; box-shadow:none; }}
.st-key-brand_home button::before {{ content:""; width:32px; height:32px; flex:0 0 32px; border-radius:10px;
    background:{ACCENT} url("data:image/svg+xml,{brand_icon}") center / 21px 21px no-repeat; }}
.st-key-brand_home button > div {{ min-width:0; justify-content:flex-start; }}
.st-key-brand_home button > div > span {{ min-width:0; }}
.st-key-brand_home button [data-testid="stMarkdownContainer"] {{ min-width:0; overflow:hidden; }}
.st-key-brand_home button p {{ font-size:1.45rem; line-height:1.6; font-weight:750; letter-spacing:-.04em;
    color:inherit; margin:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.stApp .st-key-brand_home button:hover {{ background:transparent; color:{ACCENT}; }}
.stApp .st-key-brand_home button:active {{ transform:none; }}
.stApp .st-key-brand_home button:focus-visible {{ outline:2px solid {ACCENT}; outline-offset:4px; }}
.brand-sub {{ color: {MUTED}; font-size: .72rem; margin: .55rem 0 .65rem; letter-spacing:.025em; }}
section[data-testid="stSidebar"] .st-key-nav,
section[data-testid="stSidebar"] .st-key-nav [data-testid="stRadio"],
section[data-testid="stSidebar"] .st-key-nav [role="radiogroup"],
section[data-testid="stSidebar"] .st-key-nav [role="radiogroup"] > div {{ width:100% !important; min-width:0; }}
section[data-testid="stSidebar"] .st-key-nav [role="radiogroup"] {{ align-items:stretch; gap:3px; }}
section[data-testid="stSidebar"] .st-key-nav [role="radiogroup"] > div:has(input[value="5"]) {{ margin-top:12px; padding-top:12px; border-top:1px solid {LINE}; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
    width:100%; box-sizing:border-box; min-height:42px; padding:9px 12px; border-radius:8px; margin:0;
    color: {MUTED}; transition: background .2s, color .2s; cursor: pointer;
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{ background: {SURFACE_2}; color: {INK}; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:has(input:focus-visible) {{ outline:2px solid {ACCENT}; outline-offset:2px; }}
/* hide the radio circle: the element just before the option's name (Streamlit 1.63 wraps both in one block) */
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] div:has(+ [data-testid="stMarkdownContainer"]) {{ display: none; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{ display:flex; align-items:center; gap:10px; font-weight:500; font-size:.9rem; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] [role="img"] {{ width:20px; font-size:18px; text-align:center; }}
.stApp label[data-testid="stRadioOption"] {{ color: {INK}; }}
.stApp label[data-testid="stRadioOption"] p {{ color: inherit; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {{
    background: {ACCENT}; color: {ON_ACCENT};
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {{
    color: {ON_ACCENT}; font-weight: 600;
}}
.side-label {{ font-size:.65rem; text-transform:uppercase; font-weight:700; color:{MUTED}; margin:0 0 .6rem; letter-spacing:.12em; }}
.st-key-sidebar_snapshot {{ border-top:1px solid {LINE}; margin-top:10px; padding-top:18px; gap:10px; }}
.side-stat {{ display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:baseline; gap:8px; padding:8px 0; font-size:.77rem;
              color:{INK}; border-bottom:1px solid {LINE}; font-variant-numeric:tabular-nums; }}
.side-stat:last-child {{ border-bottom:0; }}
.side-stat span:first-child {{ color:{MUTED}; }}
.side-stat span:last-child {{ text-align:right; font-weight:600; white-space:nowrap; }}
.stApp p.side-note {{ color:{MUTED}; font-size:.71rem; line-height:1.55; margin:0; }}
:is(.st-key-sidebar_snapshot, .st-key-sidebar_help) [data-testid="stExpander"] details {{ background:transparent; border:0 !important; border-radius:6px; }}
:is(.st-key-sidebar_snapshot, .st-key-sidebar_help) [data-testid="stExpander"] summary {{ padding:5px 0; min-height:28px; }}
:is(.st-key-sidebar_snapshot, .st-key-sidebar_help) [data-testid="stExpander"] summary p {{ font-size:.74rem; color:{MUTED}; }}
.st-key-sidebar_snapshot [data-testid="stCaptionContainer"] p {{ font-size:.74rem; }}
.st-key-sidebar_help {{ border-top:1px solid {LINE}; padding-top:10px; gap:6px; }}
.st-key-sidebar_help .side-label {{ margin-bottom:0; }}
.st-key-sidebar_help [data-testid="stMarkdownContainer"]:has(> .side-label) {{ margin-bottom:0; }}
.st-key-sidebar_help [data-testid="stMarkdownContainer"] p {{ color:{INK}; font-size:.75rem; line-height:1.65; }}
.st-key-sidebar_help [data-testid="stCaptionContainer"] p {{ color:{MUTED}; font-size:.68rem; overflow-wrap:anywhere; }}
.st-key-sidebar_settings {{ gap:4px; }}
.st-key-sidebar_settings [data-testid="stWidgetLabel"] p {{ font-weight:500; font-size:.82rem; }}

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
.st-key-pipeline_controls, .st-key-pipeline_activity, [class*="st-key-pipeline_source_"] {{
    background:{SURFACE}; border:1px solid {LINE} !important; border-radius:{RADIUS}; padding:20px !important;
}}
.st-key-pipeline_controls, .st-key-pipeline_activity {{ gap:12px; }}
.st-key-pipeline_run {{ gap:10px; }}
[class*="st-key-pipeline_source_"] {{ background:{BG}; padding:14px !important; gap:10px; min-height:180px; }}
[class*="st-key-pipeline_source_"]:has(input:checked) {{ border-color:{ACCENT}88 !important; background:{ACCENT}06; }}
.st-key-pipeline_controls [data-testid="stWidgetLabel"] p {{ font-size:.78rem; line-height:1.45; }}
.st-key-pipeline_controls [data-testid="stCaptionContainer"] p {{ font-size:.73rem; }}
.pipeline-source-count {{ display:flex; flex-direction:column; gap:2px; margin:5px 0 10px; }}
.pipeline-source-count strong {{ font-size:1.85rem; line-height:1.1; color:{INK}; font-weight:750; letter-spacing:-.035em; font-variant-numeric:tabular-nums; }}
.pipeline-source-count span {{ color:{MUTED}; font-size:.71rem; }}
.pipeline-folder {{ color:{MUTED}; font-size:.68rem; padding-top:10px; border-top:1px solid {LINE}; overflow-wrap:anywhere; }}
.pipeline-selection {{ display:flex; flex-direction:column; gap:4px; padding:0 0 4px; }}
.pipeline-selection strong {{ font-size:.8rem; color:{INK}; font-weight:600; }}
.pipeline-selection span {{ font-size:.7rem; color:{MUTED}; }}
.pipeline-scope-note {{ color:{MUTED}; font-size:.73rem; line-height:1.65; padding:4px 0; }}
.pipeline-scope-note strong {{ color:{INK}; font-weight:600; }}
.st-key-pipeline_controls button:disabled {{ background:{SURFACE_2} !important; color:{MUTED} !important; border-color:{LINE} !important; cursor:not-allowed; }}
.st-key-pipeline_controls button:disabled p {{ color:{MUTED}; }}
.st-key-pipeline_controls :is(pre,code), .st-key-pipeline_run :is(pre,code) {{ background:{SURFACE_2} !important; color:{INK} !important; }}
.st-key-pipeline_run [data-testid="stMetric"] {{ padding:10px !important; border:0 !important; background:{BG}; border-radius:8px; }}
.st-key-pipeline_run [data-testid="stMetricValue"] {{ font-size:1.4rem; }}
.st-key-pipeline_run [data-testid="stMetricLabel"] p {{ font-size:.68rem; }}
/* Streamlit subtracts paragraph spacing from Markdown. This custom header
   has no trailing paragraph margin, so that subtraction overlaps the alert. */
.st-key-pipeline_run [data-testid="stMarkdownContainer"]:has(> .pipeline-run-header) {{ margin-bottom:0; }}
.pipeline-run-header {{ display:flex; flex-direction:column; gap:14px; padding:3px 0 2px; }}
.pipeline-run-heading {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px 14px; }}
.pipeline-run-heading h3 {{ margin:0; padding:0; font-size:1rem; line-height:1.45; }}
.pipeline-state {{ display:inline-flex; align-items:center; gap:7px; flex:0 1 auto; max-width:100%; box-sizing:border-box;
    padding:6px 10px; border-radius:20px; font-size:.7rem; line-height:1.5; font-weight:600;
    white-space:normal; overflow-wrap:anywhere; background:{SURFACE_2}; color:{INK}; }}
.pipeline-state::before {{ content:""; width:6px; height:6px; flex:0 0 6px; border-radius:50%; background:currentColor; }}
.pipeline-run-times {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px 18px;
    padding:12px 0 0; margin:0; border-top:1px solid {LINE}; }}
.pipeline-run-times > div {{ min-width:0; }}
.pipeline-run-times dt {{ margin:0 0 4px; color:{MUTED}; font-size:.65rem; line-height:1.4; }}
.pipeline-run-times dd {{ margin:0; color:{INK}; font-size:.73rem; line-height:1.55; overflow-wrap:anywhere; }}
.st-key-pipeline_run [data-testid="stAlert"] {{ border-radius:10px; }}
.st-key-pipeline_run [data-testid="stAlert"] p {{ font-size:.8rem; line-height:1.6; }}
.state-completed_with_warnings {{ background:{'#FFF4DB' if palette.mode == 'light' else '#3C3020'}; color:{'#865B15' if palette.mode == 'light' else '#F0CB80'}; }}
.state-running, .state-queued {{ background:{ACCENT}18; color:{ACCENT}; }}
.state-completed {{ background:{POS}18; color:{POS}; }}
.state-failed, .state-interrupted {{ background:{NEG}18; color:{NEG}; }}
.pipeline-stages {{ display:flex; flex-direction:column; gap:0; margin:0 0 8px; }}
.pipeline-step {{ display:flex; gap:10px; align-items:center; padding:11px 6px; border-bottom:1px solid {LINE}; }}
.pipeline-step:last-child {{ border-bottom:0; }}
.pipeline-step > div {{ flex:1; min-width:0; }}
.pipeline-step-number {{ display:grid; place-items:center; width:24px; height:24px; flex-shrink:0; border-radius:50%; background:{SURFACE_2}; color:{MUTED}; font-size:.7rem; }}
.pipeline-step strong {{ display:block; font-size:.75rem; color:{INK}; font-weight:500; }}
.pipeline-step-status {{ color:{MUTED}; font-size:.68rem; white-space:nowrap; }}
.step-running {{ background:{ACCENT}08; border-radius:6px; }}
.step-completed .pipeline-step-number {{ color:{POS}; background:{POS}16; }}
.step-failed, .step-interrupted {{ background:{NEG}08; border-radius:6px; }}
.step-failed :is(.pipeline-step-number,.pipeline-step-status), .step-interrupted .pipeline-step-status {{ color:{NEG}; }}
.pipeline-empty {{ display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:260px; border:1px dashed {LINE}; border-radius:{RADIUS}; padding:30px; text-align:center; background:{BG}; }}
.pipeline-empty-icon {{ color:{ACCENT}; font-size:2rem; padding:8px 15px; background:{ACCENT}0C; border-radius:12px; margin-bottom:14px; }}
.pipeline-empty h3 {{ color:{INK}; font-size:1rem; padding:0; margin:0 0 8px; }}
.pipeline-empty p {{ color:{MUTED}; font-size:.8rem; line-height:1.65; max-width:32ch; margin:0; }}
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

/* ---------- conversation ---------- */
.st-key-ask_view {{ max-width:920px; margin-inline:auto; }}
.ask-context {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; color:{INK}; font-size:.76rem; font-weight:600; }}
.ask-context > span {{ width:6px; height:6px; border-radius:50%; background:{ACCENT}; }}
.ask-context small {{ display:block; flex-basis:100%; margin-left:14px; font-size:.7rem; font-weight:400; color:{MUTED}; }}
.st-key-clear_chat button {{ min-height:34px; }}
.st-key-clear_chat button p {{ font-size:.73rem; }}
.st-key-clear_chat button:disabled {{ color:{MUTED}; opacity:.55; }}
.ask-welcome {{ padding:28px 26px 24px; background:linear-gradient(120deg, {SURFACE}, {ACCENT}0A);
    border:1px solid {LINE}; border-radius:14px; margin:6px 0 8px; }}
.ask-welcome h3 {{ font-size:1.5rem; padding:0; margin:10px 0 8px; color:{INK}; letter-spacing:-.035em; }}
.ask-welcome h3 span {{ color:inherit; font-size:inherit; }}
.ask-welcome p {{ font-size:.85rem; color:{MUTED}; line-height:1.65; margin:0; max-width:65ch; }}
[class*="st-key-ask_starter_"] {{ background:{SURFACE}; border:1px solid {LINE} !important;
    border-radius:12px; padding:17px 18px 12px !important; gap:8px; height:100%;
    transition:border-color .15s, box-shadow .15s; }}
[class*="st-key-ask_starter_"]:hover {{ border-color:{ACCENT}77 !important; box-shadow:0 4px 14px #0F233B08; }}
.ask-card-label {{ color:{ACCENT}; font-size:.64rem; text-transform:uppercase; letter-spacing:.08em; font-weight:700; }}
[class*="st-key-ask_starter_"] .stButton > button {{ justify-content:flex-start; align-items:flex-start;
    text-align:left; background:transparent !important; border:0 !important; padding:0; min-height:58px; }}
[class*="st-key-ask_starter_"] .stButton > button p {{ color:{INK}; font-size:.86rem; font-weight:600; line-height:1.6; text-align:left; }}
.st-key-ask_view [data-testid="stChatMessage"] {{ padding:18px 20px; border-radius:12px; gap:14px; }}
.st-key-ask_view [class*="st-key-ask_user_"] [data-testid="stChatMessage"] {{ background:{SURFACE_2}; border-color:transparent; }}
.st-key-ask_view [class*="st-key-ask_assistant_"] [data-testid="stChatMessage"] {{ background:{SURFACE}; border-color:{LINE}; }}
.st-key-ask_view [data-testid="stChatMessageAvatarCustom"] {{ background:{ACCENT}16; color:{ACCENT}; border-radius:9px; }}
.st-key-ask_view [class*="st-key-ask_user_"] [data-testid="stChatMessageAvatarCustom"] {{ background:{BG}; color:{MUTED}; }}
.st-key-ask_view [data-testid="stChatMessageAvatarCustom"] :is(span,svg) {{ color:inherit; }}
.ask-author {{ color:{MUTED}; font-size:.65rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; margin-bottom:6px; }}
.st-key-ask_view [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] p {{ color:{INK}; font-size:.92rem; line-height:1.75; }}
.st-key-ask_view [data-testid="stChatMessageContent"] a {{ color:{ACCENT}; text-decoration:underline; text-underline-offset:2px; }}
.st-key-ask_view [data-testid="stChatMessageContent"] [data-testid="stCaptionContainer"] p {{ font-size:.73rem; }}
.st-key-ask_view [data-testid="stSpinner"] p {{ color:{MUTED}; font-size:.86rem; }}
.st-key-ask_composer {{ max-width:920px; margin-inline:auto; gap:7px; }}
.st-key-ask_composer [data-testid="stCaptionContainer"] p {{ text-align:center; font-size:.68rem; line-height:1.5; margin:0; }}
.st-key-ask_input {{ max-width:920px; margin-inline:auto; }}
.stApp:has(.st-key-ask_view) [data-testid="stBottomBlockContainer"] {{ padding:1rem 2.5rem 1.5rem; }}
.stApp .st-key-ask_input [data-testid="stChatInput"] {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; box-shadow:0 3px 14px #0F233B06; }}
.st-key-ask_input [data-testid="stChatInput"] div {{ background:transparent; border-color:{LINE}; }}
.st-key-ask_input [data-testid="stChatInput"]:focus-within {{ border-color:{ACCENT}; box-shadow:0 0 0 2px {ACCENT}16; }}
.st-key-ask_input textarea {{ background:{SURFACE} !important; color:{INK}; font-size:.9rem; }}
.st-key-ask_input button:not(:disabled) {{ background:{ACCENT}; color:{ON_ACCENT}; border-radius:8px; }}

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
    .pipeline-run-heading {{ align-items:flex-start; flex-direction:column; }}
    .pipeline-run-times {{ grid-template-columns:1fr; gap:12px; }}
    .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
    .stApp p.hello {{ font-size: 1.65rem; }}
    .bank-score {{ font-size: 2rem; }}
    .bank-card svg {{ display: none; }}
    .heading-top {{ flex-wrap:wrap; }}
    .control-description {{ border:0; padding:0; }}
    .quote {{ padding:16px; }}
    .quote .meta a {{ margin-left:0; }}
    .stApp:has(.st-key-ask_view) [data-testid="stBottomBlockContainer"] {{ padding:1rem; }}
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
