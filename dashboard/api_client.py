"""HTTP communication between the Streamlit dashboard and FastAPI."""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ApiError(RuntimeError):
    """The API request failed or returned an invalid response."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


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
