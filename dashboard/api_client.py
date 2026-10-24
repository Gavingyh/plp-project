"""HTTP communication between the Streamlit dashboard and FastAPI."""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ApiError(RuntimeError):
    """The API request failed or returned an invalid response."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 error_code: str | None = None, setup_hint: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.setup_hint = setup_hint


def request_json(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    read_timeout: float = 30,
) -> dict:
    """Return an API JSON object, including its metadata and result rows.

    Timeouts are measured separately: five seconds to connect, followed by
    read_timeout seconds without response data. Chat callers can allow a
    longer read timeout for model/tool calls. Requests are not retried
    automatically, since retrying a chat POST could generate an answer twice.
    """
    default_url = f"http://127.0.0.1:{os.getenv('PLP_API_PORT', '8000')}"
    base_url = (os.getenv("PLP_API_URL") or default_url).rstrip("/")

    try:
        response = requests.request(
            method,
            f"{base_url}/{path.lstrip('/')}",
            params=params,
            json=body,
            timeout=(5, read_timeout),
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise ApiError("The API request timed out.") from exc
    except requests.ConnectionError as exc:
        raise ApiError("Cannot connect to the API service.") from exc
    except requests.HTTPError as exc:
        if exc.response is None:
            raise ApiError(f"The API returned an HTTP error for {path}.") from exc
        if path.strip("/") == "chat" and exc.response.status_code == 503:
            try:
                payload = exc.response.json()
            except ValueError:
                payload = None
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if (isinstance(detail, dict) and isinstance(detail.get("code"), str)
                    and isinstance(detail.get("message"), str) and detail["message"].strip()
                    and (detail.get("setup_hint") is None or isinstance(detail["setup_hint"], str))):
                raise ApiError(detail["message"], status_code=503,
                               error_code=detail["code"], setup_hint=detail.get("setup_hint")) from exc
        raise ApiError(
            f"The API returned HTTP {exc.response.status_code} for {path}.",
            status_code=exc.response.status_code,
        ) from exc
    except requests.RequestException as exc:
        raise ApiError("The API request failed.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiError("The API returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise ApiError("Expected a JSON object from the API.")

    return payload
