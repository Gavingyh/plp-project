"""Data adapters and rendered data pages against a synthetic HTTP API.

Run without the project-wide model fixtures:
    python -m unittest discover -s tests -p test_dashboard_views.py -v
"""

import json as jsonlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard import data
from dashboard.api_client import ApiError
from dashboard.style import _plot_data, area_chart, sparkline, trend_chart

ROOT = Path(__file__).resolve().parents[1]
BANKS = ("DBS", "OCBC", "UOB")


def index_row(bank="DBS", aspect="ALL", source="ALL", n=100):
    return dict(
        bank=bank,
        aspect=aspect,
        source=source,
        score=0.12,
        n=n,
        pos_n=n,
        neu_n=0,
        neg_n=0,
        confidence_mean=0.8,
        model_version="finbert-adapted-test",
        computed_at="2026-10-14T01:02:00+00:00",
        insufficient_data=n < 5,
    )


def series_row(period, n=10):
    return dict(
        period=period,
        score=0.1,
        n=n,
        pos_n=n,
        neu_n=0,
        neg_n=0,
        confidence_mean=0.8,
        sufficient=n >= 5,
    )


def fake_api(*, empty=False, fail_path=None, chat_payload=None, suggestions=None):
    """Exercise the real HTTP client while replacing only its transport."""

    def request(method, url, *, params=None, json=None, timeout=None):
        path = urlparse(url).path
        status = 503 if path == fail_path else 200
        params = params or {}
        if path == "/sentiment/index":
            rows = [
                index_row(b, a, n=2 if params["window"] == "7d" else 100)
                for b in BANKS
                for a in ("ALL", "dividend_policy")
            ]
            if params["source"] == "*":
                rows += [index_row(b, source="earnings") for b in BANKS]
            payload = {"window": params["window"], "rows": [] if empty else rows}
            if not empty:
                payload["data_as_of"] = "2026-09-25"
        elif path == "/sentiment/series":
            labels = {
                "month": ("2026-07", "2026-09"),
                "quarter": ("2026-Q1", "2026-Q3"),
                "week": ("2025-W52", "2026-W02"),
            }[params["bucket"]]
            payload = {"series": [] if empty else [series_row(p) for p in labels]}
        elif path == "/analyst-consensus/latest":
            payload = {
                "rows": (
                    []
                    if empty
                    else [
                        dict(
                            bank=b,
                            as_of_date="2026-09-24" if b == "UOB" else "2026-09-25",
                            n_analysts=10,
                            recommendation_key="buy",
                            target_mean=40.0,
                            current_price=35.0,
                        )
                        for b in BANKS
                    ]
                )
            }
        elif path == "/evidence/latest":
            row = dict(
                sentence_id="s1",
                text="The dividend increased.",
                source="earnings",
                url="https://example.com/results",
                published_at="2026-09-25",
            )
            if "aspect" in params:
                row.update(aspect=params["aspect"], label="positive", confidence=0.9)
            payload = {"rows": [] if empty else [row]}
        elif path == "/suggestions":
            payload = {
                "suggestions": (
                    suggestions
                    if suggestions is not None
                    else [
                        {
                            "question": "What is the overall sentiment on DBS?",
                            "category": "overall",
                        },
                        {
                            "question": "What is the overall sentiment on OCBC?",
                            "category": "overall",
                        },
                    ]
                )
            }
        elif path == "/chat":
            payload = (
                chat_payload
                if chat_payload is not None
                else {
                    "question": json["message"],
                    "answer": f"Stored response for: {json['message']}",
                    "guard": None,
                    "citation_unverified": False,
                    "unverified_numbers": [],
                }
            )
        else:
            raise AssertionError(f"Unexpected request: {method} {path}")
        result = requests.Response()
        result.status_code = status
        result._content = jsonlib.dumps(payload).encode()
        return result

    return request


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        transport = patch(
            "dashboard.api_client.requests.request", side_effect=fake_api()
        )
        self.request = transport.start()
        self.addCleanup(transport.stop)

    def test_index_retains_windows_dates_model_and_volume_flags(self):
        frame = data.load_index()
        self.assertEqual(set(frame["window"]), {"7d", "30d", "all_time"})
        self.assertEqual(set(frame["data_as_of"]), {"2026-09-25"})
        self.assertEqual(set(frame["model_version"]), {"finbert-adapted-test"})
        self.assertTrue(frame.loc[frame["window"] == "7d", "insufficient_data"].all())
        self.assertFalse(frame.duplicated(["bank", "aspect", "window", "source"]).any())

    def test_source_breakdown_excludes_blended_and_topic_rows(self):
        frame = data.load_source_breakdown()
        self.assertEqual(len(frame), 3)
        self.assertEqual(set(frame["source"]), {"earnings"})
        self.assertEqual(set(frame["aspect"]), {"ALL"})

    def test_insufficient_source_score_is_hidden(self):
        with patch(
            "dashboard.data.request_json",
            return_value={
                "rows": [index_row(source="earnings", n=2)],
            },
        ):
            frame = data.load_source_breakdown()
        self.assertTrue(pd.isna(frame.iloc[0]["score"]))
        self.assertEqual(frame.iloc[0]["n"], 2)

    def test_evidence_overall_and_topic_contracts(self):
        overall = data.load_evidence("DBS", "ALL")
        self.assertNotIn("aspect", self.request.call_args.kwargs["params"])
        self.assertNotIn("label", overall.columns)
        topic = data.load_evidence("DBS", "dividend_policy")
        self.assertEqual(topic.iloc[0]["label"], "positive")
        self.assertEqual(
            self.request.call_args.kwargs["params"]["aspect"], "dividend_policy"
        )

    def test_consensus_keeps_each_banks_latest_date(self):
        frame = data.load_analyst_consensus().set_index("bank")
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame.loc["UOB", "as_of_date"], "2026-09-24")

    def test_series_inserts_missing_periods_including_iso_year_boundary(self):
        for bucket, missing in (
            ("month", "2026-08"),
            ("quarter", "2026-Q2"),
            ("week", "2026-W01"),
        ):
            with self.subTest(bucket=bucket):
                frame = data.load_time_series("DBS", "ALL", bucket)
                self.assertEqual(len(frame), 3)
                gap = frame.loc[frame["period"] == missing].iloc[0]
                self.assertEqual(gap["n"], 0)
                self.assertFalse(gap["sufficient"])
                self.assertTrue(pd.isna(gap["score"]))

    def test_empty_results_keep_usable_schemas_and_allow_missing_date(self):
        self.request.side_effect = fake_api(empty=True)
        for load in (
            data.load_index,
            data.load_source_breakdown,
            data.load_analyst_consensus,
            lambda: data.load_evidence("DBS", "ALL"),
            lambda: data.load_time_series("DBS", "ALL", "month"),
        ):
            frame = load()
            self.assertTrue(frame.empty)
            self.assertGreater(len(frame.columns), 0)

    def test_malformed_result_is_an_error_not_empty_data(self):
        for payload in ({}, {"rows": None}, {"rows": [{}]}):
            with self.subTest(payload=payload), patch(
                "dashboard.data.request_json", return_value=payload
            ):
                with self.assertRaises(ApiError):
                    data.load_analyst_consensus()

    def test_chart_paths_break_at_thin_periods_and_preserve_axis(self):
        frame = pd.DataFrame(
            [series_row("2026-07"), series_row("2026-08", n=2), series_row("2026-09")]
        )
        plotted = _plot_data(frame)
        self.assertTrue(pd.isna(plotted.iloc[1]["score"]))
        self.assertNotEqual(plotted.iloc[0]["_segment"], plotted.iloc[2]["_segment"])
        # Serialization validates the real Altair marks, channels and data.
        for chart in (area_chart(frame), trend_chart(frame.assign(bank="DBS"))):
            spec = chart.to_dict()
            self.assertEqual(
                spec["layer"][0]["encoding"]["detail"]["field"], "_segment"
            )
            self.assertEqual(
                spec["layer"][0]["encoding"]["x"]["scale"]["domain"],
                ["2026-07", "2026-08", "2026-09"],
            )
        self.assertEqual(frame.iloc[1]["score"], 0.1)  # raw evidence isn't mutated

    def test_sparkline_keeps_gaps(self):
        svg = sparkline([0.1, 0.2, None, 0.3, 0.4])
        self.assertEqual(svg.count("<polyline"), 2)


class DashboardAppTestCase(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"LOG_FILE": "none"})
        env.start()
        self.addCleanup(env.stop)
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        transport = patch(
            "dashboard.api_client.requests.request", side_effect=fake_api()
        )
        self.request = transport.start()
        self.addCleanup(transport.stop)
        database = patch(
            "sqlite3.connect", side_effect=AssertionError("Dashboard accessed SQLite")
        )
        self.database = database.start()
        self.addCleanup(database.stop)

    def page(self, name):
        app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=30)
        app.query_params["page"] = name
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app


class DashboardPageTests(DashboardAppTestCase):
    def test_four_data_pages_render_without_database_access(self):
        for name in ("Overview", "Topics", "Trends", "Evidence"):
            with self.subTest(page=name):
                st.cache_data.clear()
                app = self.page(name)
                self.assertFalse(app.error, [e.value for e in app.error])
                captions = " ".join(c.value for c in app.caption)
                self.assertIn("Data as of: 2026-09-25", captions)
                self.assertIn("Index computed: 2026-10-14 01:02 UTC", captions)
                self.assertNotIn("zero-shot", captions)
        self.database.assert_not_called()

    def test_trends_suppresses_insufficient_window_score(self):
        app = self.page("Trends")
        self.assertEqual(app.metric[0].value, "Too little data")
        self.assertIn("2026-09-25", " ".join(c.value for c in app.caption))

    def test_empty_database_shows_message_without_key_error(self):
        self.request.side_effect = fake_api(empty=True)
        app = self.page("Overview")
        self.assertTrue(app.warning)
        self.assertFalse(app.error)

    def test_failures_in_each_remaining_loader_show_service_error(self):
        cases = (
            ("Evidence", "/evidence/latest"),
            ("Trends", "/sentiment/series"),
            ("Overview", "/analyst-consensus/latest"),
            ("Overview", "/sentiment/index"),
        )
        for page, path in cases:
            with self.subTest(page=page, endpoint=path):
                st.cache_data.clear()
                self.request.side_effect = fake_api(fail_path=path)
                app = self.page(page)
                self.assertTrue(app.error)
                self.assertIn("HTTP 503", app.error[0].value)
