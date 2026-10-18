"""Ask-page presentation and session state; the API owns chatbot behaviour."""

from collections.abc import Callable
import html

import streamlit as st

from dashboard.api_client import ApiError
from dashboard.chat import GUARD_LABELS


def _queue_question(question: str):
    if question and question.strip():
        st.session_state.pop("api_chat_failure", None)
        st.session_state.api_chat_pending = question.strip()


def _queue_typed_question():
    _queue_question(st.session_state.get("ask_input", ""))


def _clear_conversation():
    st.session_state.api_chat_history = []
    st.session_state.pop("api_chat_pending", None)
    st.session_state.pop("api_chat_failure", None)


def _suggestion_buttons(items: list[dict], *, start: int = 0, cards: bool = False):
    categories = {
        "overall": "Bank overview",
        "comparison": "Compare banks",
        "compare": "Compare banks",
        "aspect": "Explore a topic",
        "topic": "Explore a topic",
        "trend": "Follow the trend",
        "analyst": "Analyst context",
        "consensus": "Analyst context",
        "evidence": "Read the evidence",
    }
    if cards:
        columns = st.columns(len(items))
        for index, (col, item) in enumerate(zip(columns, items), start=start):
            with col.container(border=True, key=f"ask_starter_{index}"):
                label = categories.get(item.get("category"), "Explore the data")
                st.markdown(
                    f'<div class="ask-card-label">{html.escape(label)}</div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    item["question"],
                    key=f"sugg-{index}-{item['question']}",
                    on_click=_queue_question,
                    args=(item["question"],),
                    use_container_width=True,
                )
    else:
        for index, item in enumerate(items, start=start):
            st.button(
                item["question"],
                key=f"sugg-{index}-{item['question']}",
                on_click=_queue_question,
                args=(item["question"],),
                use_container_width=True,
            )


def _render_message(message: dict, index: int):
    role = message["role"]
    avatar = ":material/person:" if role == "user" else ":material/monitoring:"
    with st.container(key=f"ask_{role}_{index}"):
        with st.chat_message(role, avatar=avatar):
            author = "You" if role == "user" else "BankPulse"
            st.markdown(
                f'<div class="ask-author">{author}</div>', unsafe_allow_html=True
            )
            st.markdown(message["content"])
            if message.get("citation_unverified"):
                st.warning(
                    "Verification warning: supporting citations could not be verified. Do not rely on this answer."
                )
            if message.get("unverified_numbers"):
                numbers = ", ".join(
                    str(number) for number in message["unverified_numbers"]
                )
                st.warning(
                    f"Verification warning: these figures could not be verified: {numbers}."
                )
            if message.get("unverified_readings"):
                readings = ", ".join(message["unverified_readings"])
                st.warning(
                    f"Verification warning: these sentiment descriptions could not be verified: {readings}."
                )
            if message.get("guard"):
                label = GUARD_LABELS.get(message["guard"], "Predefined response")
                st.caption(f"Response type: {label}")


def render_answer_guidance():
    """Chatbot-specific details added to the shared sidebar help on Ask."""
    st.markdown(
        "**How answers work**\n\n"
        "Answers use the stored sentiment index and retrieved evidence. "
        "Follow-ups use the recent conversation.\n\n"
        "**Verification**\n\n"
        "Automated checks can revise or withhold unsupported figures, citations "
        "and sentiment descriptions, but may miss mistakes. Review supporting "
        "sources and sample sizes. BankPulse does not provide investment advice."
    )


def render(container, load_suggestions: Callable, send_message: Callable):
    history = st.session_state.setdefault("api_chat_history", [])
    # Consume each submission once. Reruns and navigation never resubmit it.
    pending = st.session_state.pop("api_chat_pending", None)
    failure = st.session_state.get("api_chat_failure")

    # Keep the input and its accessible caption together in Streamlit's footer.
    with st.bottom:
        with st.container(key="ask_composer"):
            st.chat_input(
                "Ask about DBS, OCBC or UOB…",
                key="ask_input",
                on_submit=_queue_typed_question,
                disabled=bool(pending),
            )
            st.caption(
                "AI answers can contain mistakes. Check the evidence. Not financial advice."
            )

    with container:
        context, controls = st.columns([3, 1], vertical_alignment="center")
        context.markdown(
            '<div class="ask-context"><span></span>DBS · OCBC · UOB'
            "<small>Based on the stored project data</small></div>",
            unsafe_allow_html=True,
        )
        controls.button(
            "Clear conversation",
            key="clear_chat",
            on_click=_clear_conversation,
            disabled=not (history or failure) or bool(pending),
            use_container_width=True,
        )

        if not history and not pending and not failure:
            st.markdown(
                '<div class="ask-welcome"><div class="eyebrow">Start exploring</div>'
                "<h3>What would you like to know?</h3>"
                "<p>Compare the banks, explore a topic or find the sentences behind a score.</p></div>",
                unsafe_allow_html=True,
            )

        for index, message in enumerate(history):
            _render_message(message, index)

        if failure:
            _render_message(
                {"role": "user", "content": failure["question"]}, len(history)
            )
            with st.container(key=f"ask_assistant_{len(history) + 1}"):
                with st.chat_message("assistant", avatar=":material/monitoring:"):
                    st.error(f"Could not get an answer. {failure['error']}")

        if pending:
            _render_message({"role": "user", "content": pending}, len(history))
            with st.container(key=f"ask_assistant_{len(history) + 1}"):
                with st.chat_message("assistant", avatar=":material/monitoring:"):
                    st.markdown(
                        '<div class="ask-author">BankPulse</div>',
                        unsafe_allow_html=True,
                    )
                    with st.spinner("Preparing your answer…", show_time=True):
                        try:
                            result = send_message(pending, history)
                        except ApiError as exc:
                            st.session_state.api_chat_failure = {
                                "question": pending,
                                "error": str(exc),
                            }
                            st.rerun()
                        else:
                            history.extend(
                                [
                                    {"role": "user", "content": pending},
                                    {
                                        "role": "assistant",
                                        "content": result["answer"],
                                        "guard": result.get("guard"),
                                        "citation_unverified": result[
                                            "citation_unverified"
                                        ],
                                        "unverified_numbers": result[
                                            "unverified_numbers"
                                        ],
                                        "unverified_readings": result.get(
                                            "unverified_readings", []
                                        ),
                                    },
                                ]
                            )
                            # Rebuild the welcome state and controls without sending again.
                            st.rerun()

        try:
            suggestions = load_suggestions()
        except ApiError as exc:
            st.warning(f"Suggested questions are unavailable. {exc}")
            suggestions = []
        if suggestions:
            if not history and not pending and not failure:
                _suggestion_buttons(suggestions[:3], cards=True)
                if len(suggestions) > 3:
                    with st.expander("More questions"):
                        _suggestion_buttons(suggestions[3:], start=3)
            else:
                with st.expander("Suggested questions"):
                    _suggestion_buttons(suggestions)

        st.caption("You can follow up with questions such as “And OCBC?”")
