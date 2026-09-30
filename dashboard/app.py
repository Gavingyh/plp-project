"""
Streamlit dashboard — see docs/DESIGN.md.

Five tabs: bank overview, aspect heatmap, time series, evidence drill-down and
chat. Every view carries the disclosures the design calls for — sample size
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
    """A red-yellow-green graded table, or a plain rounded one without matplotlib.

    Returns something st.dataframe can render either way.
    """
    if HAS_MATPLOTLIB:
        return frame.style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1).format("{:.3f}")
    return frame.round(3)

st.set_page_config(page_title="SG Bank Sentiment Dashboard", layout="wide")


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
        f"Not financial advice — sentiment is an indicator, not a recommendation. "
        f"Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        "See docs/STATUS.md for known limitations (Reddit skews toward DBS, "
        "news volume rises towards the present, analyst figures are Yahoo "
        "consensus aggregates rather than analyst reports, scores come from base "
        "FinBERT applied zero-shot, and aspects are matched by embedding "
        "similarity, so a sentence often counts under several aspects)."
    )


st.title("🏦 Singapore Bank Sentiment Dashboard")
st.caption("DBS · OCBC · UOB — overall & aspect-based sentiment from news, social, and earnings sources")

df_all = load_index()
if df_all.empty:
    st.warning("No sentiment data yet. Run the pipeline: `python run_daily_batch.py` → "
               "`python -m preprocess.pipeline` → `python -m aspects.assign` → "
               "`python -m sentiment.score` → `python -m aggregate.index`")
    st.stop()

# sentiment_index now carries 3 rows per (bank, aspect) — one per window
# ('7d', '30d', 'all_time', see aggregate/index.py). Overview/Heatmap use the
# all-time snapshot; Time Series is the one view that shows all three.
df = df_all[df_all.window == "all_time"]

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Overview", "Aspect Heatmap", "Time Series", "Evidence", "Chat"])

with tab1:
    st.subheader("Overall sentiment by bank (all-time)")
    cols = st.columns(3)
    for col, bank in zip(cols, BANKS):
        row = df[(df.bank == bank) & (df.aspect == "ALL")]
        with col:
            if row.empty or row.iloc[0]["n"] == 0:
                st.metric(bank, "No data")
            else:
                r = row.iloc[0]
                st.metric(bank, f"{r['score']:+.3f}", help=f"n={int(r['n'])} data points")
                st.caption(f"n={int(r['n'])} · pos {int(r['pos_n'])} / neu {int(r['neu_n'])} / neg {int(r['neg_n'])}")

    st.divider()
    st.subheader("What the blended score is made of")
    st.caption(
        "The headline numbers above blend every source. These are the same "
        "scores split by source. Check them before comparing banks, because "
        "coverage is very unequal: earnings material is management describing "
        "its own results and scores far more positive than retail chatter, and "
        "DBS contributes about six times as much of it as the other two "
        "because it publishes analyst-call transcripts. A cross-bank gap in "
        "the blended number may reflect that rather than real sentiment."
    )
    breakdown_df = load_source_breakdown()
    if breakdown_df.empty:
        st.info("No per-source rows yet — run `python -m aggregate.index`.")
    else:
        pivot_src = breakdown_df.pivot(index="source", columns="bank", values="score")
        pivot_src_n = breakdown_df.pivot(index="source", columns="bank", values="n")
        st.dataframe(heatmap_table(pivot_src), use_container_width=True)
        if not HAS_MATPLOTLIB:
            st.caption("Colour scale unavailable: matplotlib is not installed.")
        st.caption("Sentence count (n) behind each cell:")
        st.dataframe(pivot_src_n.fillna(0).astype(int), use_container_width=True)

    st.divider()
    st.subheader("Professional analyst consensus")
    st.caption(
        "Consensus aggregates from Yahoo Finance (unofficial API) — the number of "
        "analysts covering each bank and their average price target. This is NOT "
        "the content of any analyst report, and is separate from the social/news "
        "sentiment scores above."
    )
    consensus_df = load_analyst_consensus()
    if consensus_df.empty:
        st.info("No analyst consensus data yet — run `python -m ingest.yahoo_analyst`.")
    else:
        acols = st.columns(3)
        for acol, bank in zip(acols, BANKS):
            brow = consensus_df[consensus_df.bank == bank]
            with acol:
                if brow.empty:
                    st.metric(f"{bank} consensus", "No data")
                else:
                    b = brow.iloc[0]
                    upside = None
                    if pd.notna(b["target_mean"]) and b["current_price"]:
                        upside = 100 * (b["target_mean"] - b["current_price"]) / b["current_price"]
                    st.metric(
                        f"{bank} — {b['recommendation_key'] or 'n/a'}",
                        f"S${b['target_mean']:.2f}" if pd.notna(b["target_mean"]) else "n/a",
                        delta=f"{upside:+.1f}% vs spot" if upside is not None else None,
                    )
                    st.caption(f"{int(b['n_analysts'])} analysts · as of {b['as_of_date']}"
                               if pd.notna(b["n_analysts"]) else f"as of {b['as_of_date']}")
    disclosure_footer()

with tab2:
    st.subheader("Sentiment by bank × aspect (all-time)")
    aspect_df = df[df.aspect != "ALL"]
    if aspect_df.empty:
        st.info("No aspect-level data yet.")
    else:
        pivot_score = aspect_df.pivot(index="aspect", columns="bank", values="score")
        pivot_n = aspect_df.pivot(index="aspect", columns="bank", values="n")
        st.dataframe(heatmap_table(pivot_score), use_container_width=True)
        if not HAS_MATPLOTLIB:
            st.caption("Colour scale unavailable: matplotlib is not installed.")
        st.caption("Sample size (n) per cell:")
        st.dataframe(pivot_n.astype(int), use_container_width=True)
    disclosure_footer()

with tab3:
    st.subheader("Sentiment over time")
    st.caption(
        "A continuous series computed with the same weighting and shrinkage as "
        "the stored index, so it cannot disagree with the headline numbers. "
        "Thin buckets are dropped rather than interpolated — a gap in the line "
        "means there was not enough data that period, not neutral sentiment."
    )
    c1, c2 = st.columns(2)
    with c1:
        ts_bank = st.selectbox("Bank", BANKS, key="ts_bank")
    with c2:
        ts_aspects = ["ALL"] + sorted(df_all[df_all.aspect != "ALL"]["aspect"].unique().tolist())
        ts_aspect = st.selectbox("Aspect", ts_aspects, key="ts_aspect")

    window_df = df_all[(df_all.bank == ts_bank) & (df_all.aspect == ts_aspect)]
    window_order = {"7d": 0, "30d": 1, "all_time": 2}
    window_df = window_df.assign(_order=window_df.window.map(window_order)).sort_values("_order")

    if window_df.empty:
        st.info("No data for this bank/aspect.")
    else:
        wc1, wc2, wc3 = st.columns(3)
        for col, (_, r) in zip((wc1, wc2, wc3), window_df.iterrows()):
            with col:
                if r["n"] == 0:
                    st.metric(r["window"], "No data")
                else:
                    st.metric(r["window"], f"{r['score']:+.3f}", help=f"n={int(r['n'])}")
                    st.caption(f"n={int(r['n'])}")
    st.divider()

    bucket = st.radio("Bucket", ["month", "quarter", "week"], horizontal=True,
                      key="ts_bucket")
    series = load_time_series(ts_bank, ts_aspect, bucket)
    if series.empty:
        st.info("Not enough data to plot a series for this selection.")
    else:
        plotted = series[series.sufficient]
        if plotted.empty:
            st.info("Every bucket in this selection is below the volume floor.")
        else:
            st.line_chart(plotted.set_index("period")["score"])
            thin = int((~series.sufficient).sum())
            if thin:
                st.caption(f"{thin} thin bucket(s) omitted from the line.")
            with st.expander("Underlying counts"):
                st.dataframe(
                    series[["period", "score", "n", "pos_n", "neu_n", "neg_n", "sufficient"]],
                    use_container_width=True, hide_index=True)
    disclosure_footer()

with tab4:
    st.subheader("Evidence drill-down")
    c1, c2 = st.columns(2)
    with c1:
        sel_bank = st.selectbox("Bank", BANKS)
    with c2:
        aspects_available = ["ALL"] + sorted(df[df.aspect != "ALL"]["aspect"].unique().tolist())
        sel_aspect = st.selectbox("Aspect", aspects_available)

    evidence = load_evidence(sel_bank, sel_aspect)
    if evidence.empty:
        st.info("No evidence sentences for this selection.")
    else:
        for _, row in evidence.iterrows():
            label = f" — {row['label']} ({row['confidence']:.2f})" if "label" in row else ""
            st.markdown(f"**[{row['source']}]**{label} {row['text']}")
            st.caption(f"{row['published_at']} · [source]({row['url']})")
            st.divider()
    disclosure_footer()


with tab5:
    st.subheader("Ask about the data")

    # Imported lazily: chatbot.agent pulls in the model backends and the
    # embedding store, which would slow every dashboard start even for
    # someone who never opens this tab.
    from chatbot.agent import Conversation
    from chatbot.suggestions import get_suggestions

    st.caption(
        "Answers come from the sentiment index in this dashboard, not from the "
        "model's own knowledge. A local model may still cite evidence it never "
        "retrieved - answers flagged with a verification warning should not be "
        "trusted, and figures that match nothing the tools returned are flagged too. "
        "The chatbot remembers the last few turns, so follow-ups like \"and OCBC?\" work. "
        "It does not give investment advice."
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
    st.markdown("**Try one of these:**")
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
