"""
An interactive chat with the bot in the terminal, for testing it. It keeps
the conversation's memory, so follow-ups like "and OCBC?" work, and shows the
same flags the API returns: which input guard answered, whether a citation
couldn't be verified, and figures that match nothing the tools returned.

Dashboards reach the same bot through POST /chat (docs/api-integration.md).

USAGE:
  python -m chatbot.chat                      # model chosen as in .env (CHATBOT_BACKEND)
  python -m chatbot.chat --backend ollama --trace data/logs/chat_trace.jsonl

Inside: type a question; /suggest lists starter questions, /tools shows the
last turn's tool calls, /reset forgets the conversation, /quit leaves.
"""

import argparse
import json

from chatbot.agent import Conversation


def format_turn(turn) -> str:
    lines = [turn.answer.strip()]
    flags = []
    if turn.guard:
        flags.append(f"answered by the {turn.guard} guard, not the model")
    shown = turn.shown_flags()
    if shown["citation_unverified"]:
        flags.append("cites evidence the tools never returned: don't trust it")
    if shown["unverified_numbers"]:
        flags.append("figures matching nothing the tools returned: " + ", ".join(map(str, shown["unverified_numbers"])))
    if shown["unverified_readings"]:
        flags.append("describes the mood in words the tools never returned: " + ", ".join(shown["unverified_readings"]))
    if getattr(turn, "repaired", None):
        flags.append(f"(checked before it was shown: {turn.repaired})")
    if flags:
        lines += [""] + [f"  [!] {f}" for f in flags]
    return "\n".join(lines)


def format_calls(turn) -> str:
    if not turn or not turn.calls:
        return "  (no tool calls)"
    return "\n".join(f"  {c.get('name', '?')}({json.dumps(c.get('args', c.get('arguments', {})), default=str)})"
                     if isinstance(c, dict) else f"  {c}" for c in turn.calls)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--backend", default=None, help="claude | openai | ollama (default: CHATBOT_BACKEND, otherwise openai)")
    p.add_argument("--trace", default=None, help="append each turn as JSON to this file")
    args = p.parse_args()

    from config.logging_config import setup_logging
    setup_logging()
    conv = Conversation(backend_name=args.backend, trace_path=args.trace)
    last = None
    print("Ask about DBS, OCBC and UOB sentiment. /suggest, /tools, /reset, /quit.")
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("/quit", "/exit"):
            break
        if q == "/reset":
            conv, last = Conversation(backend_name=args.backend, trace_path=args.trace), None
            print("(conversation forgotten)")
            continue
        if q == "/suggest":
            from chatbot.suggestions import get_suggestions
            for s in get_suggestions(limit=6):
                print(f"  - {s}")
            continue
        if q == "/tools":
            print(format_calls(last))
            continue
        last = conv.ask(q)
        print("\nbot> " + format_turn(last))


if __name__ == "__main__":
    main()
