"""
Streamlit dashboard — see docs/DESIGN.md.

Six pages in a side navigation: overview, topics, trends, evidence, chat and
data management. Every data view carries the disclosures the design calls for — sample size
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
from dashboard.chat import send_chat
from dashboard import ask as ask_view, data, trends, evidence as evidence_view
from dashboard import manage as manage_view
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
    bank_card,
    comparison_chart,
    heatmap_chart,
    mix_chart,
    pretty,
    section_heading,
    sentiment_cmap,
    source_chart,
    strengths_card,
    takeaway,
    trend_chart,
)


def open_overview():
    """Navigate within this session, preserving the conversation and theme."""
    st.session_state.nav = "Overview"


with st.sidebar:
    with st.container(key="sidebar_layout"):
        with st.container(key="sidebar_brand"):
            st.button(
                "BankPulse",
                key="brand_home",
                on_click=open_overview,
                use_container_width=True,
            )
            st.markdown(
                '<div class="brand-sub">SINGAPORE BANK SENTIMENT</div>',
                unsafe_allow_html=True,
            )
        # Reserve the visual order here so the theme is available before loading
        # data; the navigation and snapshot are filled once their data is ready.
        sidebar_navigation = st.container(key="sidebar_navigation")
        sidebar_snapshot = st.container(key="sidebar_snapshot")
        with st.container(key="sidebar_utilities"):
            sidebar_help = st.container(key="sidebar_help")
            with st.container(key="sidebar_settings"):
                dark_mode = st.toggle(
                    "Dark mode",
                    value=st.query_params.get("theme") == "dark",
                    key="dark_mode",
                    help="Switch between light and dark themes.",
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
def load_trend(bank: str, aspect: str) -> dict:
    return data.load_trend(bank, aspect)


@st.cache_data(ttl=300)
def load_analyst_consensus() -> pd.DataFrame:
    return data.load_analyst_consensus()


@st.cache_data(ttl=300)
def load_suggestions() -> list[dict]:
    return data.load_suggestions(limit=6)


def refresh_pipeline_data():
    """Invalidate API-derived views without clearing chat history or user choices."""
    for loader in (
        load_index,
        load_evidence,
        load_source_breakdown,
        load_time_series,
        load_trend,
        load_analyst_consensus,
        load_suggestions,
    ):
        loader.clear()


def disclosure_footer():
    with st.container(key="disclosure"):
        st.caption(
            f"Not financial advice. Data as of: {data_as_of}. Index computed: {computed_at}."
        )


def score_guidance():
    """Shared score explanations in the sidebar on every page."""
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


manage_view.sync_history(refresh_pipeline_data)
index_error = None
try:
    df_all = load_index()
except ApiError as exc:
    index_error = str(exc)
    df_all = pd.DataFrame(columns=data.INDEX_COLUMNS + ["window", "data_as_of"])

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
    "Data Management": ":material/database:",
}
_total = df_all[(df_all.window == "all_time") & (df_all.aspect == "ALL")]["n"].sum()
with sidebar_navigation:
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
with sidebar_snapshot:
    text_date = pd.to_datetime(data_as_of, errors="coerce")
    snapshot_rows = "".join(
        f'<div class="side-stat"><span>{label}</span><span>{html.escape(str(value))}</span></div>'
        for label, value in (
            ("Sentences", f"{int(_total):,}" if index_error is None else "Unknown"),
            (
                "Text through",
                text_date.strftime("%d %b %Y") if pd.notna(text_date) else "Unknown",
            ),
            (
                "Scores computed",
                (
                    timestamps.max().strftime("%d %b %Y")
                    if not timestamps.empty
                    else "Unknown"
                ),
            ),
        )
    )
    st.markdown(
        '<div class="side-label">Data snapshot</div>' + snapshot_rows,
        unsafe_allow_html=True,
    )
    with st.expander("Snapshot details"):
        st.caption(
            f"Data as of: {data_as_of}. Index computed: {computed_at}. "
            "Text through is the newest stored sentence date. Scores computed is "
            "when the index was calculated; it does not indicate new text was collected."
        )
    st.markdown(
        '<p class="side-note">Sentiment is an indicator, not investment advice.</p>',
        unsafe_allow_html=True,
    )

with sidebar_help:
    st.markdown('<div class="side-label">Help</div>', unsafe_allow_html=True)
    with st.expander("How BankPulse works"):
        if page == "Ask":
            ask_view.render_answer_guidance()
        if page == "Data Management":
            manage_view.render_guidance()
        score_guidance()


def page_header(title: str, sub: str):
    labels = {
        "Overview": "Market overview",
        "Topics": "Topic explorer",
        "Trends": "Sentiment history",
        "Evidence": "Evidence library",
        "Ask": "Research assistant",
        "Data Management": "Data operations",
    }
    snapshot = pd.to_datetime(data_as_of, errors="coerce")
    date_label = snapshot.strftime("%d %b %Y") if pd.notna(snapshot) else data_as_of
    meta = (
        '<div class="report-meta"><span>All available data</span>'
        "<span>−1 negative &nbsp; / &nbsp; 0 neutral &nbsp; / &nbsp; +1 positive</span></div>"
        if page in ("Overview", "Topics")
        else ""
    )
    st.markdown(
        '<div class="page-heading"><div class="heading-top">'
        f'<span class="eyebrow">{labels[page]}</span>'
        f'<span class="snapshot-badge">Data through {html.escape(date_label)}</span></div>'
        f'<p class="hello">{html.escape(title)}</p><p class="sub">{html.escape(sub)}</p>{meta}</div>',
        unsafe_allow_html=True,
    )


if page != "Data Management":
    manage_view.render_update_notice(refresh_pipeline_data)
    if index_error is not None:
        st.error(index_error)
        st.stop()
    if df_all.empty:
        st.warning(
            "No sentiment results are available for the selected model. "
            "Check that the API is using the project's matching database snapshot, "
            "or open Data Management to inspect manual updates."
        )
        st.stop()


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
    evidence_view.reset_filters()


def open_topic_trends(bank: str, aspect: str):
    st.session_state.nav = "Trends"
    st.session_state.ts_bank = bank
    st.session_state.ts_aspect = aspect


def card(title: str, hint: str = ""):
    """A bordered container with a heading and a one-line 'what am I looking at'."""
    box = st.container(border=True, key=f"panel_{title.replace(' ', '_')}")
    box.markdown(section_heading(title), unsafe_allow_html=True)
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
        "A view of the conversation around DBS, OCBC and UOB. "
        "Compare sentiment, follow its movement and explore the source text.",
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
                "Read the gap alongside source coverage and sample sizes."
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
    left, right = st.columns([1, 1])
    with left:
        box = card(
            "The conversation mix",
            "Positive, neutral and negative sentences · raw label shares",
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
                mix_chart(mix, height=230, palette=palette),
                use_container_width=True,
                theme=None,
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
            "Quarterly index · gaps mean missing or insufficient coverage",
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
                trend_chart(trend_df, height=230, palette=palette),
                use_container_width=True,
                theme=None,
            )
        else:
            box.info("Not enough history to draw a trend yet.")
        box.caption(
            "The index weights confidence and source. Zero represents neutral sentiment."
        )

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
        with st.container(border=True, key="topic_controls"):
            chooser, description = st.columns([1, 1.6], vertical_alignment="center")
            selected_topic = chooser.selectbox(
                "Topic to compare",
                topics,
                index=topics.index(remembered) if remembered in topics else 0,
                format_func=pretty,
                key="topics_aspect",
            )
            description.markdown(
                '<div class="control-description">'
                f"<strong>{html.escape(pretty(selected_topic))}</strong><p>"
                + html.escape(
                    TOPIC_DESCRIPTIONS.get(
                        selected_topic, "Sentiment in the collected text on this topic."
                    )
                )
                + "</p></div>",
                unsafe_allow_html=True,
            )
        if st.query_params.get("topic") != selected_topic:
            st.query_params["topic"] = selected_topic

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
                    "The ranking describes sentiment in the collected text."
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

        visual, bank_details = st.columns([1.35, 1], gap="medium")
        with visual:
            with card(
                "Bank comparison", "One topic. Three banks. The same −1 to +1 scale."
            ):
                st.altair_chart(
                    comparison_chart(focus, palette=palette),
                    use_container_width=True,
                    theme=None,
                )
                st.markdown(
                    '<div class="reading-note"><b>Read the score with its coverage.</b> '
                    f"Headline comparisons require {MIN_TOPIC_N}+ sentences per bank. "
                    "Higher sentiment does not imply a better investment; source mix differs between banks.</div>",
                    unsafe_allow_html=True,
                )
        with bank_details:
            for bank in BANKS:
                row = focus[focus.bank == bank]
                r = None if row.empty else row.iloc[0]
                n = 0 if r is None else int(r["n"])
                score = None if r is None or pd.isna(r["score"]) else float(r["score"])
                with st.container(border=True, key=f"topic_card_{bank}"):
                    st.markdown(
                        bank_card(
                            bank, score, n, None, [], palette=palette, compact=True
                        ),
                        unsafe_allow_html=True,
                    )
                    if 0 < n < MIN_TOPIC_N:
                        st.caption(f"Small sample: fewer than {MIN_TOPIC_N} sentences.")
                    trend_col, evidence_col = st.columns(2)
                    trend_col.button(
                        f"View {bank} trend",
                        key=f"topic_trend_{bank}",
                        on_click=open_topic_trends,
                        args=(bank, selected_topic),
                        disabled=n == 0,
                        use_container_width=True,
                    )
                    evidence_col.button(
                        f"View {bank} evidence",
                        key=f"topic_evidence_{bank}",
                        on_click=open_topic_evidence,
                        args=(bank, selected_topic),
                        disabled=n == 0,
                        use_container_width=True,
                    )

        matrix_tab, rankings_tab, numbers_tab = st.tabs(
            ["Compare all topics", "Within each bank", "Scores & coverage"]
        )
        with matrix_tab:
            st.markdown(
                section_heading("The full topic picture", "Score + sentence count"),
                unsafe_allow_html=True,
            )
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

        with rankings_tab:
            st.markdown(
                section_heading("Highest and lowest topic scores"),
                unsafe_allow_html=True,
            )
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

        with numbers_tab:
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
        "Track sentiment over time",
        "See recent movement, inspect the history and check how much text supports each period.",
    )
    trends.render(
        df_all, data_as_of, palette, load_time_series, load_trend, open_topic_evidence
    )
    disclosure_footer()

# ---------------------------------------------------------------- Evidence
elif page == "Evidence":
    page_header(
        "Supporting evidence",
        "Read recent sentences and open their original sources to assess the model's predictions.",
    )
    evidence_view.render(df_all, load_evidence)
    disclosure_footer()

# --------------------------------------------------------------------- Ask
elif page == "Ask":
    chat_area = st.container(key="ask_view")
    with chat_area:
        page_header(
            "Ask BankPulse",
            "Explore bank sentiment, compare topics and find supporting evidence through conversation.",
        )
    ask_view.render(chat_area, load_suggestions, send_chat)

# --------------------------------------------------------- Data Management
elif page == "Data Management":
    page_header(
        "Manage data updates",
        "Update from local files or online sources, follow analysis progress and review previous runs.",
    )
    if index_error is not None:
        st.warning(f"The sentiment snapshot is unavailable: {index_error}")
    manage_view.render(refresh_pipeline_data)
