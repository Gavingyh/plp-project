"""
Shared tool-schema conversion for backends using OpenAI's function-calling
wire format — Ollama's /api/chat deliberately mirrors this shape (verified
live, see ollama_backend.py), and OpenAI's own Chat Completions API is
naturally this shape. Kept in one place so both backends convert identically
rather than maintaining two copies that could drift apart.
"""


def to_openai_function_tools(claude_tool_schemas: list[dict]) -> list[dict]:
    """Converts chatbot/tools.py's TOOL_SCHEMAS (Anthropic's native shape:
    name/description/input_schema) into OpenAI-style function-calling tools
    ({"type": "function", "function": {name, description, parameters}})."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in claude_tool_schemas
    ]
