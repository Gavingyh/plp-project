"""The dashboard's stateless chat API adapter; no model or database imports."""

from dashboard.api_client import ApiError, request_json

GUARD_LABELS = {
    "advice": "Investment advice request",
    "other_bank": "Bank outside project coverage",
    "off_topic": "Question outside project scope",
    "greeting": "Greeting",
    "thanks": "Thanks",
    "goodbye": "Goodbye",
    "help": "Help",
    "service": "Banking service question",
    "injection": "Unsupported instruction",
    "feedback": "Feedback",
}


def send_chat(message: str, history: list[dict]) -> dict:
    """Send earlier messages, excluding display-only verification metadata.

    The new question goes in message exactly once. The API reconstructs the
    conversation and applies its own context limits. A long read timeout
    allows several local model/tool calls; the HTTP client does not retry.
    """
    payload = request_json(
        "POST",
        "/chat",
        body={
            "message": message,
            "history": [
                {"role": item["role"], "content": item["content"]} for item in history
            ],
        },
        read_timeout=600,
    )
    if (
        not isinstance(payload.get("answer"), str)
        or not payload["answer"].strip()
        or not isinstance(payload.get("citation_unverified"), bool)
        or not isinstance(payload.get("unverified_numbers"), list)
        or (payload.get("guard") is not None and not isinstance(payload["guard"], str))
    ):
        raise ApiError("The API returned an invalid chat response.")
    return payload
