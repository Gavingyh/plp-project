"""Visual theme for the dashboard: charcoal canvas, raised surfaces, one mint
accent, side navigation, and the chart and card builders the pages use.
Pure presentation - no data logic lives here."""

import html

import altair as alt
import pandas as pd

# Surfaces (one dark theme for the whole app, never pure black)
BG = "#111318"
SURFACE = "#1A1D24"
SURFACE_2 = "#222630"
LINE = "#2B303B"

# Type
INK = "#E8EAEE"
MUTED = "#9199A8"        # 5.9:1 on SURFACE

# The single UI accent, and the dark ink used on top of it
ACCENT = "#A8E6D8"
ON_ACCENT = "#0F1B18"

# Semantic sentiment colours
POS = "#79DBA6"
NEU = "#3B4150"
NEG = "#F28B82"

# One colour per bank, used only for data series
BANK_COLORS = {"DBS": "#7CC4FF", "OCBC": "#C9A7F5", "UOB": "#F2C879"}

RADIUS = "14px"          # one corner radius: cards, buttons, inputs, nav items
FONT = "Geist, 'Segoe UI', system-ui, sans-serif"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap');
html, body, .stApp,
.stApp :is(p, h1, h2, h3, h4, h5, h6, li, label, button, input, textarea, div, td, th, a) {{
    font-family: {FONT};
}}
.stApp {{ background: {BG}; color: {INK}; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -.02em; font-weight: 600; }}
h3 {{ font-size: 1.15rem; }}
[data-testid="stCaptionContainer"], .stApp small {{ color: {MUTED}; }}
hr {{ border-color: {LINE}; }}

/* ---------- sidebar navigation ---------- */
section[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
.brand {{ font-size: 1.25rem; font-weight: 700; color: {INK}; letter-spacing: -.02em; }}
.brand-sub {{ color: {MUTED}; font-size: .8rem; margin: .1rem 0 1.6rem; }}
section[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
    width: 100%; padding: 11px 14px; border-radius: {RADIUS}; margin: 0;
    color: {MUTED}; transition: background .2s, color .2s; cursor: pointer;
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{ background: {SURFACE_2}; color: {INK}; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{ font-weight: 500; font-size: .95rem; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {{
    background: {ACCENT}; color: {ON_ACCENT};
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {{
    color: {ON_ACCENT}; font-weight: 600;
}}
.side-label {{ font-size: .75rem; color: {MUTED}; margin: 2rem 0 .4rem; letter-spacing: .02em; }}
.side-stat {{ display:flex; justify-content:space-between; padding:.45rem 0; font-size:.85rem;
              color:{INK}; border-bottom:1px solid {LINE}; font-variant-numeric: tabular-nums; }}
.side-stat span:first-child {{ color:{MUTED}; }}

/* ---------- page header ---------- */
.stApp p.hello {{ font-size: 1.9rem; font-weight: 700; color: {INK}; margin: 0; letter-spacing: -.03em; }}
.stApp p.sub {{ color: {MUTED}; font-size: .95rem; margin: .3rem 0 1.5rem; max-width: 65ch; line-height: 1.55; }}

/* ---------- surfaces ---------- */
.panel {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS};
          padding: 18px 20px; margin-bottom: 14px; }}
.panel h4 {{ margin: 0 0 .15rem; font-size: 1rem; }}
.panel .hint {{ color: {MUTED}; font-size: .85rem; margin: 0 0 .6rem; line-height: 1.5; max-width: 70ch; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {LINE} !important; border-radius: {RADIUS}; background: {SURFACE}; }}

/* the answer to "so what?", always first on a page */
.takeaway {{ background: {SURFACE}; border: 1px solid {LINE}; border-left: 3px solid {ACCENT};
             border-radius: {RADIUS}; padding: 16px 20px; margin-bottom: 18px; }}
.takeaway .kicker {{ color: {ACCENT}; font-size: .78rem; font-weight: 600; margin-bottom: .3rem; }}
.takeaway .body {{ font-size: 1.05rem; line-height: 1.55; color: {INK}; max-width: 75ch; }}

/* ---------- bank cards ---------- */
.bank-card {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS};
              padding: 18px 20px; height: 100%; }}
.bank-top {{ display:flex; align-items:center; gap:10px; font-weight:600; font-size:.95rem; }}
.bank-dot {{ width:10px; height:10px; border-radius:50%; }}
.bank-score {{ font-size: 2.2rem; font-weight: 700; letter-spacing: -.03em; line-height: 1.1;
               margin-top: 14px; font-variant-numeric: tabular-nums; }}
.bank-word {{ font-size: .9rem; margin-top: 2px; }}
.bank-meta {{ color: {MUTED}; font-size: .8rem; margin-top: 12px; line-height: 1.5; }}
.bank-card svg {{ float: right; margin-top: -58px; }}
.up {{ color: {POS}; }} .down {{ color: {NEG}; }} .flat {{ color: {MUTED}; }}

/* ---------- strengths / weaknesses ---------- */
.sw {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; padding: 16px 18px; height: 100%; }}
.sw .who {{ display:flex; align-items:center; gap:8px; font-weight:600; margin-bottom:.7rem; }}
.sw .row {{ display:flex; justify-content:space-between; gap:12px; padding:.4rem 0;
            font-size:.9rem; border-top:1px solid {LINE}; }}
.sw .row span:last-child {{ font-variant-numeric: tabular-nums; }}
.sw .tag {{ color: {MUTED}; font-size:.75rem; margin-top:.5rem; }}

/* ---------- evidence ---------- */
.quote {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS};
          padding: 14px 18px; margin-bottom: 10px; }}
.quote .text {{ line-height: 1.55; color: {INK}; }}
.quote .meta {{ color: {MUTED}; font-size: .8rem; margin-top: .5rem; display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
.quote a {{ color: {ACCENT}; text-decoration: none; }}
.chip {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size:.75rem; font-weight:600; }}
.chip.pos {{ background: rgba(121,219,166,.14); color: {POS}; }}
.chip.neg {{ background: rgba(242,139,130,.14); color: {NEG}; }}
.chip.neu {{ background: rgba(145,153,168,.16); color: {MUTED}; }}

/* ---------- native widgets ---------- */
div[data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; padding: 14px 18px; }}
div[data-testid="stMetricValue"] {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.stButton > button {{ border-radius: {RADIUS}; border: 1px solid {LINE}; background: {SURFACE_2}; color: {INK};
    transition: border-color .2s, color .2s, transform .1s; }}
.stButton > button:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
.stButton > button:active {{ transform: translateY(1px); }}
.stButton > button:focus-visible {{ outline: 2px solid {ACCENT}; outline-offset: 2px; }}
.stButton > button[kind="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: 600; }}
div[data-baseweb="select"] > div {{ border-radius: {RADIUS}; background: {SURFACE_2}; border: 1px solid {LINE}; }}
div[data-testid="stDataFrame"] {{ border-radius: {RADIUS}; overflow: hidden; }}
details {{ background: {SURFACE}; border: 1px solid {LINE} !important; border-radius: {RADIUS}; }}
[data-testid="stChatMessage"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}; }}

@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style>
"""


# ---------- plain-language helpers ----------

def pretty(name: str) -> str:
    """'net_interest_margin' -> 'Net interest margin'."""
    return str(name).replace("_", " ").capitalize()


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
    return (f'<div class="takeaway"><div class="kicker">{html.escape(kicker)}</div>'
            f'<div class="body">{body}</div></div>')


def sparkline(values, color=ACCENT, w=96, h=34) -> str:
    """Inline SVG polyline for a bank card; empty string if too few points."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = " ".join(
        f"{i * w / (len(vals) - 1):.1f},{h - 3 - (v - lo) / span * (h - 6):.1f}"
        for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" points="{pts}"/></svg>')


def bank_card(bank: str, score: float | None, n: int, delta: float | None,
              spark_values) -> str:
    color = BANK_COLORS.get(bank, MUTED)
    head = (f'<div class="bank-top"><span class="bank-dot" style="background:{color}"></span>'
            f'{html.escape(bank)}</div>')
    if score is None:
        return f'<div class="bank-card">{head}<div class="bank-score">No data</div></div>'
    if delta is None:
        trend = ""
    elif abs(delta) < 0.005:
        trend = '<span class="flat">Last 30 days: in line with all-time</span><br>'
    else:
        cls, word = ("up", "above") if delta > 0 else ("down", "below")
        trend = f'<span class="{cls}">Last 30 days: {abs(delta):.3f} {word} all-time</span><br>'
    return (
        f'<div class="bank-card">{head}'
        f'<div class="bank-score">{score:+.3f}</div>'
        f'<div class="bank-word" style="color:{color}">{score_word(score)}</div>'
        f'{sparkline(spark_values, color)}'
        f'<div class="bank-meta">{trend}Based on {n:,} sentences</div></div>')


def strengths_card(bank: str, best: list, worst: list) -> str:
    """best/worst are lists of (aspect, score); empty lists mean too little data."""
    color = BANK_COLORS.get(bank, MUTED)

    def rows(items, cls):
        return "".join(
            f'<div class="row"><span>{html.escape(pretty(a))}</span>'
            f'<span class="{cls}">{s:+.2f}</span></div>' for a, s in items)
    if best or worst:
        body = ('<div class="tag">Best</div>' + rows(best, "up")
                + '<div class="tag" style="margin-top:.9rem">Weakest</div>' + rows(worst, "down"))
    else:
        body = '<div class="tag">Not enough sentences per topic yet.</div>'
    return (f'<div class="sw"><div class="who"><span class="bank-dot" style="background:{color}">'
            f'</span>{html.escape(bank)}</div>{body}</div>')


def quote_card(text, source, published, url, label=None, confidence=None) -> str:
    chip = ""
    if label:
        key = {"positive": "pos", "negative": "neg"}.get(str(label).lower(), "neu")
        conf = f" {confidence:.0%}" if confidence is not None and pd.notna(confidence) else ""
        chip = f'<span class="chip {key}">{html.escape(str(label).capitalize())}{conf}</span>'
    link = f'<a href="{html.escape(str(url))}" target="_blank">Open source</a>' if url else ""
    return (f'<div class="quote"><div class="text">{html.escape(str(text))}</div>'
            f'<div class="meta">{chip}<span>{html.escape(pretty(source))}</span>'
            f'<span>{html.escape(str(published)[:10])}</span>{link}</div></div>')


def sentiment_cmap():
    """Dark red - charcoal - dark green scale for the number tables; needs matplotlib."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("sentiment", ["#7A3A3F", SURFACE_2, "#2E6B55"])


# ---------- charts ----------

def _themed(chart, height):
    return (chart.properties(height=height, background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=LINE, domainColor=LINE,
                            tickColor=LINE, labelFont="Geist", titleFont="Geist", labelFontSize=12)
            .configure_legend(labelColor=INK, titleColor=MUTED, labelFont="Geist",
                              orient="top", title=None, symbolType="circle", labelFontSize=12))


def _bank_scale(banks):
    present = [b for b in BANK_COLORS if b in set(banks)]
    return alt.Scale(domain=present, range=[BANK_COLORS[b] for b in present])


def _zero_rule():
    return alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=MUTED, strokeDash=[4, 4]).encode(y="y:Q")


def area_chart(df, height=320, color=ACCENT):
    """One series: area + line with a soft gradient fill."""
    base = alt.Chart(df).encode(
        x=alt.X("period:N", title=None, axis=alt.Axis(labelAngle=0, grid=False, labelOverlap=True)),
        y=alt.Y("score:Q", title=None, axis=alt.Axis(gridDash=[3, 3])),
        tooltip=[alt.Tooltip("period", title="Period"), alt.Tooltip("score:Q", format="+.3f", title="Score"),
                 alt.Tooltip("n:Q", title="Sentences")])
    area = base.mark_area(
        line={"color": color, "strokeWidth": 2}, interpolate="monotone",
        color=alt.Gradient(gradient="linear", x1=1, x2=1, y1=1, y2=0,
                           stops=[alt.GradientStop(color="rgba(17,19,24,0)", offset=0),
                                  alt.GradientStop(color=color + "55", offset=1)]))
    return _themed(area + base.mark_circle(color=color, size=36) + _zero_rule(), height)


def trend_chart(df, height=300):
    """df: period, bank, score, n. One line per bank."""
    base = alt.Chart(df).encode(
        x=alt.X("period:N", title=None, axis=alt.Axis(labelAngle=0, grid=False, labelOverlap=True)),
        y=alt.Y("score:Q", title=None, axis=alt.Axis(gridDash=[3, 3])),
        color=alt.Color("bank:N", scale=_bank_scale(df.bank)),
        tooltip=["bank", "period", alt.Tooltip("score:Q", format="+.3f"),
                 alt.Tooltip("n:Q", title="Sentences")])
    return _themed(base.mark_line(strokeWidth=2.5, interpolate="monotone")
                   + base.mark_circle(size=34) + _zero_rule(), height)


def mix_chart(df, height=190):
    """df: bank, label (Positive/Neutral/Negative), share (0..1), mid (segment centre, 0..1), pct (text), count, order.
    100% stacked bars."""
    order = ["Positive", "Neutral", "Negative"]
    base = alt.Chart(df).encode(
        y=alt.Y("bank:N", title=None, axis=alt.Axis(grid=False, labelColor=INK, labelFontSize=13)),
        x=alt.X("share:Q", title=None, stack="normalize", axis=alt.Axis(format="%", grid=False)),
        color=alt.Color("label:N", scale=alt.Scale(domain=order, range=[POS, NEU, NEG]), sort=order),
        order=alt.Order("order:Q"),
        tooltip=["bank", "label", alt.Tooltip("share:Q", format=".0%"),
                 alt.Tooltip("count:Q", format=",", title="Sentences")])
    bars = base.mark_bar(cornerRadius=4, height=26)
    text = alt.Chart(df).mark_text(fontWeight=600, fontSize=12).encode(
        y=alt.Y("bank:N"),
        x=alt.X("mid:Q", scale=alt.Scale(domain=[0, 1])),
        text="pct:N",
        color=alt.condition(alt.datum.label == "Neutral", alt.value(INK), alt.value(BG)))
    return _themed(bars + text, height)


def source_chart(df, height=300):
    """df: bank, source, score, n. Grouped bars: one cluster per source."""
    df = df.assign(source=df.source.map(pretty))
    base = alt.Chart(df).encode(
        x=alt.X("source:N", title=None, axis=alt.Axis(labelAngle=0, grid=False)),
        xOffset="bank:N",
        y=alt.Y("score:Q", title=None, axis=alt.Axis(gridDash=[3, 3])),
        color=alt.Color("bank:N", scale=_bank_scale(df.bank)),
        tooltip=["bank", "source", alt.Tooltip("score:Q", format="+.3f"),
                 alt.Tooltip("n:Q", title="Sentences")])
    return _themed(base.mark_bar(cornerRadius=3) + _zero_rule(), height)


def heatmap_chart(df, height=None):
    """df: bank, aspect, score, n. Cells with few sentences are faded."""
    df = df.assign(topic=df.aspect.map(pretty), thin=df.n < 30)
    base = alt.Chart(df).encode(
        x=alt.X("bank:N", title=None, axis=alt.Axis(orient="top", labelAngle=0, labelColor=INK,
                                                    labelFontSize=13, grid=False)),
        y=alt.Y("topic:N", title=None, axis=alt.Axis(labelColor=INK, labelFontSize=13, grid=False)))
    cells = base.mark_rect(cornerRadius=6, stroke=BG, strokeWidth=3).encode(
        color=alt.Color("score:Q", legend=None,
                        scale=alt.Scale(domain=[-0.1, 0, 0.1], range=[NEG, SURFACE_2, POS], clamp=True)),
        opacity=alt.condition(alt.datum.thin, alt.value(0.35), alt.value(1)),
        tooltip=[alt.Tooltip("topic", title="Topic"), "bank", alt.Tooltip("score:Q", format="+.3f"),
                 alt.Tooltip("n:Q", title="Sentences")])
    text = base.mark_text(fontSize=12, fontWeight=600, color=INK).encode(
        text=alt.Text("score:Q", format="+.2f"))
    return _themed(cells + text, height or max(220, df.topic.nunique() * 48))
