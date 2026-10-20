"""Manual-update UI through the real HTTP client, with a synthetic worker API.

No pipeline worker, model or project database is used by these tests.
"""

from collections import Counter
import copy
import json
from unittest.mock import patch
from urllib.parse import urlparse

import requests
import pytest

from dashboard import pipeline_client
from dashboard.api_client import ApiError
from test_dashboard_views import DashboardAppTestCase, fake_api

RUN_ID = "11111111111141118111111111111111"
STEP_NAMES = (
    ("preflight", "Check prerequisites"),
    ("import", "Import documents"),
    ("preprocess", "Prepare sentences"),
    ("assign", "Assign topics"),
    ("score", "Score sentiment"),
    ("aggregate", "Refresh sentiment index"),
)


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


def run_record(status="queued", sources=None):
    terminal = status in pipeline_client.TERMINAL
    return {
        "run_id": RUN_ID,
        "status": status,
        "sources": sources or ["earnings"],
        "started_at": "2026-10-18T06:00:00+00:00",
        "finished_at": "2026-10-18T06:02:00+00:00" if terminal else None,
        "model_version": "finbert-adapted-test" if terminal else None,
        "db_path": "/synthetic/data/plp.db",
        "log_path": "/synthetic/data/run/pipeline/run.log",
        "worker_log_path": "/synthetic/data/run/pipeline/run.worker.log",
        "current_stage": "aggregate" if terminal else "preflight",
        "imported_documents": (
            [{"doc_id": "new-document", "source": "earnings"}] if terminal else []
        ),
        "warnings": [],
        "error": None,
        "stages": [
            {
                "key": key,
                "label": label,
                "status": "completed" if terminal else "pending",
                "metrics": (
                    {"documents_inserted": 1} if key == "import" and terminal else {}
                ),
                "files": (
                    [
                        {
                            "source": "earnings",
                            "file": "DBS/results.pdf",
                            "status": "already_stored",
                        }
                    ]
                    if key == "import" and terminal
                    else []
                ),
                "error": None,
            }
            for key, label in STEP_NAMES
        ],
    }


class PipelineAPI:
    def __init__(self, **base_options):
        self.base = fake_api(**base_options)
        self.runs = []
        self.posts = []
        self.gets = Counter()
        self.missing = set()
        self.counts = {
            "earnings": 182,
            "sgx_research": 25,
            "google_news": 0,
            "arctic_shift": 0,
        }
        self.failure = None
        self.history_status = 200
        self.sources_status = 200
        self.updated = False

    def finish(self, status="completed"):
        window = self.runs[0].get("collection_window")
        self.runs = [run_record(status, self.runs[0]["sources"])]
        self.runs[0]["collection_window"] = window
        self.updated = True

    def __call__(self, method, url, *, params=None, json=None, timeout=None):
        path = urlparse(url).path
        if method == "GET":
            self.gets[path] += 1
        if path == "/pipeline/sources":
            return response(
                {
                    "sources": [
                        {
                            "key": key,
                            "label": label,
                            "kind": (
                                "online"
                                if key in pipeline_client.ONLINE_SOURCES
                                else "local_pdf"
                            ),
                            "folder": f"/synthetic/data/{key}",
                            "exists": key not in self.missing,
                            "pdf_count": self.counts[key],
                        }
                        for key, label in pipeline_client.SOURCES.items()
                    ]
                },
                self.sources_status,
            )
        if path == "/pipeline/runs" and method == "GET":
            active = next(
                (
                    run["run_id"]
                    for run in self.runs
                    if run["status"] in pipeline_client.ACTIVE
                ),
                None,
            )
            return response(
                {"runs": copy.deepcopy(self.runs), "active_run_id": active},
                self.history_status,
            )
        if path == "/pipeline/runs" and method == "POST":
            self.posts.append(json)
            if self.failure == "conflict":
                self.runs = [run_record("running", ["sgx_research"])]
                return response({"detail": "Another run is active"}, 409)
            self.runs = [run_record(sources=json["sources"])]
            if "since" in json:
                self.runs[0]["collection_window"] = {
                    "since": json["since"],
                    "until": json["until"],
                }
            if self.failure == "timeout":
                raise requests.Timeout(
                    "The worker accepted the run but the response was lost"
                )
            if self.failure == "unavailable":
                self.runs = [run_record("failed", json["sources"])]
                self.runs[0]["error"] = "Cannot launch pipeline worker"
                return response({"detail": "Worker launch failed"}, 503)
            return response({"run": copy.deepcopy(self.runs[0])}, 202)
        if path.startswith("/pipeline/runs/"):
            return response(
                {
                    "run": copy.deepcopy(
                        next(
                            run
                            for run in self.runs
                            if run["run_id"] == path.rsplit("/", 1)[1]
                        )
                    )
                }
            )
        result = self.base(method, url, params=params, json=json, timeout=timeout)
        if self.updated and path == "/sentiment/index":
            payload = result.json()
            payload["data_as_of"] = "2026-10-18"
            for row in payload["rows"]:
                row["computed_at"] = "2026-10-18T06:02:00+00:00"
                row["score"] = 0.3
            return response(payload)
        return result


class DashboardPipelineTests(DashboardAppTestCase):
    def setUp(self):
        super().setUp()
        self.api = PipelineAPI()
        self.request.side_effect = self.api

    def test_explicit_selection_posts_once_and_polling_or_navigation_never_reposts(
        self,
    ):
        app = self.page("Data Management")
        self.assertTrue(app.button(key="pipeline_start").disabled)
        self.assertFalse(self.api.posts)
        app.checkbox(key="pipeline_select_sgx_research").check().run()
        app.button(key="pipeline_start").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.api.posts, [{"sources": ["sgx_research"]}])
        self.assertTrue(app.button(key="pipeline_start").disabled)
        self.assertTrue(app.checkbox(key="pipeline_select_earnings").disabled)
        app.run()
        app.sidebar.radio(key="nav").set_value("Overview").run()
        self.assertTrue(any("update in progress" in item.value for item in app.info))
        app.sidebar.radio(key="nav").set_value("Data Management").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.api.posts), 1)
        self.database.assert_not_called()

    def test_both_sources_and_reopening_page_follow_saved_run(self):
        app = self.page("Data Management")
        for key in ("earnings", "sgx_research"):
            app.checkbox(key=f"pipeline_select_{key}").check().run()
        app.button(key="pipeline_start").click().run()
        self.assertEqual(self.api.posts, [{"sources": ["earnings", "sgx_research"]}])
        reopened = self.page("Data Management")
        self.assertTrue(reopened.button(key="pipeline_start").disabled)
        self.assertEqual(reopened.selectbox(key="pipeline_focus").value, RUN_ID)
        self.assertEqual(len(self.api.posts), 1)

    def test_history_and_run_times_use_singapore_time_including_date_rollover(self):
        for start, finish in (
            ("2026-10-18T18:00:00+00:00", "2026-10-18T18:02:00+00:00"),
            ("2026-10-19T02:00:00+08:00", "2026-10-19T02:02:00+08:00"),
        ):
            with self.subTest(start=start):
                run = run_record("completed")
                run.update(started_at=start, finished_at=finish)
                self.api.runs = [run]
                app = self.page("Data Management")
                self.assertFalse(app.exception)
                self.assertIn(
                    "19 Oct · 02:00 SGT",
                    app.selectbox(key="pipeline_focus").options[0],
                )
                header = next(
                    item.value
                    for item in app.markdown
                    if 'class="pipeline-run-header"' in item.value
                )
                self.assertIn("19 Oct 2026, 02:00 SGT", header)
                self.assertIn("19 Oct 2026, 02:02 SGT", header)
                self.assertEqual(self.api.runs[0]["started_at"], start)
                self.assertFalse(self.api.posts)

    def test_all_pdf_sources_selects_both_and_stays_in_sync_with_individual_choices(
        self,
    ):
        app = self.page("Data Management")
        app.checkbox(key="pipeline_all_sources").check().run()
        self.assertTrue(
            all(
                app.checkbox(key=f"pipeline_select_{key}").value
                for key in pipeline_client.SOURCES
            )
        )
        app.checkbox(key="pipeline_select_sgx_research").uncheck().run()
        self.assertFalse(app.checkbox(key="pipeline_all_sources").value)
        app.checkbox(key="pipeline_all_sources").check().run()
        app.checkbox(key="pipeline_all_sources").uncheck().run()
        self.assertTrue(app.button(key="pipeline_start").disabled)
        app.checkbox(key="pipeline_all_sources").check().run()
        app.button(key="pipeline_start").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.api.posts[0]["sources"], list(pipeline_client.SOURCES))
        self.assertIn("since", self.api.posts[0])
        self.assertIn("until", self.api.posts[0])
        self.assertTrue(app.checkbox(key="pipeline_all_sources").disabled)
        self.api.finish()
        app.run()
        self.assertTrue(app.checkbox(key="pipeline_all_sources").value)
        self.assertTrue(
            all(
                app.checkbox(key=f"pipeline_select_{key}").value
                for key in pipeline_client.SOURCES
            )
        )

    def test_missing_folder_cannot_be_selected_but_empty_folder_can_resume_pending_work(
        self,
    ):
        self.api.missing.add("earnings")
        self.api.counts["sgx_research"] = 0
        app = self.page("Data Management")
        self.assertTrue(app.checkbox(key="pipeline_select_earnings").disabled)
        self.assertFalse(app.checkbox(key="pipeline_all_sources").disabled)
        self.assertFalse(app.checkbox(key="pipeline_select_sgx_research").disabled)
        app.checkbox(key="pipeline_select_sgx_research").check().run()
        self.assertFalse(app.button(key="pipeline_start").disabled)

    def test_empty_or_unavailable_index_does_not_block_data_management(self):
        for options in ({"empty": True}, {"fail_path": "/sentiment/index"}):
            with self.subTest(options=options):
                import streamlit as st

                st.cache_data.clear()
                self.api.base = fake_api(**options)
                app = self.page("Data Management")
                app.checkbox(key="pipeline_select_earnings").check().run()
                self.assertFalse(app.button(key="pipeline_start").disabled)

    def test_history_or_source_failure_blocks_start_and_recovers_without_post(self):
        for attribute in ("history_status", "sources_status"):
            with self.subTest(endpoint=attribute):
                setattr(self.api, attribute, 503)
                app = self.page("Data Management")
                self.assertTrue(app.button(key="pipeline_start").disabled)
                self.assertTrue(app.error)
                setattr(self.api, attribute, 200)
                app.run()
                self.assertFalse(app.exception)
                self.assertFalse(self.api.posts)

    def test_conflict_and_lost_response_require_status_check_without_automatic_retry(
        self,
    ):
        for failure in ("conflict", "timeout", "unavailable"):
            with self.subTest(failure=failure):
                self.api.runs = []
                self.api.posts = []
                self.api.failure = failure
                app = self.page("Data Management")
                app.checkbox(key="pipeline_select_earnings").check().run()
                app.button(key="pipeline_start").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(len(self.api.posts), 1)
                self.assertTrue(app.button(key="pipeline_start").disabled)
                self.assertTrue(app.warning)
                app.run()
                app.button(key="pipeline_check_status").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(len(self.api.posts), 1)
                self.assertEqual(
                    app.button(key="pipeline_start").disabled, failure != "unavailable"
                )

    def test_completion_refreshes_all_cached_views_and_retains_conversation(self):
        app = self.page("Overview")
        for name in ("Evidence", "Trends", "Ask", "Data Management"):
            app.sidebar.radio(key="nav").set_value(name).run()
        before = self.api.gets.copy()
        app.session_state["api_chat_history"] = [
            {"role": "user", "content": "Keep my conversation"}
        ]
        app.checkbox(key="pipeline_select_earnings").check().run()
        app.button(key="pipeline_start").click().run()
        self.api.finish()
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        self.assertEqual(
            app.session_state["api_chat_history"][0]["content"], "Keep my conversation"
        )
        for name in ("Overview", "Evidence", "Trends", "Ask"):
            app.sidebar.radio(key="nav").set_value(name).run()
            self.assertFalse(app.exception)
        self.assertIn("18 Oct 2026", " ".join(item.value for item in app.markdown))
        for path in (
            "/sentiment/index",
            "/evidence/latest",
            "/sentiment/trend",
            "/sentiment/series",
            "/suggestions",
            "/analyst-consensus/latest",
        ):
            self.assertGreater(self.api.gets[path], before[path], path)
        self.assertEqual(len(self.api.posts), 1)

    def test_terminal_warnings_failures_and_imported_files_are_visible(self):
        for status in ("completed_with_warnings", "failed", "interrupted"):
            with self.subTest(status=status):
                run = run_record(status)
                run["warnings"] = [
                    {
                        "stage": "import",
                        "file": "report.pdf",
                        "message": "No usable prose",
                    }
                ]
                if status in {"failed", "interrupted"}:
                    run["stages"][2].update(
                        status=status, error="Topic model unavailable"
                    )
                    run["error"] = "Topic model unavailable"
                self.api.runs = [run]
                app = self.page("Data Management")
                self.assertTrue(
                    app.warning if status == "completed_with_warnings" else app.error
                )
                self.assertEqual(app.metric[0].value, "1")
                self.assertTrue(
                    any(item.label == "Warnings (1)" for item in app.expander)
                )
                self.assertFalse(self.api.posts)

    def test_missing_english_model_shows_setup_fix_and_no_zero_metric_cards(self):
        run = run_record("failed")
        run["error"] = "RuntimeError: Missing dependencies: en_core_web_sm"
        run["imported_documents"] = []
        run["current_stage"] = "preflight"
        for stage in run["stages"]:
            stage.update(status="pending", files=[], metrics={})
        run["stages"][0]["status"] = "failed"
        self.api.runs = [run]
        app = self.page("Data Management")
        self.assertIn("Setup check failed. Import did not start.", app.error[0].value)
        self.assertTrue(
            any("-m spacy download en_core_web_sm" in block.value for block in app.code)
        )
        self.assertFalse(app.metric)
        self.assertFalse(self.api.posts)

    def test_online_only_selection_posts_inclusive_ui_dates_once(self):
        from datetime import date

        app = self.page("Data Management")
        app.checkbox(key="pipeline_select_google_news").check().run()
        app.date_input(key="pipeline_since").set_value(date(2024, 5, 1)).run()
        app.date_input(key="pipeline_through").set_value(date(2024, 5, 2)).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.button(key="pipeline_start").disabled)
        app.button(key="pipeline_start").click().run()
        self.assertEqual(
            self.api.posts,
            [
                {
                    "sources": ["google_news"],
                    "since": "2024-05-01",
                    "until": "2024-05-03",
                }
            ],
        )
        app.run()
        self.assertEqual(len(self.api.posts), 1)
        self.api.finish()
        app.run()
        self.assertEqual(app.date_input(key="pipeline_since").value, date(2024, 5, 1))
        self.assertEqual(app.date_input(key="pipeline_through").value, date(2024, 5, 2))

    def test_invalid_online_dates_disable_submit_and_pdf_only_drops_dates(self):
        from datetime import date

        app = self.page("Data Management")
        app.checkbox(key="pipeline_select_arctic_shift").check().run()
        app.date_input(key="pipeline_since").set_value(date(2024, 5, 1)).run()
        app.date_input(key="pipeline_through").set_value(date(2024, 6, 2)).run()
        self.assertTrue(app.button(key="pipeline_start").disabled)
        self.assertTrue(app.error)
        app.checkbox(key="pipeline_select_arctic_shift").uncheck().run()
        app.checkbox(key="pipeline_select_earnings").check().run()
        app.button(key="pipeline_start").click().run()
        self.assertEqual(self.api.posts, [{"sources": ["earnings"]}])

    def test_all_available_sources_skips_a_missing_pdf_folder(self):
        self.api.missing.add("earnings")
        app = self.page("Data Management")
        app.checkbox(key="pipeline_all_sources").check().run()
        self.assertFalse(app.checkbox(key="pipeline_select_earnings").value)
        app.button(key="pipeline_start").click().run()
        self.assertEqual(
            self.api.posts[0]["sources"],
            ["sgx_research", "google_news", "arctic_shift"],
        )

    def test_collection_failures_and_duplicate_counts_are_visible(self):
        run = run_record("completed_with_warnings", ["google_news", "arctic_shift"])
        run["source_results"] = {
            "google_news": {
                "status": "failed",
                "fetched": 0,
                "documents_inserted": 0,
                "duplicates": 0,
                "filtered": 0,
            },
            "arctic_shift": {
                "status": "partial",
                "fetched": 20,
                "documents_inserted": 5,
                "duplicates": 15,
                "filtered": 0,
            },
        }
        run["warnings"] = [
            {"source": "google_news", "message": "Window request failed"}
        ]
        run["stages"][1]["files"] = []
        self.api.runs = [run]
        app = self.page("Data Management")
        self.assertFalse(app.exception)
        results = app.dataframe[0].value
        self.assertEqual(results["Status"].tolist(), ["Failed", "Incomplete"])
        self.assertEqual(app.metric[1].label, "Duplicates skipped")
        self.assertEqual(app.metric[1].value, "15")
        self.assertTrue(app.warning)


def test_pipeline_http_errors_retain_status_without_backend_details():
    with patch(
        "dashboard.api_client.requests.request",
        return_value=response({"detail": "private worker traceback"}, 409),
    ):
        with pytest.raises(ApiError) as caught:
            pipeline_client.start_run(["earnings"])
    assert caught.value.status_code == 409
    assert "traceback" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"runs": []},
        {"runs": [{}], "active_run_id": None},
        {"runs": [], "active_run_id": RUN_ID},
    ],
)
def test_malformed_history_cannot_be_treated_as_idle(payload):
    with patch("dashboard.pipeline_client.request_json", return_value=payload):
        with pytest.raises(ApiError):
            pipeline_client.load_history()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "sources": [
                {
                    "key": "earnings",
                    "label": "Bank earnings PDFs",
                    "folder": "/data/earnings",
                    "exists": True,
                    "pdf_count": 1,
                }
            ]
        },
        {"sources": []},
    ],
)
def test_source_version_mismatch_explains_that_both_services_need_restarting(payload):
    with patch("dashboard.pipeline_client.request_json", return_value=payload):
        with pytest.raises(ApiError, match="Restart both services"):
            pipeline_client.load_sources()
