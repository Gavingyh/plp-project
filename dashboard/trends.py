"""Trends view: observed history, sample volume and the API's recent-trend summary."""

from collections.abc import Callable
import html

import pandas as pd
import streamlit as st

from dashboard.api_client import ApiError
from dashboard.style import (
    Palette,
    history_chart,
    pretty,
    score_word,
    takeaway,
    section_heading,
)

BANKS = ["DBS", "OCBC", "UOB"]


def visible_history(series: pd.DataFrame, data_as_of: str, view: str) -> pd.DataFrame:
    """Keep complete buckets that overlap the requested calendar-month range."""
    frame = series.copy()
    anchor = pd.to_datetime(data_as_of, errors="coerce")
    if frame.empty:
        return frame
    frame["period_status"] = "Snapshot date unknown"
    if pd.notna(anchor):
        end_of_day = (
            anchor.normalize() + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        )
        frame["period_status"] = frame["period_end"].map(
            lambda end: (
                "Incomplete calendar period"
                if end > end_of_day
                else "Period ended by snapshot date"
            )
        )
        if view == "Latest 24 months":
            # Include the snapshot month plus the preceding 23 calendar months.
            cutoff = (anchor.to_period("M") - 23).start_time
            frame = frame[
                (frame.period_end >= cutoff) & (frame.period_start <= end_of_day)
            ]
    return frame


def render(
    index: pd.DataFrame,
    data_as_of: str,
    palette: Palette,
    load_series: Callable,
    load_trend: Callable,
    on_view_evidence: Callable,
):
    aspects = ["ALL"] + sorted(
        index.loc[index.aspect != "ALL", "aspect"].unique().tolist(), key=pretty
    )
    for key, query, options in (
        ("ts_bank", "bank", BANKS),
        ("ts_aspect", "topic", aspects),
    ):
        if key not in st.session_state:
            remembered = st.query_params.get(query)
            st.session_state[key] = remembered if remembered in options else options[0]

    with st.container(border=True, key="trend_controls"):
        c1, c2, c3, c4 = st.columns([1, 1.4, 1.2, 1.6])
        bank = c1.selectbox("Bank", BANKS, key="ts_bank")
        aspect = c2.selectbox(
            "Topic",
            aspects,
            key="ts_aspect",
            format_func=lambda a: "Overall" if a == "ALL" else pretty(a),
        )
        view = c3.selectbox(
            "History", ["Latest 24 months", "All history"], key="ts_view"
        )
        bucket = c4.radio(
            "Group by",
            ["month", "quarter", "week"],
            horizontal=True,
            key="ts_bucket",
            format_func=lambda b: {
                "month": "Monthly",
                "quarter": "Quarterly",
                "week": "Weekly",
            }[b],
        )
    for key, value in (("bank", bank), ("topic", aspect)):
        if st.query_params.get(key) != value:
            st.query_params[key] = value
    st.caption(
        f"Recent windows end on {data_as_of}, the newest stored data date. They do not end today."
    )

    topic = (
        "overall sentiment"
        if aspect == "ALL"
        else f"{pretty(aspect).lower()} sentiment"
    )
    trend_details = None
    try:
        trend = load_trend(bank, aspect)
    except ApiError as exc:
        st.warning(f"Recent comparison unavailable. {exc}")
    else:
        if trend["trend_available"]:
            wording = {
                "improving": "more positive",
                "declining": "more negative",
                "stable": "similar",
            }[trend["direction"]]
            message = (
                f"<b>{bank}</b>: {html.escape(topic)} is <b>{wording}</b> in the latest seven days "
                "compared with the overlapping 30-day baseline."
            )
            st.markdown(
                takeaway("Recent movement · latest 7 days vs 30-day baseline", message),
                unsafe_allow_html=True,
            )
            trend_details = (
                f"Recent comparison: {trend['delta_7d_vs_30d']:+.3f} score points before small-sample shrinkage. "
                "The summary cards retain the displayed index scores, so subtracting them may give a different value. "
                "The 30-day baseline includes the latest seven days. This is a descriptive comparison, not a significance test."
            )
        else:
            st.info(
                "Not enough recent data for a 7-day versus 30-day comparison. Historical scores remain available where coverage permits."
            )

    window_df = index[(index.bank == bank) & (index.aspect == aspect)]
    for col, window, name in zip(
        st.columns(3),
        ("7d", "30d", "all_time"),
        ("Latest 7 days", "Latest 30 days", "All available data"),
    ):
        rows = window_df[window_df.window == window]
        row = None if rows.empty else rows.iloc[0]
        n = 0 if row is None else int(row["n"])
        with col.container(border=True, key=f"trend_window_{window}"):
            if row is None or not n:
                st.metric(name, "No data")
                st.caption("0 scored sentences")
            elif row["insufficient_data"]:
                st.metric(name, "Too little data")
                st.caption(f"Only {n:,} sentences · score withheld")
            else:
                st.metric(name, f"{row['score']:+.3f}")
                st.caption(
                    f"{score_word(float(row['score']))} · {n:,} scored sentences"
                )

    try:
        series = visible_history(load_series(bank, aspect, bucket), data_as_of, view)
    except ApiError as exc:
        st.error(str(exc))
        return
    with st.container(border=True, key="panel_history"):
        heading, action = st.columns([2.4, 1], vertical_alignment="center")
        heading.markdown(
            section_heading(
                f"{bank} · {'Overall' if aspect == 'ALL' else pretty(aspect)}",
                "Sentiment over time",
            ),
            unsafe_allow_html=True,
        )
        action.button(
            "View supporting evidence",
            key="trend_evidence",
            on_click=on_view_evidence,
            args=(bank, aspect),
            use_container_width=True,
        )
        if series.empty:
            st.info(
                "No history in this display range. Try All history or another topic."
            )
        else:
            if not series.sufficient.any():
                st.info(
                    "Every period shown has too few sentences for a sentiment score. The volume bars show the available coverage."
                )
            st.altair_chart(
                history_chart(series, palette.bank_colors[bank], palette=palette),
                use_container_width=True,
                theme=None,
            )
            st.caption(
                f"{series.period.iloc[0]} to {series.period.iloc[-1]} · "
                "Line: sentiment score. Bars: scored sentences. Gaps mean missing data or fewer than five sentences. "
                "History uses calendar buckets; the cards above use rolling windows."
            )
            if series.period_status.eq("Incomplete calendar period").any():
                st.caption(
                    f"The latest {bucket} is incomplete: the snapshot ends on {data_as_of}. Its volume is not directly comparable with a full period."
                )
            with st.expander("See history values and coverage"):
                st.dataframe(
                    series.assign(score=series.score.where(series.sufficient))[
                        [
                            "period",
                            "score",
                            "n",
                            "pos_n",
                            "neu_n",
                            "neg_n",
                            "sufficient",
                            "period_status",
                        ]
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
    st.caption("Opens recent examples for this bank and topic, across available dates.")
    if trend_details:
        with st.expander("How this recent comparison is calculated"):
            st.caption(trend_details)
