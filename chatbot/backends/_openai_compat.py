"""
Shared tool-schema conversion for backends using OpenAI's function-calling
wire format: Ollama's /api/chat uses the same shape (checked against a running
Ollama, see ollama_backend.py), as does OpenAI's Chat Completions API. One
copy, so both backends convert the same way.
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
