"""Chat adapter and Ask-page behaviour, without model/database calls."""

from copy import deepcopy
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import requests

from dashboard import chat, data
from dashboard.api_client import ApiError
from test_dashboard_views import DashboardAppTestCase, fake_api

VALID_ANSWER = {
    "answer": "Stored sentiment is slightly positive.",
    "guard": None,
    "citation_unverified": False,
    "unverified_numbers": [],
}


class ChatAdapterTests(unittest.TestCase):
    def test_configuration_status_is_loaded_only_from_fastapi(self):
        payload = {"configured": True, "problem": None}
        with patch("dashboard.chat.request_json", return_value=payload) as request:
            self.assertEqual(chat.load_chat_status(), payload)
        request.assert_called_once_with("GET", "/chat/status", read_timeout=5)

    def test_invalid_configuration_status_does_not_enable_chat(self):
        for payload in ({}, {"configured": "true"}, {"configured": False},
                        {"configured": True, "problem": {}},
                        {"configured": False, "problem": {"code": "missing", "message": " "}}):
            with self.subTest(payload=payload), patch("dashboard.chat.request_json", return_value=payload):
                with self.assertRaisesRegex(ApiError, "invalid chatbot status"):
                    chat.load_chat_status()

    def test_request_separates_new_question_and_strips_display_metadata(self):
        history = [
            {"role": "user", "content": "DBS dividends?"},
            {
                "role": "assistant",
                "content": "Here is the stored score.",
                "guard": None,
                "citation_unverified": True,
                "unverified_numbers": [0.5],
                "unverified_readings": ["neutral"],
            },
        ]
        original = deepcopy(history)
        with patch("dashboard.chat.request_json", return_value=VALID_ANSWER) as request:
            self.assertEqual(chat.send_chat("And OCBC?", history), VALID_ANSWER)
        request.assert_called_once_with(
            "POST",
            "/chat",
            body={
                "message": "And OCBC?",
                "history": [
                    {"role": "user", "content": "DBS dividends?"},
                    {"role": "assistant", "content": "Here is the stored score."},
                ],
            },
            read_timeout=600,
        )
        self.assertEqual(history, original)

    def test_malformed_chat_cannot_be_treated_as_a_verified_answer(self):
        invalid_answers = [
            {},
            {**VALID_ANSWER, "answer": " "},
            {**VALID_ANSWER, "answer": None},
            {**VALID_ANSWER, "citation_unverified": None},
            {**VALID_ANSWER, "citation_unverified": "false"},
            {**VALID_ANSWER, "unverified_numbers": None},
            {**VALID_ANSWER, "unverified_readings": None},
            {**VALID_ANSWER, "unverified_readings": "neutral"},
            {**VALID_ANSWER, "unverified_readings": [1]},
            {**VALID_ANSWER, "guard": []},
        ]
        for payload in invalid_answers:
            with self.subTest(payload=payload), patch(
                "dashboard.chat.request_json", return_value=payload
            ):
                with self.assertRaises(ApiError):
                    chat.send_chat("DBS?", [])

    def test_suggestions_use_api_limit_and_allow_empty_list(self):
        for suggestions in (
            [],
            [{"question": "How is DBS doing?", "category": "overall"}],
        ):
            with self.subTest(suggestions=suggestions), patch(
                "dashboard.data.request_json",
                return_value={"suggestions": suggestions},
            ) as request:
                self.assertEqual(data.load_suggestions(limit=4), suggestions)
                request.assert_called_once_with(
                    "GET", "/suggestions", params={"limit": 4}
                )

    def test_invalid_suggestions_raise_service_error(self):
        for payload in (
            {},
            {"suggestions": None},
            {"suggestions": [{}]},
            {"suggestions": [{"question": " "}]},
        ):
            with self.subTest(payload=payload), patch(
                "dashboard.data.request_json", return_value=payload
            ):
                with self.assertRaises(ApiError):
                    data.load_suggestions()


class ChatPageTests(DashboardAppTestCase):
    MISSING_KEY = {
        "configured": False,
        "problem": {
            "code": "openai_key_missing",
            "message": "Chatbot unavailable: API access has not been configured.",
            "setup_hint": "Set OPENAI_API_KEY in the API server's .env, then restart the API.",
        },
    }

    def test_missing_key_disables_input_and_suggestions_without_asking_for_a_secret(self):
        self.request.side_effect = fake_api(chat_status=self.MISSING_KEY)
        app = self.page("Ask")
        self.assertTrue(app.chat_input[0].disabled)
        self.assertIn("not been configured", app.warning[0].value)
        self.assertTrue(all(b.disabled for b in app.button if b.label.startswith("What is the overall")))
        self.assertIn("Administrator setup", [e.label for e in app.expander])
        self.assertIn("OPENAI_API_KEY", " ".join(m.value for m in app.markdown))
        self.assertEqual(len(app.text_input), 0)
        self.assertEqual(self.chat_calls(), [])

    def test_missing_credentials_preserve_history_and_other_tabs_and_recover(self):
        app = self.page("Ask")
        self.ask(app, "DBS?")
        original = deepcopy(app.session_state["api_chat_history"])
        self.request.side_effect = fake_api(chat_status=self.MISSING_KEY)
        app.run()
        self.assertTrue(app.chat_input[0].disabled)
        self.assertEqual(app.session_state["api_chat_history"], original)
        self.assertEqual(len(app.chat_message), 2)
        for page in ("Overview", "Topics", "Trends", "Evidence"):
            app.radio(key="nav").set_value(page).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
        self.request.side_effect = fake_api()
        app.radio(key="nav").set_value("Ask").run()
        self.assertFalse(app.chat_input[0].disabled)
        self.assertEqual(len(self.chat_calls()), 1)
        self.ask(app, "And OCBC?")
        self.assertEqual(self.chat_calls()[-1].kwargs["json"]["history"],
                         [{"role": r["role"], "content": r["content"]} for r in original])

    def test_status_failure_disables_chat_without_posting(self):
        self.request.side_effect = fake_api(fail_path="/chat/status")
        app = self.page("Ask")
        self.assertTrue(app.chat_input[0].disabled)
        self.assertIn("availability could not be checked", app.warning[0].value)
        self.assertEqual(self.chat_calls(), [])

    def test_pending_question_is_kept_if_configuration_disappears_before_rerun(self):
        app = self.page("Ask")
        self.request.side_effect = fake_api(chat_status=self.MISSING_KEY)
        app.session_state["api_chat_pending"] = "And OCBC?"
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["api_chat_failure"]["question"], "And OCBC?")
        self.assertEqual(app.session_state["api_chat_history"], [])
        self.assertEqual(self.chat_calls(), [])

    def test_rejected_key_has_setup_guidance_and_keeps_prior_history(self):
        app = self.page("Ask")
        self.ask(app, "DBS?")
        original = deepcopy(app.session_state["api_chat_history"])
        normal_request = fake_api()

        def reject_chat(method, url, **kwargs):
            if urlparse(url).path == "/chat":
                result = requests.Response()
                result.status_code = 503
                import json
                result._content = json.dumps({"detail": {
                    "code": "openai_key_rejected", "message": "The chatbot's API key was rejected.",
                    "setup_hint": "Check OPENAI_API_KEY on the API server, then restart the API.",
                }}).encode()
                return result
            return normal_request(method, url, **kwargs)

        self.request.side_effect = reject_chat
        self.ask(app, "And OCBC?")
        self.assertIn("key was rejected", app.error[0].value)
        self.assertNotIn("HTTP 503", app.error[0].value)
        self.assertIn("Administrator setup", [e.label for e in app.expander])
        self.assertEqual(app.session_state["api_chat_history"], original)
        app.run()
        self.assertEqual(len(self.chat_calls()), 2)

    def chat_calls(self):
        return [call for call in self.request.call_args_list if call.args[0] == "POST"]

    def ask(self, app, question):
        app.chat_input[0].set_value(question).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_follow_up_sends_prior_pair_once_and_rerun_does_not_generate(self):
        app = self.page("Ask")
        self.ask(app, "How is DBS doing?")
        first = self.chat_calls()[0]
        self.assertEqual(
            first.kwargs["json"], {"message": "How is DBS doing?", "history": []}
        )
        self.ask(app, "And OCBC?")
        self.assertEqual(
            self.chat_calls()[1].kwargs["json"],
            {
                "message": "And OCBC?",
                "history": [
                    {"role": "user", "content": "How is DBS doing?"},
                    {
                        "role": "assistant",
                        "content": "Stored response for: How is DBS doing?",
                    },
                ],
            },
        )
        self.assertEqual(len(app.session_state["api_chat_history"]), 4)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.chat_calls()), 2)
        self.assertEqual(len(app.chat_message), 4)
        self.database.assert_not_called()

    def test_suggestion_click_sends_question(self):
        app = self.page("Ask")
        question = "What is the overall sentiment on DBS?"
        next(button for button in app.button if button.label == question).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(
            self.chat_calls()[0].kwargs["json"], {"message": question, "history": []}
        )
        app.run()
        self.assertEqual(len(self.chat_calls()), 1)

    def test_brand_navigation_preserves_chat_and_theme(self):
        app = self.page("Ask")
        self.ask(app, "DBS?")
        app.toggle(key="dark_mode").set_value(True).run()
        history = deepcopy(app.session_state["api_chat_history"])
        app.button(key="brand_home").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.sidebar.radio(key="nav").value, "Overview")
        self.assertEqual(app.query_params["page"], "Overview")
        self.assertEqual(app.query_params["theme"], "dark")
        self.assertTrue(app.toggle(key="dark_mode").value)
        self.assertEqual(app.session_state["api_chat_history"], history)
        app.sidebar.radio(key="nav").set_value("Ask").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.chat_message), 2)
        self.assertEqual(len(self.chat_calls()), 1)

    def test_flags_survive_navigation_and_clear_removes_history_and_flags(self):
        self.request.side_effect = fake_api(
            chat_payload={
                **VALID_ANSWER,
                "citation_unverified": True,
                "unverified_numbers": [0.5],
                "unverified_readings": ["neutral"],
            }
        )
        app = self.page("Ask")
        self.ask(app, "DBS?")
        self.assertEqual(len(app.warning), 3)
        self.assertIn("0.5", app.warning[1].value)
        self.assertIn("neutral", app.warning[2].value)
        app.radio(key="nav").set_value("Topics").run()
        app.radio(key="nav").set_value("Ask").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.warning), 3)
        self.assertEqual(len(self.chat_calls()), 1)
        app.button(key="clear_chat").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["api_chat_history"], [])
        self.assertEqual(len(app.chat_message), 0)
        self.assertEqual(len(app.warning), 0)
        self.ask(app, "OCBC?")
        self.assertEqual(self.chat_calls()[-1].kwargs["json"]["history"], [])

    def test_guard_response_has_readable_type(self):
        self.request.side_effect = fake_api(
            chat_payload={**VALID_ANSWER, "guard": "advice"}
        )
        app = self.page("Ask")
        self.ask(app, "Should I buy DBS?")
        self.assertIn(
            "Response type: Investment advice request", [c.value for c in app.caption]
        )
        app.run()
        self.assertIn(
            "Response type: Investment advice request", [c.value for c in app.caption]
        )

    def test_clear_is_available_immediately_after_first_answer(self):
        app = self.page("Ask")
        self.assertTrue(app.button(key="clear_chat").disabled)
        self.ask(app, "DBS?")
        self.assertFalse(app.button(key="clear_chat").disabled)
        app.button(key="clear_chat").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["api_chat_history"], [])
        self.assertEqual(len(app.chat_message), 0)

    def test_failed_request_does_not_contaminate_follow_up_history(self):
        self.request.side_effect = fake_api(fail_path="/chat")
        app = self.page("Ask")
        self.ask(app, "DBS?")
        self.assertTrue(app.error)
        self.assertIn("HTTP 503", app.error[0].value)
        self.assertEqual(app.session_state["api_chat_history"], [])
        self.assertFalse(app.chat_input[0].disabled)
        self.request.side_effect = fake_api()
        self.ask(app, "OCBC?")
        self.assertFalse(app.error)
        self.assertEqual(self.chat_calls()[-1].kwargs["json"]["history"], [])

    def test_clear_removes_failed_turn_and_does_not_retry(self):
        self.request.side_effect = fake_api(fail_path="/chat")
        app = self.page("Ask")
        self.ask(app, "DBS?")
        app.run()
        self.assertEqual(len(self.chat_calls()), 1)
        self.assertTrue(app.error)
        app.button(key="clear_chat").click().run()
        self.assertFalse(app.error)
        self.assertEqual(len(app.chat_message), 0)
        self.assertEqual(app.session_state["api_chat_history"], [])
        self.assertEqual(len(self.chat_calls()), 1)

    def test_suggestion_failure_leaves_typed_chat_available(self):
        self.request.side_effect = fake_api(fail_path="/suggestions")
        app = self.page("Ask")
        self.assertIn("Suggested questions are unavailable", app.warning[0].value)
        self.ask(app, "How is DBS doing?")
        self.assertEqual(len(self.chat_calls()), 1)
        self.assertEqual(len(app.session_state["api_chat_history"]), 2)
        self.assertFalse(app.error)

    def test_empty_suggestions_leave_typed_chat_available(self):
        self.request.side_effect = fake_api(suggestions=[])
        app = self.page("Ask")
        self.assertFalse(app.warning)
        self.ask(app, "DBS?")
        self.assertEqual(len(self.chat_calls()), 1)

    def test_chat_timeout_is_not_retried_or_saved(self):
        normal_request = fake_api()

        def timeout_chat(method, url, **kwargs):
            if urlparse(url).path == "/chat":
                raise requests.Timeout("model is slow")
            return normal_request(method, url, **kwargs)

        self.request.side_effect = timeout_chat
        app = self.page("Ask")
        self.ask(app, "DBS?")
        self.assertIn("timed out", app.error[0].value)
        self.assertEqual(len(self.chat_calls()), 1)
        self.assertEqual(app.session_state["api_chat_history"], [])
        app.run()
        self.assertEqual(len(self.chat_calls()), 1)

    def test_malformed_answer_is_not_added_to_history(self):
        self.request.side_effect = fake_api(
            chat_payload={"answer": "An answer missing verification fields"}
        )
        app = self.page("Ask")
        self.ask(app, "DBS?")
        self.assertIn("invalid chat response", app.error[0].value)
        self.assertEqual(app.session_state["api_chat_history"], [])

    def test_sessions_have_separate_history(self):
        first = self.page("Ask")
        self.ask(first, "DBS?")
        second = self.page("Ask")
        self.assertEqual(second.session_state["api_chat_history"], [])
        self.ask(second, "OCBC?")
        self.assertEqual(self.chat_calls()[-1].kwargs["json"]["history"], [])
        self.assertEqual(first.session_state["api_chat_history"][0]["content"], "DBS?")

    def test_whitespace_does_not_generate_answer(self):
        app = self.page("Ask")
        self.ask(app, "   ")
        self.assertEqual(len(self.chat_calls()), 0)
        self.assertEqual(app.session_state["api_chat_history"], [])
