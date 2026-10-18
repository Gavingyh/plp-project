"""Browse a clearly bounded set of recent evidence, without model inference."""

from collections.abc import Callable
import html

import pandas as pd
import streamlit as st

from dashboard.api_client import ApiError
from dashboard.style import pretty, quote_card

BANKS = ["DBS", "OCBC", "UOB"]
PAGE_SIZE = 10


def reset_filters():
    st.session_state.evidence_source = "ALL"
    st.session_state.evidence_sentiment = "ALL"
    st.session_state.evidence_visible = PAGE_SIZE


def _reset_page():
    st.session_state.evidence_visible = PAGE_SIZE


def _show_more():
    st.session_state.evidence_visible = (
        st.session_state.get("evidence_visible", PAGE_SIZE) + PAGE_SIZE
    )


def filter_examples(frame: pd.DataFrame, source: str, sentiment: str) -> pd.DataFrame:
    """Filter only the loaded rows; never present this subset as corpus-wide search."""
    filtered = frame.copy()
    if source != "ALL":
        filtered = filtered[filtered.source == source]
    if sentiment != "ALL" and "label" in filtered.columns:
        filtered = filtered[filtered.label == sentiment]
    return filtered


def render(index: pd.DataFrame, load_evidence: Callable):
    aspects = ["ALL"] + sorted(
        index.loc[index.aspect != "ALL", "aspect"].unique().tolist(), key=pretty
    )
    for key, query, options in (
        ("evidence_bank", "bank", BANKS),
        ("evidence_aspect", "topic", aspects),
    ):
        if key not in st.session_state:
            remembered = st.query_params.get(query)
            st.session_state[key] = remembered if remembered in options else options[0]
    with st.container(border=True, key="evidence_controls"):
        controls = st.columns([0.7, 1.5, 1.15, 1.05, 0.85], vertical_alignment="bottom")
        bank = controls[0].selectbox(
            "Bank", BANKS, key="evidence_bank", on_change=reset_filters
        )
        aspect = controls[1].selectbox(
            "Topic",
            aspects,
            key="evidence_aspect",
            format_func=lambda a: "Overall" if a == "ALL" else pretty(a),
            on_change=reset_filters,
        )
    for key, value in (("bank", bank), ("topic", aspect)):
        if st.query_params.get(key) != value:
            st.query_params[key] = value

    try:
        frame = load_evidence(bank, aspect)
    except ApiError as exc:
        st.error(str(exc))
        return
    context = "Overall" if aspect == "ALL" else pretty(aspect)
    if frame.empty:
        st.info(
            "No recent evidence is available for this bank and topic. Try another selection."
        )
        return

    frame = frame.assign(
        _published=pd.to_datetime(
            frame.published_at, format="mixed", utc=True, errors="coerce"
        )
    ).sort_values("_published", ascending=False, kind="stable", na_position="last")
    frame["display_date"] = (
        frame["_published"].dt.strftime("%Y-%m-%d").fillna("Date unknown")
    )
    dates = frame._published.dropna()
    date_note = (
        f" Dates in this loaded set (UTC): {dates.min():%d %b %Y}–{dates.max():%d %b %Y}."
        if not dates.empty
        else ""
    )
    st.markdown(
        '<div class="evidence-context">'
        f'<div class="count">{len(frame)}</div><div><strong>{bank} · {html.escape(context)}</strong>'
        "<span>Recent source excerpts · newest first</span></div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Loaded the {len(frame)} most recent matching sentences (maximum 30).{date_note}"
    )
    st.caption(
        "Recent examples, not the complete text behind the aggregate score. Filters apply only to this loaded set."
    )

    sources = ["ALL"] + sorted(frame.source.dropna().unique().tolist(), key=pretty)
    has_labels = "label" in frame.columns
    sentiments = ["ALL", "positive", "neutral", "negative"] if has_labels else ["ALL"]
    for key, options in (
        ("evidence_source", sources),
        ("evidence_sentiment", sentiments),
    ):
        if st.session_state.get(key) not in options:
            st.session_state[key] = "ALL"
    source = controls[2].selectbox(
        "Source",
        sources,
        format_func=lambda s: "All loaded sources" if s == "ALL" else pretty(s),
        key="evidence_source",
        on_change=_reset_page,
    )
    sentiment = controls[3].selectbox(
        "Sentiment",
        sentiments,
        format_func=lambda s: "All sentiments" if s == "ALL" else s.capitalize(),
        key="evidence_sentiment",
        disabled=not has_labels,
        on_change=_reset_page,
    )
    with controls[4]:
        st.button(
            "Reset filters",
            key="evidence_reset",
            on_click=reset_filters,
            use_container_width=True,
        )
    with st.expander("Reading these examples"):
        if not has_labels:
            st.caption(
                "Choose a specific topic to see its predicted sentiment labels and filter by sentiment."
            )
        else:
            st.caption(
                "Sentiment labels are model predictions. Model confidence is not measured accuracy."
            )

    filtered = filter_examples(frame, source, sentiment)
    if filtered.empty:
        st.info(
            "No matching sentences in the loaded examples. Reset the filters to see the other loaded sentences; this does not mean the full dataset has no matches."
        )
        return
    visible = min(st.session_state.get("evidence_visible", PAGE_SIZE), len(filtered))
    st.caption(
        f"Showing {visible} of {len(filtered)} matching examples · {len(frame)} recent sentences loaded · newest first"
    )
    for row in filtered.head(visible).itertuples(index=False):
        st.markdown(
            quote_card(
                row.text,
                row.source,
                row.display_date,
                row.url,
                getattr(row, "label", None),
                getattr(row, "confidence", None),
            ),
            unsafe_allow_html=True,
        )
    if visible < len(filtered):
        st.button(
            f"Show next {min(PAGE_SIZE, len(filtered) - visible)}",
            key="evidence_more",
            on_click=_show_more,
        )
