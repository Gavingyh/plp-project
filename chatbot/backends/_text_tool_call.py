"""
A tool call written out as text instead of made.

Local llama models sometimes answer with the call itself, e.g.
`Let me check. {"name": "search_evidence", "parameters": {"bank": "DBS"}}`,
rather than returning it in `tool_calls`. The user then sees JSON instead of
an answer. Seen three times in the gold-set runs of 30 Sep and 1 Oct (8B
lookup-2 and mt-3 turn 2, 3B compare-3). The backend recognises such a call
and runs it, as if the model had made it properly.

Only a JSON object naming one of the offered tools, with its arguments under
"parameters" or "arguments", counts; any other JSON in an answer is left
alone.
"""

import json


def text_tool_call(content: str, tool_names: set[str]) -> tuple[str, dict] | None:
    """(name, arguments) of the first tool call written in `content`, or None."""
    if not content or '"name"' not in content:
        return None
    decoder = json.JSONDecoder()
    start = content.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(content, start)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and obj.get("name") in tool_names:
            args = obj.get("parameters", obj.get("arguments", {}))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict):
                return obj["name"], args
        start = content.find("{", start + 1)
    return None
