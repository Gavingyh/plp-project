"""Recent-trend semantics, history coverage and navigation to supporting text."""

from unittest.mock import patch

import pandas as pd
import pytest

from dashboard import data
from dashboard.api_client import ApiError
from dashboard.style import LIGHT, history_chart
from dashboard.trends import visible_history
from test_dashboard_views import DashboardAppTestCase, fake_api, series_row


def test_trend_adapter_uses_backend_comparison_and_validates_it():
    payload = {
        "trend_available": True,
        "direction": "declining",
        "delta_7d_vs_30d": -0.11,
    }
    with patch("dashboard.data.request_json", return_value=payload) as request:
        assert data.load_trend("DBS", "ALL") == payload
        request.assert_called_once_with(
            "GET", "/sentiment/trend", params={"bank": "DBS", "aspect": "ALL"}
        )
    for invalid in (
        {},
        {"trend_available": "false"},
        {**payload, "direction": "buy"},
        {**payload, "delta_7d_vs_30d": float("nan")},
    ):
        with patch("dashboard.data.request_json", return_value=invalid), pytest.raises(
            ApiError
        ):
            data.load_trend("DBS", "ALL")


def test_history_uses_snapshot_months_preserves_gaps_and_flags_partial_period():
    periods = pd.period_range("2024-09", "2026-09", freq="M")
    frame = pd.DataFrame([series_row(str(period)) for period in periods])
    frame["period_start"] = periods.start_time
    frame["period_end"] = periods.end_time
    frame.loc[1, ["score", "sufficient", "n"]] = [float("nan"), False, 0]
    result = visible_history(frame, "2026-09-25", "Latest 24 months")
    assert len(result) == 24
    assert result.period.iloc[0] == "2024-10"
    assert not result.sufficient.iloc[0]
    assert result.period_status.iloc[-1] == "Incomplete calendar period"
    assert len(frame) == 25  # display clipping doesn't mutate the API result
    spec = history_chart(result, LIGHT.bank_colors["DBS"]).to_dict()
    assert spec["vconcat"][0]["mark"]["interpolate"] == "linear"
    assert spec["vconcat"][1]["encoding"]["y"]["field"] == "n"
    assert spec["resolve"]["scale"]["x"] == "shared"
    all_history = visible_history(frame, "2026-09-30", "All history")
    assert len(all_history) == 25
    assert not all_history.period_status.eq("Incomplete calendar period").any()


class TrendsPageTests(DashboardAppTestCase):
    def test_summary_uses_api_direction_and_drilldown_keeps_context(self):
        self.request.side_effect = fake_api(
            trend_payload={
                "trend_available": True,
                "direction": "declining",
                "delta_7d_vs_30d": -0.11,
            }
        )
        app = self.page("Topics")
        app.button(key="topic_trend_OCBC").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.selectbox(key="ts_bank").value, "OCBC")
        self.assertEqual(app.selectbox(key="ts_aspect").value, "dividend_policy")
        self.assertTrue(any("more negative" in item.value for item in app.markdown))
        self.assertTrue(any("-0.110" in item.value for item in app.caption))
        # The index fixture has identical displayed scores: this direction must come from the API.
        app.button(key="trend_evidence").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.selectbox(key="evidence_bank").value, "OCBC")
        self.assertEqual(app.selectbox(key="evidence_aspect").value, "dividend_policy")

    def test_unavailable_trend_does_not_invent_stability(self):
        app = self.page("Trends")
        self.assertTrue(
            any("Not enough recent data" in item.value for item in app.info)
        )
        self.assertFalse(app.error)
        self.assertTrue(
            any("History uses calendar buckets" in item.value for item in app.caption)
        )
        self.assertIsNotNone(app.button(key="trend_evidence"))

    def test_trend_service_error_leaves_history_available(self):
        self.request.side_effect = fake_api(fail_path="/sentiment/trend")
        app = self.page("Trends")
        self.assertTrue(
            any("Recent comparison unavailable" in item.value for item in app.warning)
        )
        self.assertFalse(app.error)
