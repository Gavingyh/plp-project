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
            cmap=sentiment_cmap(), vmin=-1, vmax=1
        ).format("{:.3f}")
    return frame.round(3)


st.set_page_config(
    page_title="SG Bank Sentiment Dashboard",
    page_icon=":material/monitoring:",
    layout="wide",
)

from dashboard.style import (  # noqa: E402
    ACCENT,
    BANK_COLORS,
    CSS,
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

st.markdown(CSS, unsafe_allow_html=True)


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
        f"Not financial advice - sentiment is an indicator, not a recommendation. "
        f"Data as of: {data_as_of}. Index computed: {computed_at}. "
        f"Sentiment model: {model_version}. "
        "Sentiment comes from the selected fine-tuned FinBERT ensemble. A local LLM "
        "assigns each sentence one topic. Source coverage differs between banks, "
        "and earnings releases reflect management's own framing. Yahoo analyst "
        "consensus is shown separately from sentiment. Very small samples show no score."
    )


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
    st.markdown(
        '<div class="brand">BankPulse</div>'
        '<div class="brand-sub">Singapore bank sentiment</div>',
        unsafe_allow_html=True,
    )
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


# sentiment_index carries 3 rows per (bank, aspect), one per window
# ('7d', '30d', 'all_time'). Overview and Topics use the
# all-time snapshot; Trends is the one view that shows all three.
df = df_all[df_all.window == "all_time"]
MIN_TOPIC_N = 30  # a topic score on fewer sentences than this is not worth a headline


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
        "How are Singapore's banks being talked about?",
        "Sentiment about DBS, OCBC and UOB runs from -1 (negative) to +1 (positive). "
        "The index weights sentence labels by confidence and source, and shrinks small "
        "samples toward neutral.",
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
                f"The covered banks have similar scores. <b>{top}</b> is highest at {live[top]['score']:+.3f} and "
                f"<b>{low}</b> lowest at {live[low]['score']:+.3f}. Read the sample sizes and "
                "source breakdown before drawing conclusions from this gap."
            )
        else:
            msg = (
                f"<b>{top}</b> is the most positively covered at {live[top]['score']:+.3f}, "
                f"<b>{low}</b> the least at {live[low]['score']:+.3f}."
            )
        st.markdown(takeaway("The short version", msg), unsafe_allow_html=True)

    cols = st.columns(3)
    for col, bank in zip(cols, BANKS):
        r = scored[bank]
        with col:
            if r is None:
                st.markdown(bank_card(bank, None, 0, None, []), unsafe_allow_html=True)
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
                bank_card(bank, float(r["score"]), int(r["n"]), delta, spark),
                unsafe_allow_html=True,
            )

    st.write("")
    left, right = st.columns([1, 1])
    with left:
        box = card(
            "What the sentences say",
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
            box.altair_chart(mix_chart(mix), use_container_width=True, theme=None)
            neutral_share = mix[mix.label == "Neutral"]["count"].sum() / max(
                mix["count"].sum(), 1
            )
            box.caption(
                f"Most sentences are neutral ({neutral_share:.0%}). That is normal for "
                "news and filings, and it is why the scores sit close to zero."
            )
    with right:
        box = card(
            "Are they getting better or worse?",
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
                trend_chart(trend_df), use_container_width=True, theme=None
            )
        else:
            box.info("Not enough history to draw a trend yet.")

    st.write("")
    box = card(
        "Why the banks differ: where the data comes from",
        "Same scores split by source. Earnings material is management describing its own "
        "results, so it reads far more positive than retail chatter, and DBS supplies about six "
        "times as much of it as the others. A gap between banks can come from that mix and not "
        "from real sentiment.",
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
            source_chart(breakdown_df), use_container_width=True, theme=None
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
    box = card(
        "What professional analysts say",
        "Yahoo Finance consensus: how many analysts cover each bank and their average price "
        "target. This is not the content of any analyst report and is separate from the "
        "sentiment scores above.",
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
                        f"{upside:+.1f}% vs current price"
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
        "What are people talking about?",
        "The same sentiment, split by topic such as dividends or asset quality. "
        "Each sentence is assigned one topic by the aspect classifier.",
    )
    aspect_df = df[df.aspect != "ALL"].copy()
    aspect_df.loc[aspect_df["insufficient_data"].eq(True), "score"] = float("nan")
    if aspect_df.empty:
        st.info("No topic-level data yet.")
    else:
        # "other" is the residual bucket for sentences matching no topic, so it is not a finding.
        solid = aspect_df[(aspect_df.n >= MIN_TOPIC_N) & (aspect_df.aspect != "other")]
        best_worst = {}
        for bank in BANKS:
            sub = solid[solid.bank == bank].sort_values("score")
            if len(sub) >= 2:
                k = min(2, len(sub) // 2)
                best_worst[bank] = (
                    [
                        (r.aspect, float(r.score))
                        for r in sub.tail(k).iloc[::-1].itertuples()
                    ],
                    [(r.aspect, float(r.score)) for r in sub.head(k).itertuples()],
                )
            else:
                best_worst[bank] = ([], [])

        if not solid.empty:
            hi = solid.loc[solid.score.idxmax()]
            lo = solid.loc[solid.score.idxmin()]
            st.markdown(
                takeaway(
                    "The short version",
                    f"The warmest topic is <b>{pretty(hi.aspect).lower()}</b> at <b>{hi.bank}</b> "
                    f"({hi.score:+.2f}). The coolest is <b>{pretty(lo.aspect).lower()}</b> at "
                    f"<b>{lo.bank}</b> ({lo.score:+.2f}). Faded cells below have fewer than "
                    f"{MIN_TOPIC_N} sentences and should not be over-read.",
                ),
                unsafe_allow_html=True,
            )

        box = card(
            "Sentiment by topic",
            "Green is positive, red is negative, grey is neutral. Hover a cell for how many "
            "sentences it rests on. 'Other' collects sentences that match no topic.",
        )
        box.altair_chart(heatmap_chart(aspect_df), use_container_width=True, theme=None)

        st.write("")
        st.markdown("#### Strengths and weak spots")
        st.caption(
            f"Each bank's best and weakest topics, using only topics with at least "
            f"{MIN_TOPIC_N} sentences."
        )
        for col, bank in zip(st.columns(3), BANKS):
            with col:
                best, worst = best_worst[bank]
                st.markdown(strengths_card(bank, best, worst), unsafe_allow_html=True)

        st.write("")
        with st.expander("See the numbers"):
            pivot_score = aspect_df.pivot(
                index="aspect", columns="bank", values="score"
            )
            pivot_n = aspect_df.pivot(index="aspect", columns="bank", values="n")
            st.dataframe(heatmap_table(pivot_score), use_container_width=True)
            if not HAS_MATPLOTLIB:
                st.caption("Colour scale unavailable: matplotlib is not installed.")
            st.caption("Sample size per cell:")
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
                area_chart(series, color=BANK_COLORS.get(ts_bank, ACCENT)),
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
        sel_bank = st.selectbox("Bank", BANKS)
    with c2:
        aspects_available = ["ALL"] + sorted(
            df[df.aspect != "ALL"]["aspect"].unique().tolist()
        )
        sel_aspect = st.selectbox(
            "Topic",
            aspects_available,
            format_func=lambda a: "Overall" if a == "ALL" else pretty(a),
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
