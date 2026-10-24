"""HTTP boundary tests, independent of the database and NLP model fixtures.

Run with only requests and python-dotenv installed:
    python -m unittest discover -s tests -p test_dashboard_api_client.py -v
"""

import json
import os
import unittest
from unittest.mock import patch

import requests

from dashboard.api_client import ApiError, request_json


def response(status, payload):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode("utf-8")
    result.headers["Content-Type"] = "application/json"
    return result


class ApiClientTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"PLP_API_URL": "", "PLP_API_PORT": "8000"})
        env.start()
        self.addCleanup(env.stop)
        transport = patch("dashboard.api_client.requests.request")
        self.request = transport.start()
        self.addCleanup(transport.stop)
        self.request.return_value = response(200, {"rows": []})

    def test_local_url_and_query_parameters(self):
        request_json("GET", "/sentiment/index", params={"window": "30d", "source": "*"})
        self.request.assert_called_once_with(
            "GET", "http://127.0.0.1:8000/sentiment/index",
            params={"window": "30d", "source": "*"}, json=None, timeout=(5, 30),
        )

    def test_custom_port_and_docker_url(self):
        with patch.dict(os.environ, {"PLP_API_PORT": "8100"}):
            request_json("GET", "/health")
            self.assertEqual(self.request.call_args.args[1], "http://127.0.0.1:8100/health")
            with patch.dict(os.environ, {"PLP_API_URL": "http://api:8000/"}):
                request_json("GET", "health")
                self.assertEqual(self.request.call_args.args[1], "http://api:8000/health")

    def test_empty_results_keep_metadata(self):
        payload = {"window": "30d", "data_as_of": "2026-09-25", "rows": []}
        self.request.return_value = response(200, payload)
        self.assertEqual(request_json("GET", "/sentiment/index"), payload)

    def test_chat_keeps_history_and_verification_flags(self):
        body = {
            "message": "And OCBC?",
            "history": [{"role": "user", "content": "How is DBS doing?"},
                        {"role": "assistant", "content": "Here is the stored score."}],
        }
        payload = {"answer": "OCBC's answer", "citation_unverified": True,
                   "unverified_numbers": [0.5]}
        self.request.return_value = response(200, payload)
        self.assertEqual(request_json("POST", "/chat", body=body, read_timeout=600), payload)
        self.request.assert_called_once_with(
            "POST", "http://127.0.0.1:8000/chat",
            params=None, json=body, timeout=(5, 600),
        )
        self.assertEqual(len(body["history"]), 2)

    def test_connection_failure_is_an_error_not_empty_data(self):
        self.request.side_effect = requests.ConnectionError("offline")
        with self.assertRaisesRegex(ApiError, "Cannot connect"):
            request_json("GET", "/sentiment/index")

    def test_timed_out_chat_is_not_retried(self):
        self.request.side_effect = requests.Timeout("answer may still be generating")
        with self.assertRaisesRegex(ApiError, "timed out"):
            request_json("POST", "/chat", body={"message": "Hello"}, read_timeout=600)
        self.assertEqual(self.request.call_count, 1)

    def test_http_error_includes_status_without_exposing_backend_details(self):
        self.request.return_value = response(503, {"detail": "private backend detail"})
        with self.assertRaisesRegex(ApiError, "HTTP 503 for /chat") as caught:
            request_json("POST", "/chat", body={"message": "Hello"})
        self.assertNotIn("private backend detail", str(caught.exception))

    def test_structured_chat_service_error_preserves_safe_message_and_setup_hint(self):
        self.request.return_value = response(503, {"detail": {
            "code": "openai_key_missing", "message": "Chatbot access is not configured.",
            "setup_hint": "Set OPENAI_API_KEY on the API server.",
        }})
        with self.assertRaisesRegex(ApiError, "not configured") as caught:
            request_json("POST", "/chat", body={"message": "DBS?"})
        self.assertEqual(caught.exception.error_code, "openai_key_missing")
        self.assertEqual(caught.exception.setup_hint, "Set OPENAI_API_KEY on the API server.")
        self.assertEqual(caught.exception.status_code, 503)

    def test_unstructured_or_malformed_service_error_keeps_generic_http_message(self):
        for payload in ({"detail": "private upstream text"}, [],
                        {"detail": {"code": 5, "message": "private upstream text"}},
                        {"detail": {"code": "bad", "message": "private upstream text", "setup_hint": []}}):
            with self.subTest(payload=payload):
                self.request.return_value = response(503, payload)
                with self.assertRaisesRegex(ApiError, "HTTP 503") as caught:
                    request_json("POST", "/chat", body={"message": "DBS?"})
                self.assertNotIn("private upstream text", str(caught.exception))

    def test_other_transport_errors_are_wrapped(self):
        self.request.side_effect = requests.RequestException("transport failed")
        with self.assertRaisesRegex(ApiError, "API request failed"):
            request_json("GET", "/health")

    def test_http_error_without_response_is_wrapped(self):
        self.request.side_effect = requests.HTTPError("no attached response")
        with self.assertRaisesRegex(ApiError, "HTTP error for /chat"):
            request_json("POST", "/chat", body={"message": "Hello"})

    def test_invalid_json_is_an_error(self):
        self.request.return_value._content = b"<html>Not an API response</html>"
        with self.assertRaisesRegex(ApiError, "invalid JSON"):
            request_json("GET", "/sentiment/index")

    def test_unexpected_json_shape_is_an_error(self):
        for payload in ([], None, "not an object"):
            with self.subTest(payload=payload):
                self.request.return_value = response(200, payload)
                with self.assertRaisesRegex(ApiError, "Expected a JSON object"):
                    request_json("GET", "/sentiment/index")
