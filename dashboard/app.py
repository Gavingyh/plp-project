"""
Streamlit dashboard — see docs/DESIGN.md.

Five pages in a side navigation: overview, topics, trends, evidence and chat. Every view carries the disclosures the design calls for — sample size
(n), last-refresh timestamp, and a not-financial-advice notice. Those are the
trust anchors, not decoration.

USAGE:
  streamlit run dashboard/app.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import get_logger, setup_logging
from ingest.db import get_connection

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
        return frame.style.background_gradient(cmap=sentiment_cmap(), vmin=-1, vmax=1).format("{:.3f}")
    return frame.round(3)

st.set_page_config(page_title="SG Bank Sentiment Dashboard", page_icon=":material/monitoring:", layout="wide")

from dashboard.style import (  # noqa: E402
    ACCENT, BANK_COLORS, CSS, area_chart, bank_card, heatmap_chart, mix_chart, pretty,
    quote_card, score_word, sentiment_cmap, source_chart, strengths_card, takeaway,
    trend_chart)

st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_index() -> pd.DataFrame:
    conn = get_connection()
    try:
        # Only the blended rows here; per-source rows are shown separately in
        # the source-composition panel (see aggregate/index.py).
        df = pd.read_sql_query(
            "SELECT * FROM sentiment_index WHERE source = 'ALL'", conn)
    finally:
        conn.close()
    return df


@st.cache_data(ttl=300)
def load_evidence(bank: str, aspect: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        if aspect == "ALL":
            query = """SELECT s.text, s.source, s.url, s.published_at
                       FROM sentences s WHERE s.bank = ? ORDER BY s.published_at DESC LIMIT 30"""
            params = (bank,)
        else:
            query = """SELECT s.text, s.source, s.url, s.published_at, ase.label, ase.confidence
                       FROM sentences s
                       JOIN aspect_sentiment ase ON ase.sentence_id = s.sentence_id
                       WHERE s.bank = ? AND ase.aspect = ?
                       ORDER BY s.published_at DESC LIMIT 30"""
            params = (bank, aspect)
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def load_source_breakdown(window: str = "all_time") -> pd.DataFrame:
    conn = get_connection()
    try:
        return pd.read_sql_query(
            "SELECT bank, source, score, n FROM sentiment_index "
            "WHERE aspect = 'ALL' AND window = ? AND source != 'ALL' "
            "ORDER BY bank, source", conn, params=(window,))
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=300)
def load_time_series(bank: str, aspect: str, bucket: str) -> pd.DataFrame:
    from aggregate.index import compute_time_series
    return pd.DataFrame(compute_time_series(bank, None if aspect == "ALL" else aspect,
                                            bucket=bucket))


@st.cache_data(ttl=300)
def load_analyst_consensus() -> pd.DataFrame:
    conn = get_connection()
    try:
        return pd.read_sql_query(
            "SELECT bank, as_of_date, n_analysts, recommendation_key, target_mean, "
            "current_price FROM analyst_consensus WHERE as_of_date = "
            "(SELECT MAX(as_of_date) FROM analyst_consensus)", conn)
    except Exception:
        return pd.DataFrame()  # table may not exist yet on a fresh install
    finally:
        conn.close()


def disclosure_footer():
    st.caption(
        f"Not financial advice - sentiment is an indicator, not a recommendation. "
        f"Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        "See docs/STATUS.md for known limitations (Reddit skews toward DBS, "
        "news volume rises towards the present, analyst figures are Yahoo "
        "consensus aggregates rather than analyst reports, scores come from base "
        "FinBERT applied zero-shot, and aspects are matched by embedding "
        "similarity, so a sentence often counts under several aspects)."
    )


df_all = load_index()
if df_all.empty:
    st.warning("No sentiment data yet. Run the pipeline: `python run_daily_batch.py` → "
               "`python -m preprocess.pipeline` → `python -m aspects.assign` → "
               "`python -m sentiment.score` → `python -m aggregate.index`")
    st.stop()

PAGES = {
    "Overview": ":material/space_dashboard:",
    "Topics": ":material/category:",
    "Trends": ":material/show_chart:",
    "Evidence": ":material/format_quote:",
    "Ask": ":material/chat:",
}
_total = df_all[(df_all.window == "all_time") & (df_all.aspect == "ALL")]["n"].sum()
with st.sidebar:
    st.markdown('<div class="brand">BankPulse</div>'
                '<div class="brand-sub">Singapore bank sentiment</div>', unsafe_allow_html=True)
    _start = st.query_params.get("page")  # deep link: ?page=Topics
    page = st.radio("Navigate", list(PAGES), format_func=lambda k: f"{PAGES[k]} {k}",
                    index=list(PAGES).index(_start) if _start in PAGES else 0,
                    label_visibility="collapsed", key="nav")
    st.markdown('<div class="side-label">Data snapshot</div>', unsafe_allow_html=True)
    for label, value in (("Sentences scored", f"{int(_total):,}"),
                         ("Refreshed", datetime.now(timezone.utc).strftime("%d %b %H:%M UTC"))):
        st.markdown(f'<div class="side-stat"><span>{label}</span><span>{value}</span></div>',
                    unsafe_allow_html=True)
    st.caption("Sentiment is an indicator, not a recommendation. "
               "Check how many sentences sit behind a number.")


def page_header(title: str, sub: str):
    st.markdown(f'<p class="hello">{title}</p><p class="sub">{sub}</p>', unsafe_allow_html=True)


# sentiment_index carries 3 rows per (bank, aspect), one per window
# ('7d', '30d', 'all_time', see aggregate/index.py). Overview and Topics use the
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
    return None if row.empty or row.iloc[0]["n"] == 0 else row.iloc[0]


# ---------------------------------------------------------------- Overview
if page == "Overview":
    page_header("How are Singapore's banks being talked about?",
                "Every sentence we collected about DBS, OCBC and UOB is scored from -1 (very "
                "negative) to +1 (very positive), then averaged. Zero is neutral.")

    scored = {b: overall(b) for b in BANKS}
    live = {b: r for b, r in scored.items() if r is not None}
    if live:
        top = max(live, key=lambda b: live[b]["score"])
        low = min(live, key=lambda b: live[b]["score"])
        gap = float(live[top]["score"] - live[low]["score"])
        if len(live) < 2:
            msg = f"Only {top} has data so far."
        elif gap < 0.05:
            msg = (f"The three banks are close. <b>{top}</b> is highest at {live[top]['score']:+.3f} and "
                   f"<b>{low}</b> lowest at {live[low]['score']:+.3f}, a gap too small to call a real "
                   f"difference. All read as <b>{score_word(float(live[top]['score'])).lower()}</b>.")
        else:
            msg = (f"<b>{top}</b> is the most positively covered at {live[top]['score']:+.3f}, "
                   f"<b>{low}</b> the least at {live[low]['score']:+.3f}.")
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
                spark = spark[spark.sufficient]["score"].tolist()[-12:]
            except Exception:
                spark = []
            recent = df_all[(df_all.bank == bank) & (df_all.aspect == "ALL")
                            & (df_all.window == "30d")]
            delta = (float(recent.iloc[0]["score"]) - float(r["score"])
                     if not recent.empty and recent.iloc[0]["n"] > 0 else None)
            st.markdown(bank_card(bank, float(r["score"]), int(r["n"]), delta, spark),
                        unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([1, 1])
    with left:
        box = card("What the sentences say",
                   "Share of each bank's sentences that were positive, neutral or negative.")
        mix_rows = []
        for b, r in live.items():
            run = 0.0
            for i, (lab, k) in enumerate((("Positive", "pos_n"), ("Neutral", "neu_n"),
                                          ("Negative", "neg_n"))):
                share = int(r[k]) / max(int(r["n"]), 1)
                mix_rows.append({"bank": b, "label": lab, "count": int(r[k]), "order": i,
                                 "share": share, "mid": run + share / 2,
                                 "pct": f"{share:.0%}" if share >= 0.06 else ""})
                run += share
        mix = pd.DataFrame(mix_rows)
        if not mix.empty:
            box.altair_chart(mix_chart(mix), use_container_width=True, theme=None)
            neutral_share = mix[mix.label == "Neutral"]["count"].sum() / max(mix["count"].sum(), 1)
            box.caption(f"Most sentences are neutral ({neutral_share:.0%}). That is normal for "
                        "news and filings, and it is why the scores sit close to zero.")
    with right:
        box = card("Are they getting better or worse?",
                   "Quarterly average sentiment. A missing stretch means too little data that quarter.")
        frames = []
        for b in live:
            try:
                s = load_time_series(b, "ALL", "quarter")
                s = s[s.sufficient].assign(bank=b)
                frames.append(s[["period", "bank", "score", "n"]])
            except Exception:
                pass
        if frames:
            trend_df = pd.concat(frames)
            box.altair_chart(trend_chart(trend_df), use_container_width=True, theme=None)
        else:
            box.info("Not enough history to draw a trend yet.")

    st.write("")
    box = card("Why the banks differ: where the data comes from",
               "Same scores split by source. Earnings material is management describing its own "
               "results, so it reads far more positive than retail chatter, and DBS supplies about six "
               "times as much of it as the others. A gap between banks can come from that mix and not "
               "from real sentiment.")
    breakdown_df = load_source_breakdown()
    if breakdown_df.empty:
        box.info("No per-source rows yet - run `python -m aggregate.index`.")
    else:
        box.altair_chart(source_chart(breakdown_df), use_container_width=True, theme=None)
        with box.expander("See the numbers"):
            pivot_src = breakdown_df.pivot(index="source", columns="bank", values="score")
            pivot_src_n = breakdown_df.pivot(index="source", columns="bank", values="n")
            st.dataframe(heatmap_table(pivot_src), use_container_width=True)
            if not HAS_MATPLOTLIB:
                st.caption("Colour scale unavailable: matplotlib is not installed.")
            st.caption("Sentence count behind each cell:")
            st.dataframe(pivot_src_n.fillna(0).astype(int), use_container_width=True)

    st.write("")
    box = card("What professional analysts say",
               "Yahoo Finance consensus: how many analysts cover each bank and their average price "
               "target. This is not the content of any analyst report and is separate from the "
               "sentiment scores above.")
    consensus_df = load_analyst_consensus()
    if consensus_df.empty:
        box.info("No analyst consensus data yet - run `python -m ingest.yahoo_analyst`.")
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
                    upside = 100 * (b["target_mean"] - b["current_price"]) / b["current_price"]
                st.metric(
                    f"{bank}: {str(b['recommendation_key'] or 'n/a').replace('_', ' ')}",
                    f"S${b['target_mean']:.2f}" if pd.notna(b["target_mean"]) else "n/a",
                    delta=f"{upside:+.1f}% vs current price" if upside is not None else None)
                st.caption(f"{int(b['n_analysts'])} analysts, as of {b['as_of_date']}"
                           if pd.notna(b["n_analysts"]) else f"as of {b['as_of_date']}")
    disclosure_footer()

# ------------------------------------------------------------------ Topics
elif page == "Topics":
    page_header("What are people talking about?",
                "The same sentiment, split by topic such as dividends or asset quality. A sentence "
                "can count under more than one topic.")
    aspect_df = df[df.aspect != "ALL"]
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
                    [(r.aspect, float(r.score)) for r in sub.tail(k).iloc[::-1].itertuples()],
                    [(r.aspect, float(r.score)) for r in sub.head(k).itertuples()])
            else:
                best_worst[bank] = ([], [])

        if not solid.empty:
            hi = solid.loc[solid.score.idxmax()]
            lo = solid.loc[solid.score.idxmin()]
            st.markdown(takeaway(
                "The short version",
                f"The warmest topic is <b>{pretty(hi.aspect).lower()}</b> at <b>{hi.bank}</b> "
                f"({hi.score:+.2f}). The coolest is <b>{pretty(lo.aspect).lower()}</b> at "
                f"<b>{lo.bank}</b> ({lo.score:+.2f}). Faded cells below have fewer than "
                f"{MIN_TOPIC_N} sentences and should not be over-read."), unsafe_allow_html=True)

        box = card("Sentiment by topic",
                   "Green is positive, red is negative, grey is neutral. Hover a cell for how many "
                   "sentences it rests on. 'Other' collects sentences that match no topic.")
        box.altair_chart(heatmap_chart(aspect_df), use_container_width=True, theme=None)

        st.write("")
        st.markdown("#### Strengths and weak spots")
        st.caption(f"Each bank's best and weakest topics, using only topics with at least "
                   f"{MIN_TOPIC_N} sentences.")
        for col, bank in zip(st.columns(3), BANKS):
            with col:
                best, worst = best_worst[bank]
                st.markdown(strengths_card(bank, best, worst), unsafe_allow_html=True)

        st.write("")
        with st.expander("See the numbers"):
            pivot_score = aspect_df.pivot(index="aspect", columns="bank", values="score")
            pivot_n = aspect_df.pivot(index="aspect", columns="bank", values="n")
            st.dataframe(heatmap_table(pivot_score), use_container_width=True)
            if not HAS_MATPLOTLIB:
                st.caption("Colour scale unavailable: matplotlib is not installed.")
            st.caption("Sample size per cell:")
            st.dataframe(pivot_n.astype(int), use_container_width=True)
    disclosure_footer()

# ------------------------------------------------------------------ Trends
elif page == "Trends":
    page_header("How has sentiment moved?",
                "Pick a bank and a topic. The line uses the same weighting as the headline numbers, "
                "and a gap means there was too little data that period, not neutral sentiment.")
    c1, c2, c3 = st.columns([1, 1, 1.2])
    with c1:
        ts_bank = st.selectbox("Bank", BANKS, key="ts_bank")
    with c2:
        ts_aspects = ["ALL"] + sorted(df_all[df_all.aspect != "ALL"]["aspect"].unique().tolist())
        ts_aspect = st.selectbox("Topic", ts_aspects, key="ts_aspect",
                                 format_func=lambda a: "Overall" if a == "ALL" else pretty(a))
    with c3:
        bucket = st.radio("Group by", ["month", "quarter", "week"], index=1, horizontal=True,
                          key="ts_bucket")

    window_df = df_all[(df_all.bank == ts_bank) & (df_all.aspect == ts_aspect)]
    window_order = {"7d": 0, "30d": 1, "all_time": 2}
    window_names = {"7d": "Last 7 days", "30d": "Last 30 days", "all_time": "All time"}
    window_df = window_df.assign(_order=window_df.window.map(window_order)).sort_values("_order")

    if window_df.empty:
        st.info("No data for this bank and topic.")
    else:
        for col, (_, r) in zip(st.columns(3), window_df.iterrows()):
            with col:
                name = window_names.get(r["window"], r["window"])
                if r["n"] == 0:
                    st.metric(name, "No data")
                else:
                    st.metric(name, f"{r['score']:+.3f}", help=f"{int(r['n'])} sentences")
                    st.caption(f"{score_word(float(r['score']))}, from {int(r['n']):,} sentences")

    series = load_time_series(ts_bank, ts_aspect, bucket)
    st.write("")
    box = card(f"{ts_bank}: {'overall' if ts_aspect == 'ALL' else pretty(ts_aspect).lower()} sentiment over time")
    if series.empty:
        box.info("Not enough data to plot a series for this selection.")
    else:
        plotted = series[series.sufficient]
        if plotted.empty:
            box.info("Every period in this selection is below the volume floor.")
        else:
            box.altair_chart(area_chart(plotted, color=BANK_COLORS.get(ts_bank, ACCENT)),
                             use_container_width=True, theme=None)
            thin = int((~series.sufficient).sum())
            if thin:
                box.caption(f"{thin} period(s) with too little data are left off the line.")
            with box.expander("See the numbers"):
                st.dataframe(
                    series[["period", "score", "n", "pos_n", "neu_n", "neg_n", "sufficient"]],
                    use_container_width=True, hide_index=True)
    disclosure_footer()

# ---------------------------------------------------------------- Evidence
elif page == "Evidence":
    page_header("What do the sentences actually say?",
                "The most recent sentences behind a score, so you can judge the numbers for yourself.")
    c1, c2 = st.columns(2)
    with c1:
        sel_bank = st.selectbox("Bank", BANKS)
    with c2:
        aspects_available = ["ALL"] + sorted(df[df.aspect != "ALL"]["aspect"].unique().tolist())
        sel_aspect = st.selectbox("Topic", aspects_available,
                                  format_func=lambda a: "Overall" if a == "ALL" else pretty(a))

    evidence = load_evidence(sel_bank, sel_aspect)
    if evidence.empty:
        st.info("No evidence sentences for this selection.")
    else:
        has_label = "label" in evidence.columns
        for _, row in evidence.iterrows():
            st.markdown(quote_card(
                row["text"], row["source"], row["published_at"], row["url"],
                row["label"] if has_label else None,
                row["confidence"] if has_label else None), unsafe_allow_html=True)
    disclosure_footer()

# --------------------------------------------------------------------- Ask
elif page == "Ask":
    page_header("Ask about the data",
                "Answers come from the sentiment index in this dashboard, not from the model's own "
                "knowledge. It does not give investment advice.")

    # Imported lazily: chatbot.agent pulls in the model backends and the
    # embedding store, which would slow every dashboard start even for
    # someone who never opens this page.
    from chatbot.agent import Conversation
    from chatbot.suggestions import get_suggestions

    st.caption(
        "A local model may still cite evidence it never retrieved. Answers flagged with a "
        "verification warning should not be trusted, and figures that match nothing the tools "
        "returned are flagged too. It remembers the last few turns, so follow-ups like "
        "\"and OCBC?\" work."
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "conversation" not in st.session_state:
        st.session_state.conversation = Conversation()

    for role, content in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(content)

    # Suggestions are generated from what the index actually holds, so a
    # clicked suggestion won't dead-end on "insufficient data".
    pending = None
    st.markdown("**Try one of these**")
    suggestions = get_suggestions(limit=6)
    for row_start in range(0, len(suggestions), 2):
        for col, item in zip(st.columns(2), suggestions[row_start:row_start + 2]):
            if col.button(item["question"], key=f"sugg-{row_start}-{item['question']}",
                          use_container_width=True):
                pending = item["question"]

    typed = st.chat_input("Or ask your own question")
    question = pending or typed

    if question:
        st.session_state.chat_history.append(("user", question))
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking - a local model can take a minute..."):
                try:
                    answer = st.session_state.conversation.ask(question).answer
                except Exception as exc:  # backend unreachable, bad key, etc.
                    answer = (f"The chatbot backend could not be reached: `{exc}`\n\n"
                              "If you are using the local backend, check that "
                              "`ollama serve` is running.")
            st.markdown(answer)
        st.session_state.chat_history.append(("assistant", answer))

    if st.session_state.chat_history and st.button("Clear conversation"):
        st.session_state.chat_history = []
        st.session_state.conversation = Conversation()
        st.rerun()

    disclosure_footer()
