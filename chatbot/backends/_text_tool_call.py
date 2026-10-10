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


def _scan(content: str, tool_names: set[str]) -> tuple[list[tuple[str, dict]], int]:
    """Every tool call written in `content`, and where the last one ends."""
    if not content or '"name"' not in content:
        return [], 0
    decoder = json.JSONDecoder()
    calls, last_end = [], 0
    start = content.find("{")
    while start != -1:
        try:
            obj, end = decoder.raw_decode(content, start)
        except json.JSONDecodeError:
            obj, end = None, start + 1
        if isinstance(obj, dict) and obj.get("name") in tool_names:
            args = obj.get("parameters", obj.get("arguments", {}))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict):
                calls.append((obj["name"], args))
                last_end = end
                start = content.find("{", end)      # past this call: its own braces aren't another one
                continue
        start = content.find("{", start + 1)
    return calls, last_end


def text_tool_calls(content: str, tool_names: set[str]) -> list[tuple[str, dict]]:
    """(name, arguments) of every tool call written in `content`, in order."""
    return _scan(content, tool_names)[0]


def writing_past_its_calls(content: str, tool_names: set[str]) -> bool:
    """True once `content` holds a complete tool call followed by words that
    aren't the start of another: the model has gone on to write an answer
    before any result came back, and that answer can only be invented."""
    calls, end = _scan(content, tool_names)
    rest = content[end:].lstrip(" \n\t;,")
    return bool(calls) and bool(rest) and not rest.startswith(("{", "[", "]", "`"))


def text_tool_call(content: str, tool_names: set[str]) -> tuple[str, dict] | None:
    """(name, arguments) of the first tool call written in `content`, or None."""
    calls = text_tool_calls(content, tool_names)
    return calls[0] if calls else None
