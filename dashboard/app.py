"""
Streamlit dashboard — MVP plan Phase 7.

Four views only, per plan scoping: bank overview, aspect heatmap, time series,
evidence drill-down. Every view carries the plan's required disclosures:
sample size (n), last-refresh timestamp, and a not-financial-advice notice —
these are the trust anchors the plan calls out, not decoration.

USAGE:
  streamlit run dashboard/app.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.db import get_connection

BANKS = ["DBS", "OCBC", "UOB"]

st.set_page_config(page_title="SG Bank Sentiment Dashboard", layout="wide")


@st.cache_data(ttl=300)
def load_index() -> pd.DataFrame:
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM sentiment_index", conn)
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


def disclosure_footer():
    st.caption(
        f"Not financial advice — sentiment is an indicator, not a recommendation. "
        f"Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        "See docs/ for known data limitations (Reddit skews toward DBS, ~1-month news "
        "window, analyst view is a news-derived proxy, sentiment model is currently base "
        "FinBERT pending Phase 5 fine-tuning)."
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

tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Aspect Heatmap", "Time Series", "Evidence"])

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
    disclosure_footer()

with tab2:
    st.subheader("Sentiment by bank × aspect (all-time)")
    aspect_df = df[df.aspect != "ALL"]
    if aspect_df.empty:
        st.info("No aspect-level data yet.")
    else:
        pivot_score = aspect_df.pivot(index="aspect", columns="bank", values="score")
        pivot_n = aspect_df.pivot(index="aspect", columns="bank", values="n")
        st.dataframe(
            pivot_score.style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1).format("{:.3f}"),
            use_container_width=True,
        )
        st.caption("Sample size (n) per cell:")
        st.dataframe(pivot_n.astype(int), use_container_width=True)
    disclosure_footer()

with tab3:
    st.subheader("Sentiment by window: 7d vs 30d vs all-time")
    st.caption(
        "Not a continuous time series yet — three discrete rolling windows "
        "(aggregate/index.py). A day-by-day series is a documented next step; "
        "this at least shows real recent-vs-baseline movement rather than a stub."
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
        if len(window_df) >= 2 and (window_df["n"] >= 5).sum() >= 2:
            st.line_chart(window_df.set_index("window")["score"])
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
