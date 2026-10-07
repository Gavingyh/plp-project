"""
Shared tool-schema conversion for backends using OpenAI's function-calling
wire format: Ollama's /api/chat uses the same shape (checked against a running
Ollama, see ollama_backend.py), as does OpenAI's Chat Completions API. One
copy, so both backends convert the same way.
"""

import json


def _nullable_optional(schema: dict) -> dict:
    """A copy of a tool's parameter schema in which every optional property also accepts null.

    A model that has nothing for an optional argument often sends null rather than leaving
    it out, and a strict server (Groq's, 6 Oct 2026) rejects the whole call with a 400 unless
    the schema allows null. chatbot/tools.py treats a null argument as not given."""
    out = json.loads(json.dumps(schema))
    required = set(out.get("required", []))
    for name, prop in out.get("properties", {}).items():
        if name in required or "type" not in prop:
            continue
        prop["type"] = [prop["type"], "null"] if isinstance(prop["type"], str) else prop["type"] + ["null"]
        if "enum" in prop and None not in prop["enum"]:
            prop["enum"] = list(prop["enum"]) + [None]
    return out


def to_openai_function_tools(claude_tool_schemas: list[dict], nullable_optional: bool = False) -> list[dict]:
    """Converts chatbot/tools.py's TOOL_SCHEMAS (Anthropic's native shape:
    name/description/input_schema) into OpenAI-style function-calling tools
    ({"type": "function", "function": {name, description, parameters}}).
    `nullable_optional` is for servers that validate arguments strictly."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": _nullable_optional(t["input_schema"]) if nullable_optional else t["input_schema"],
            },
        }
        for t in claude_tool_schemas
    ]
