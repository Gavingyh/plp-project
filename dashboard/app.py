"""
Streamlit dashboard — see docs/DESIGN.md.

Five pages in a side navigation: overview, topics, trends, evidence and chat. Every view carries the disclosures the design calls for — sample size
(n), last-refresh timestamp, and a not-financial-advice notice. Those are the
trust anchors, not decoration.

USAGE:
  streamlit run dashboard/app.py
"""

import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.api_client import ApiError
from dashboard.chat import GUARD_LABELS, send_chat
from dashboard import data
from config.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

BANKS = ["DBS", "OCBC", "UOB"]

# pandas' Styler.background_gradient needs matplotlib, and it does not import it
# until the Styler is RENDERED — inside st.dataframe, not where the Styler is
# built. So a missing matplotlib produced a dashboard that started cleanly,
# answered its health check, and then crashed on the heatmap tables. It was
# absent from requirements.txt from the first commit, so those two tables had
# never once rendered.
#
# matplotlib is a declared dependency now. This guard exists so that if it goes
# missing again the tables lose their colour scale instead of taking down the
# page, and so the degradation is visible rather than silent.
try:
    import matplotlib  # noqa: F401

    HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover - exercised by tests/test_dashboard_styling.py
    HAS_MATPLOTLIB = False


def heatmap_table(frame: pd.DataFrame):
    """A red-to-green graded table, or a plain rounded one without matplotlib.

    Returns something st.dataframe can render either way.
    """
    if HAS_MATPLOTLIB:
        return frame.style.background_gradient(
            cmap=sentiment_cmap(palette=palette), vmin=-1, vmax=1
        ).format("{:.3f}")
    return frame.round(3)


st.set_page_config(
    page_title="SG Bank Sentiment Dashboard",
    page_icon=":material/monitoring:",
    layout="wide",
)

from dashboard.style import (  # noqa: E402
    DARK,
    LIGHT,
    css,
    area_chart,
    bank_card,
    heatmap_chart,
    mix_chart,
    pretty,
    quote_card,
    score_word,
    sentiment_cmap,
    source_chart,
    strengths_card,
    takeaway,
    trend_chart,
)

with st.sidebar:
    st.markdown(
        '<div class="brand">BankPulse</div>'
        '<div class="brand-sub">Singapore bank sentiment</div>',
        unsafe_allow_html=True,
    )
    dark_mode = st.toggle(
        "Dark mode",
        value=st.query_params.get("theme") == "dark",
        key="dark_mode",
        help="Switch between white and dark backgrounds.",
    )

palette = DARK if dark_mode else LIGHT
if dark_mode:
    if st.query_params.get("theme") != "dark":
        st.query_params["theme"] = "dark"
elif "theme" in st.query_params:
    del st.query_params["theme"]
st.markdown(css(palette), unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_index() -> pd.DataFrame:
    return data.load_index()


@st.cache_data(ttl=300)
def load_evidence(bank: str, aspect: str) -> pd.DataFrame:
    return data.load_evidence(bank, aspect)


@st.cache_data(ttl=300)
def load_source_breakdown(window: str = "all_time") -> pd.DataFrame:
    return data.load_source_breakdown(window)


@st.cache_data(ttl=300)
def load_time_series(bank: str, aspect: str, bucket: str) -> pd.DataFrame:
    return data.load_time_series(bank, aspect, bucket)


@st.cache_data(ttl=300)
def load_analyst_consensus() -> pd.DataFrame:
    return data.load_analyst_consensus()


@st.cache_data(ttl=300)
def load_suggestions() -> list[dict]:
    return data.load_suggestions(limit=6)


def render_chat_message(message: dict):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("citation_unverified"):
            st.warning(
                "Verification warning: supporting citations could not be verified. Do not rely on this answer."
            )
        if message.get("unverified_numbers"):
            numbers = ", ".join(str(number) for number in message["unverified_numbers"])
            st.warning(
                f"Verification warning: these figures could not be verified: {numbers}."
            )
        if message.get("guard"):
            label = GUARD_LABELS.get(message["guard"], "Predefined response")
            st.caption(f"Response type: {label}")


def disclosure_footer():
    st.caption(
        f"Not financial advice. Data as of: {data_as_of}. Index computed: {computed_at}."
    )
    with st.expander("How to read these scores and their limitations"):
        st.markdown(
            "**Scores run from −1 (negative) to +1 (positive); 0 is neutral.** "
            "The index weights sentence labels by confidence and source, and shrinks "
            "small samples toward neutral. The sentence mix shows raw label shares, "
            "so it is not the same calculation as the index.\n\n"
            "Sentiment comes from the selected fine-tuned FinBERT ensemble. A local LLM "
            "assigns each sentence one topic. Source coverage differs between banks; "
            "earnings releases reflect management's own framing. These scores describe "
            "the collected text, rather than a representative survey of investors. "
            "Very small samples show no score.\n\n"
            "Yahoo analyst consensus is separate from sentiment. Recent 7-day and "
            "30-day windows end on the newest stored data date, not today's date."
        )
        st.caption(f"Sentiment model: {model_version}.")


try:
    df_all = load_index()
except ApiError as exc:
    st.error(str(exc))
    st.stop()
if df_all.empty:
    st.warning(
        "No sentiment results are available for the selected model. "
        "Check that the API is using the project's matching database snapshot."
    )
    st.stop()

data_as_of = next(iter(df_all["data_as_of"].dropna()), "Unknown")
timestamps = pd.to_datetime(df_all["computed_at"], utc=True, errors="coerce").dropna()
computed_at = (
    timestamps.max().strftime("%Y-%m-%d %H:%M UTC")
    if not timestamps.empty
    else "Unknown"
)
model_version = (
    ", ".join(sorted(df_all["model_version"].dropna().unique())) or "Unknown"
)

PAGES = {
    "Overview": ":material/space_dashboard:",
    "Topics": ":material/category:",
    "Trends": ":material/show_chart:",
    "Evidence": ":material/format_quote:",
    "Ask": ":material/chat:",
}
_total = df_all[(df_all.window == "all_time") & (df_all.aspect == "ALL")]["n"].sum()
with st.sidebar:
    _start = st.query_params.get("page")  # deep link: ?page=Topics
    page = st.radio(
        "Navigate",
        list(PAGES),
        format_func=lambda k: f"{PAGES[k]} {k}",
        index=list(PAGES).index(_start) if _start in PAGES else 0,
        label_visibility="collapsed",
        key="nav",
    )
    if (
        st.query_params.get("page") != page
    ):  # keep the address in step, so a refresh stays on this page
        st.query_params["page"] = page
    st.markdown('<div class="side-label">Data snapshot</div>', unsafe_allow_html=True)
    for label, value in (
        ("Sentences scored", f"{int(_total):,}"),
        ("Data as of", data_as_of),
        ("Index computed", computed_at),
    ):
        st.markdown(
            f'<div class="side-stat"><span>{label}</span><span>{html.escape(str(value))}</span></div>',
            unsafe_allow_html=True,
        )
    st.caption(
        "Sentiment is an indicator, not a recommendation. "
        "Check how many sentences sit behind a number."
    )


def page_header(title: str, sub: str):
    st.markdown(
        f'<p class="hello">{title}</p><p class="sub">{sub}</p>', unsafe_allow_html=True
    )
    if page in ("Overview", "Topics"):
        st.caption(
            f"Period: All available data · Data through {data_as_of} · "
            "Scores: −1 negative / 0 neutral / +1 positive"
        )


# sentiment_index carries 3 rows per (bank, aspect), one per window
# ('7d', '30d', 'all_time'). Overview and Topics use the
# all-time snapshot; Trends is the one view that shows all three.
df = df_all[df_all.window == "all_time"]
MIN_TOPIC_N = 30  # a topic score on fewer sentences than this is not worth a headline
TOPIC_DESCRIPTIONS = {
    "asset_quality": "Loan quality, credit losses, provisioning and non-performing loans.",
    "capital_liquidity": "Capital strength, funding and the bank's ability to meet its obligations.",
    "dividend_policy": "Dividends, payout ratios and capital returned to shareholders.",
    "net_interest_margin": "Lending margins, net interest income and loan/deposit growth.",
    "management_guidance": "Management's outlook, targets and forward-looking statements.",
    "income_profit_results": "Revenue, profits and reported financial results.",
    "wealth_business": "Wealth management, private banking and related fee income.",
    "investor_stock_sentiment": "Investor discussion about the banks' shares and valuations.",
    "retail_banking_sentiment": "Customer experiences with banking products and services.",
    "macro_market_environment": "Interest rates, economic conditions and the wider market outlook.",
}


def open_topic_evidence(bank: str, aspect: str):
    """A callback runs before the sidebar widgets are recreated on the next run."""
    st.session_state.nav = "Evidence"
    st.session_state.evidence_bank = bank
    st.session_state.evidence_aspect = aspect


def card(title: str, hint: str = ""):
    """A bordered container with a heading and a one-line 'what am I looking at'."""
    box = st.container(border=True)
    box.markdown(f"#### {title}")
    if hint:
        box.caption(hint)
    return box


def overall(bank: str):
    row = df[(df.bank == bank) & (df.aspect == "ALL")]
    return None if row.empty or row.iloc[0]["insufficient_data"] else row.iloc[0]


# ---------------------------------------------------------------- Overview
if page == "Overview":
    page_header(
        "Singapore bank sentiment",
        "Compare DBS, OCBC and UOB, explore the topics behind their scores, "
        "and read the supporting evidence.",
    )

    scored = {b: overall(b) for b in BANKS}
    live = {b: r for b, r in scored.items() if r is not None}
    if live:
        top = max(live, key=lambda b: live[b]["score"])
        low = min(live, key=lambda b: live[b]["score"])
        gap = float(live[top]["score"] - live[low]["score"])
        if len(live) < 2:
            msg = f"Only {top} has data so far."
        elif gap < 0.05:
            msg = (
                f"The banks have similar scores. <b>{top}</b> is highest at {live[top]['score']:+.3f} "
                f"and <b>{low}</b> lowest at {live[low]['score']:+.3f}. "
                "The small gap should be read alongside source coverage and sample sizes."
            )
        else:
            msg = (
                f"<b>{top}</b> is the most positively covered at {live[top]['score']:+.3f}, "
                f"<b>{low}</b> the least at {live[low]['score']:+.3f}."
            )
        st.markdown(
            takeaway("Key finding · all available data", msg), unsafe_allow_html=True
        )

    cols = st.columns(3)
    for col, bank in zip(cols, BANKS):
        r = scored[bank]
        with col:
            if r is None:
                st.markdown(
                    bank_card(bank, None, 0, None, [], palette=palette),
                    unsafe_allow_html=True,
                )
                continue
            try:
                spark = load_time_series(bank, "ALL", "month")
                spark = spark["score"].where(spark["sufficient"]).tail(12).tolist()
            except ApiError as exc:
                st.warning(f"{bank} history unavailable: {exc}")
                spark = []
            recent = df_all[
                (df_all.bank == bank)
                & (df_all.aspect == "ALL")
                & (df_all.window == "30d")
            ]
            delta = (
                float(recent.iloc[0]["score"]) - float(r["score"])
                if not recent.empty and not recent.iloc[0]["insufficient_data"]
                else None
            )
            st.markdown(
                bank_card(
                    bank, float(r["score"]), int(r["n"]), delta, spark, palette=palette
                ),
                unsafe_allow_html=True,
            )

    st.caption(
        "Coverage includes news, social discussion, bank earnings and broker research. "
        "Source mix and sentence counts differ between banks."
    )
    st.write("")
    left, right = st.columns([1, 1])
    with left:
        box = card(
            "Positive, neutral or negative?",
            "Share of each bank's sentences that were positive, neutral or negative.",
        )
        mix_rows = []
        for b, r in live.items():
            run = 0.0
            for i, (lab, k) in enumerate(
                (("Positive", "pos_n"), ("Neutral", "neu_n"), ("Negative", "neg_n"))
            ):
                share = int(r[k]) / max(int(r["n"]), 1)
                mix_rows.append(
                    {
                        "bank": b,
                        "label": lab,
                        "count": int(r[k]),
                        "order": i,
                        "share": share,
                        "mid": run + share / 2,
                        "pct": f"{share:.0%}" if share >= 0.06 else "",
                    }
                )
                run += share
        mix = pd.DataFrame(mix_rows)
        if not mix.empty:
            box.altair_chart(
                mix_chart(mix, palette=palette), use_container_width=True, theme=None
            )
            neutral_share = mix[mix.label == "Neutral"]["count"].sum() / max(
                mix["count"].sum(), 1
            )
            box.caption(
                f"Neutral sentences make up {neutral_share:.0%} of the collected text. "
                "These are raw sentence shares; the index also applies confidence and source weights."
            )
    with right:
        box = card(
            "How sentiment changed",
            "Quarterly sentiment. Gaps indicate missing data or too few sentences that quarter.",
        )
        frames = []
        for b in live:
            try:
                s = load_time_series(b, "ALL", "quarter")
                s = s.assign(bank=b)
                if not s.empty:
                    frames.append(s[["period", "bank", "score", "n", "sufficient"]])
            except ApiError as exc:
                box.warning(f"{b} history unavailable: {exc}")
        if frames and any(f["sufficient"].any() for f in frames):
            trend_df = pd.concat(frames)
            box.altair_chart(
                trend_chart(trend_df, palette=palette),
                use_container_width=True,
                theme=None,
            )
        else:
            box.info("Not enough history to draw a trend yet.")

    st.write("")
    box = st.expander("Source breakdown · check what is behind the comparison")
    box.caption(
        "Scores split by source. Bank earnings reflect management's own framing, "
        "while news and social discussion provide other perspectives. Different source "
        "mixes can affect the overall bank comparison. Hover a bar for its sentence count."
    )
    try:
        breakdown_df = load_source_breakdown()
    except ApiError as exc:
        box.error(str(exc))
        st.stop()
    if breakdown_df.empty:
        box.info("No per-source sentiment results are available.")
    else:
        box.altair_chart(
            source_chart(breakdown_df, palette=palette),
            use_container_width=True,
            theme=None,
        )
        with box.expander("See the numbers"):
            pivot_src = breakdown_df.pivot(
                index="source", columns="bank", values="score"
            )
            pivot_src_n = breakdown_df.pivot(index="source", columns="bank", values="n")
            st.dataframe(heatmap_table(pivot_src), use_container_width=True)
            if not HAS_MATPLOTLIB:
                st.caption("Colour scale unavailable: matplotlib is not installed.")
            st.caption("Sentence count behind each cell:")
            st.dataframe(pivot_src_n.fillna(0).astype(int), use_container_width=True)

    st.write("")
    box = st.expander("Analyst context · separate from sentiment scores")
    box.caption(
        "Yahoo Finance consensus: analyst ratings and average price targets. "
        "These are external opinions, separate from our sentiment model. "
        "Prices and targets are from the dated snapshots shown below."
    )
    try:
        consensus_df = load_analyst_consensus()
    except ApiError as exc:
        box.error(str(exc))
        st.stop()
    if consensus_df.empty:
        box.info("No analyst consensus data is available.")
    else:
        acols = box.columns(3)
        for acol, bank in zip(acols, BANKS):
            brow = consensus_df[consensus_df.bank == bank]
            with acol:
                if brow.empty:
                    st.metric(f"{bank} consensus", "No data")
                    continue
                b = brow.iloc[0]
                upside = None
                if pd.notna(b["target_mean"]) and b["current_price"]:
                    upside = (
                        100
                        * (b["target_mean"] - b["current_price"])
                        / b["current_price"]
                    )
                st.metric(
                    f"{bank}: {str(b['recommendation_key'] or 'n/a').replace('_', ' ')}",
                    (
                        f"S${b['target_mean']:.2f}"
                        if pd.notna(b["target_mean"])
                        else "n/a"
                    ),
                    delta=(
                        f"{upside:+.1f}% vs snapshot price"
                        if upside is not None
                        else None
                    ),
                )
                st.caption(
                    f"{int(b['n_analysts'])} analysts, as of {b['as_of_date']}"
                    if pd.notna(b["n_analysts"])
                    else f"as of {b['as_of_date']}"
                )
    disclosure_footer()

# ------------------------------------------------------------------ Topics
elif page == "Topics":
    page_header(
        "Compare sentiment by topic",
        "Choose a topic, compare the banks, then read the sentences behind each score.",
    )
    aspect_df = df[df.aspect != "ALL"].copy()
    aspect_df.loc[aspect_df["insufficient_data"].eq(True), "score"] = float("nan")
    topics = sorted(
        aspect_df.loc[aspect_df.aspect != "other", "aspect"].unique().tolist(),
        key=pretty,
    )
    if not topics:
        st.info("No topic-level data yet.")
    else:
        remembered = st.query_params.get("topic", "dividend_policy")
        selected_topic = st.selectbox(
            "Topic to compare",
            topics,
            index=topics.index(remembered) if remembered in topics else 0,
            format_func=pretty,
            key="topics_aspect",
        )
        if st.query_params.get("topic") != selected_topic:
            st.query_params["topic"] = selected_topic
        st.caption(
            TOPIC_DESCRIPTIONS.get(
                selected_topic, "Sentiment in the collected text on this topic."
            )
        )

        focus = aspect_df[aspect_df.aspect == selected_topic]
        comparable = focus[(focus.n >= MIN_TOPIC_N) & focus.score.notna()]
        if len(comparable) >= 2:
            hi = comparable.loc[comparable.score.idxmax()]
            lo = comparable.loc[comparable.score.idxmin()]
            if hi.score - lo.score < 0.01:
                finding = (
                    f"The banks with enough coverage have similar scores for "
                    f"<b>{html.escape(pretty(selected_topic).lower())}</b> "
                    f"({lo.score:+.3f} to {hi.score:+.3f})."
                )
            else:
                scope = (
                    "Among banks with enough coverage, "
                    if len(comparable) < len(BANKS)
                    else ""
                )
                finding = (
                    f"{scope}<b>{html.escape(pretty(selected_topic))}</b>: "
                    f"<b>{hi.bank}</b> has the highest sentiment score ({hi.score:+.3f}) "
                    f"and <b>{lo.bank}</b> the lowest ({lo.score:+.3f}). "
                    "Lowest is a relative comparison; it does not necessarily mean negative sentiment."
                )
            st.markdown(
                takeaway("Selected topic · bank comparison", finding),
                unsafe_allow_html=True,
            )
        else:
            st.info(
                f"Fewer than two banks have at least {MIN_TOPIC_N} sentences on this topic. "
                "There is not enough coverage for a headline comparison."
            )

        for col, bank in zip(st.columns(3), BANKS):
            row = focus[focus.bank == bank]
            r = None if row.empty else row.iloc[0]
            n = 0 if r is None else int(r["n"])
            score = None if r is None or pd.isna(r["score"]) else float(r["score"])
            with col:
                st.markdown(
                    bank_card(bank, score, n, None, [], palette=palette),
                    unsafe_allow_html=True,
                )
                if 0 < n < MIN_TOPIC_N:
                    st.caption(f"Small sample: fewer than {MIN_TOPIC_N} sentences.")
                st.button(
                    f"View {bank} evidence",
                    key=f"topic_evidence_{bank}",
                    on_click=open_topic_evidence,
                    args=(bank, selected_topic),
                    disabled=n == 0,
                    use_container_width=True,
                )
        st.caption(
            f"Headline comparisons require at least {MIN_TOPIC_N} sentences per bank. "
            "Sentence counts and source mix differ; a higher score is not a stock recommendation."
        )

        st.write("")
        with st.expander("Compare all topics"):
            st.caption(
                "Green is positive, red is negative. Each cell shows its score and sentence count. "
                f"Faded cells have fewer than {MIN_TOPIC_N} sentences; a dash means no reliable score."
            )
            include_other = st.checkbox(
                "Include uncategorised text", key="topics_include_other"
            )
            matrix = (
                aspect_df if include_other else aspect_df[aspect_df.aspect != "other"]
            )
            st.altair_chart(
                heatmap_chart(matrix, palette=palette),
                use_container_width=True,
                theme=None,
            )
            if include_other:
                st.caption(
                    "Uncategorised text did not match an investment topic; it is not a separate investment finding."
                )

        with st.expander("Highest and lowest topic scores within each bank"):
            st.caption(
                f"Relative sentiment rankings, using topics with at least {MIN_TOPIC_N} sentences. These are not ratings of financial performance."
            )
            solid = aspect_df[
                (aspect_df.n >= MIN_TOPIC_N)
                & (aspect_df.aspect != "other")
                & aspect_df.score.notna()
            ]
            for col, bank in zip(st.columns(3), BANKS):
                sub = solid[solid.bank == bank].sort_values("score")
                k = min(2, len(sub) // 2)
                best = (
                    [
                        (r.aspect, float(r.score))
                        for r in sub.tail(k).iloc[::-1].itertuples()
                    ]
                    if k
                    else []
                )
                worst = (
                    [(r.aspect, float(r.score)) for r in sub.head(k).itertuples()]
                    if k
                    else []
                )
                with col:
                    st.markdown(
                        strengths_card(bank, best, worst, palette=palette),
                        unsafe_allow_html=True,
                    )

        with st.expander("Scores and sample sizes"):
            pivot_score = aspect_df.pivot(
                index="aspect", columns="bank", values="score"
            ).rename(index=pretty)
            pivot_n = aspect_df.pivot(
                index="aspect", columns="bank", values="n"
            ).rename(index=pretty)
            st.dataframe(heatmap_table(pivot_score), use_container_width=True)
            if not HAS_MATPLOTLIB:
                st.caption("Colour scale unavailable: matplotlib is not installed.")
            st.caption("Scored sentences per topic and bank:")
            st.dataframe(pivot_n.fillna(0).astype(int), use_container_width=True)
    disclosure_footer()

# ------------------------------------------------------------------ Trends
elif page == "Trends":
    page_header(
        "How has sentiment moved?",
        "Pick a bank and a topic. The line uses the same weighting as the headline numbers, "
        "and a gap means there was too little data that period, not neutral sentiment.",
    )
    c1, c2, c3 = st.columns([1, 1, 1.2])
    with c1:
        ts_bank = st.selectbox("Bank", BANKS, key="ts_bank")
    with c2:
        ts_aspects = ["ALL"] + sorted(
            df_all[df_all.aspect != "ALL"]["aspect"].unique().tolist()
        )
        ts_aspect = st.selectbox(
            "Topic",
            ts_aspects,
            key="ts_aspect",
            format_func=lambda a: "Overall" if a == "ALL" else pretty(a),
        )
    with c3:
        bucket = st.radio(
            "Group by",
            ["month", "quarter", "week"],
            index=1,
            horizontal=True,
            key="ts_bucket",
        )

    window_df = df_all[(df_all.bank == ts_bank) & (df_all.aspect == ts_aspect)]
    window_order = {"7d": 0, "30d": 1, "all_time": 2}
    window_names = {"7d": "Last 7 days", "30d": "Last 30 days", "all_time": "All time"}
    st.caption(f"Recent windows end on {data_as_of}, the newest stored data date.")
    window_df = window_df.assign(_order=window_df.window.map(window_order)).sort_values(
        "_order"
    )

    if window_df.empty:
        st.info("No data for this bank and topic.")
    else:
        for col, (_, r) in zip(st.columns(3), window_df.iterrows()):
            with col:
                name = window_names.get(r["window"], r["window"])
                if r["n"] == 0:
                    st.metric(name, "No data")
                elif r["insufficient_data"]:
                    st.metric(name, "Too little data")
                    st.caption(f"Only {int(r['n'])} sentences")
                else:
                    st.metric(
                        name, f"{r['score']:+.3f}", help=f"{int(r['n'])} sentences"
                    )
                    st.caption(
                        f"{score_word(float(r['score']))}, from {int(r['n']):,} sentences"
                    )

    try:
        series = load_time_series(ts_bank, ts_aspect, bucket)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()
    st.write("")
    box = card(
        f"{ts_bank}: {'overall' if ts_aspect == 'ALL' else pretty(ts_aspect).lower()} sentiment over time"
    )
    if series.empty:
        box.info("Not enough data to plot a series for this selection.")
    else:
        if not series["sufficient"].any():
            box.info("Every period in this selection is below the volume floor.")
        else:
            box.altair_chart(
                area_chart(
                    series,
                    color=palette.bank_colors.get(ts_bank, palette.accent),
                    palette=palette,
                ),
                use_container_width=True,
                theme=None,
            )
            thin = int((~series.sufficient).sum())
            if thin:
                box.caption(
                    f"{thin} period(s) with missing or insufficient data appear as gaps."
                )
            with box.expander("See the numbers"):
                st.dataframe(
                    series.assign(score=series["score"].where(series["sufficient"]))[
                        [
                            "period",
                            "score",
                            "n",
                            "pos_n",
                            "neu_n",
                            "neg_n",
                            "sufficient",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
    disclosure_footer()

# ---------------------------------------------------------------- Evidence
elif page == "Evidence":
    page_header(
        "What do the sentences actually say?",
        "The most recent sentences behind a score, so you can judge the numbers for yourself.",
    )
    c1, c2 = st.columns(2)
    with c1:
        sel_bank = st.selectbox("Bank", BANKS, key="evidence_bank")
    with c2:
        aspects_available = ["ALL"] + sorted(
            df[df.aspect != "ALL"]["aspect"].unique().tolist()
        )
        sel_aspect = st.selectbox(
            "Topic",
            aspects_available,
            format_func=lambda a: "Overall" if a == "ALL" else pretty(a),
            key="evidence_aspect",
        )

    try:
        evidence = load_evidence(sel_bank, sel_aspect)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()
    if evidence.empty:
        st.info("No evidence sentences for this selection.")
    else:
        has_label = "label" in evidence.columns
        for _, row in evidence.iterrows():
            st.markdown(
                quote_card(
                    row["text"],
                    row["source"],
                    row["published_at"],
                    row["url"],
                    row["label"] if has_label else None,
                    row["confidence"] if has_label else None,
                ),
                unsafe_allow_html=True,
            )
    disclosure_footer()

# --------------------------------------------------------------------- Ask
elif page == "Ask":
    page_header(
        "Ask about the data",
        "Answers come from the sentiment index in this dashboard, not from the model's own "
        "knowledge. It does not give investment advice.",
    )

    st.caption(
        "A local model may still cite evidence it never retrieved. Answers flagged with a "
        "verification warning should not be trusted, and figures that match nothing the tools "
        "returned are flagged too. It remembers the last few turns, so follow-ups like "
        '"and OCBC?" work.'
    )

    # API history contains messages and display metadata, not backend objects.
    # Use a separate key from the old in-process Conversation implementation.
    if "api_chat_history" not in st.session_state:
        st.session_state.api_chat_history = []
    history = st.session_state.api_chat_history

    if st.button("Clear conversation", key="clear_chat"):
        st.session_state.api_chat_history = []
        history = st.session_state.api_chat_history

    for message in history:
        render_chat_message(message)

    # Suggestions are generated from what the index actually holds, so a
    # clicked suggestion won't dead-end on "insufficient data".
    pending = None
    st.markdown("**Try one of these**")
    try:
        suggestions = load_suggestions()
    except ApiError as exc:
        st.warning(f"Suggested questions are unavailable. {exc}")
        suggestions = []
    for row_start in range(0, len(suggestions), 2):
        for col, item in zip(st.columns(2), suggestions[row_start : row_start + 2]):
            if col.button(
                item["question"],
                key=f"sugg-{row_start}-{item['question']}",
                use_container_width=True,
            ):
                pending = item["question"]

    typed = st.chat_input("Or ask your own question")
    question = pending or typed

    if question and question.strip():
        with st.chat_message("user"):
            st.markdown(question)
        with st.spinner("Thinking - a local model can take a minute..."):
            try:
                result = send_chat(question, history)
            except ApiError as exc:
                st.error(f"Could not get an answer. {exc}")
            else:
                answer = {
                    "role": "assistant",
                    "content": result["answer"],
                    "guard": result.get("guard"),
                    "citation_unverified": result["citation_unverified"],
                    "unverified_numbers": result["unverified_numbers"],
                }
                history.extend([{"role": "user", "content": question}, answer])
                render_chat_message(answer)

    disclosure_footer()
