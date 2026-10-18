"""API responses adapted for dashboard views; no database or model imports."""

from datetime import datetime

import pandas as pd

from dashboard.api_client import ApiError, request_json

INDEX_COLUMNS = [
    "bank",
    "aspect",
    "source",
    "score",
    "n",
    "pos_n",
    "neu_n",
    "neg_n",
    "confidence_mean",
    "model_version",
    "computed_at",
    "insufficient_data",
]
SERIES_COLUMNS = [
    "period",
    "score",
    "n",
    "pos_n",
    "neu_n",
    "neg_n",
    "confidence_mean",
    "sufficient",
]


def _frame(payload: dict, key: str, columns: list[str]) -> pd.DataFrame:
    rows = payload.get(key)
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not set(columns).issubset(row) for row in rows
    ):
        raise ApiError(f"The API returned invalid {key} data.")
    # Keep a stable schema even when the API returns an empty list.
    return pd.DataFrame(rows, columns=columns)


def load_index() -> pd.DataFrame:
    frames = []
    for window in ("7d", "30d", "all_time"):
        payload = request_json(
            "GET",
            "/sentiment/index",
            params={"window": window, "source": "ALL"},
        )
        frame = _frame(payload, "rows", INDEX_COLUMNS)
        frame["window"] = window
        frame["data_as_of"] = payload.get("data_as_of")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def load_source_breakdown(window: str = "all_time") -> pd.DataFrame:
    payload = request_json(
        "GET",
        "/sentiment/index",
        params={"window": window, "source": "*"},
    )
    frame = _frame(payload, "rows", INDEX_COLUMNS)
    breakdown = frame.loc[
        (frame["aspect"] == "ALL") & (frame["source"] != "ALL")
    ].copy()
    breakdown.loc[breakdown["insufficient_data"].eq(True), "score"] = float("nan")
    return breakdown.sort_values(["bank", "source"]).reset_index(drop=True)


def load_evidence(bank: str, aspect: str) -> pd.DataFrame:
    params = {"bank": bank, "limit": 30}
    columns = ["sentence_id", "text", "source", "url", "published_at"]
    if aspect != "ALL":
        params["aspect"] = aspect
        columns += ["aspect", "label", "confidence"]
    payload = request_json("GET", "/evidence/latest", params=params)
    return _frame(payload, "rows", columns)


def load_analyst_consensus() -> pd.DataFrame:
    payload = request_json("GET", "/analyst-consensus/latest")
    return _frame(
        payload,
        "rows",
        [
            "bank",
            "as_of_date",
            "n_analysts",
            "recommendation_key",
            "target_mean",
            "current_price",
        ],
    )


def load_suggestions(limit: int = 6) -> list[dict]:
    payload = request_json("GET", "/suggestions", params={"limit": limit})
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("question"), str)
        or not item["question"].strip()
        for item in suggestions
    ):
        raise ApiError("The API returned invalid suggested questions.")
    return suggestions


def load_time_series(bank: str, aspect: str, bucket: str) -> pd.DataFrame:
    payload = request_json(
        "GET",
        "/sentiment/series",
        params={
            "bank": bank,
            "aspect": aspect,
            "bucket": bucket,
        },
    )
    frame = _frame(payload, "series", SERIES_COLUMNS)
    if frame.empty:
        return frame

    # The API omits buckets with no sentences. Insert them so chart lines
    # cannot bridge a completely missing week/month/quarter.
    freq = {"week": "W-SUN", "month": "M", "quarter": "Q"}[bucket]
    periods = [
        (
            pd.Period(datetime.strptime(f"{label}-1", "%G-W%V-%u"), freq=freq)
            if bucket == "week"
            else pd.Period(label, freq=freq)
        )
        for label in frame["period"]
    ]
    frame.index = pd.PeriodIndex(periods)
    frame = frame.reindex(pd.period_range(min(periods), max(periods), freq=freq))
    if bucket == "week":
        frame["period"] = [
            f"{p.start_time.isocalendar().year}-W{p.start_time.isocalendar().week:02d}"
            for p in frame.index
        ]
    elif bucket == "quarter":
        frame["period"] = [f"{p.year}-Q{p.quarter}" for p in frame.index]
    else:
        frame["period"] = frame.index.astype(str)
    frame["sufficient"] = frame["sufficient"].eq(True)
    for column in ("n", "pos_n", "neu_n", "neg_n"):
        frame[column] = frame[column].fillna(0).astype(int)
    return frame.reset_index(drop=True)
