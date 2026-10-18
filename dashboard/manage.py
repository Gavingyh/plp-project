"""Data Management presentation and polling. FastAPI owns all pipeline work."""

from collections.abc import Callable
import html
from pathlib import PurePosixPath

import pandas as pd
import streamlit as st

from dashboard.api_client import ApiError
from dashboard import pipeline_client as client
from dashboard.style import section_heading

STATUS_LABELS = {
    "queued": "Queued",
    "running": "Running",
    "completed": "Completed",
    "completed_with_warnings": "Completed with warnings",
    "failed": "Failed",
    "interrupted": "Interrupted",
    "pending": "Pending",
}


def sync_history(refresh: Callable) -> tuple[dict | None, bool]:
    """Notice terminal runs before loading cached data, including after reconnects.

    Also clear caches after failure: earlier stages may have committed evidence.
    Chat messages and the user's selections remain in Session State.
    """
    try:
        history = client.load_history()
    except ApiError as exc:
        st.session_state.pipeline_history_error = str(exc)
        return None, False
    st.session_state.pop("pipeline_history_error", None)
    seen = set(st.session_state.get("pipeline_seen_terminal", []))
    terminal = {
        row["run_id"] for row in history["runs"] if row["status"] in client.TERMINAL
    }
    changed = bool(terminal - seen)
    if changed:
        refresh()
    # Bounded by the history window; a fresh session invalidates old cached data too.
    st.session_state.pipeline_seen_terminal = list(terminal)
    st.session_state.pipeline_history = history
    return history, changed


@st.fragment(run_every=2)
def render_update_notice(refresh: Callable):
    """Keep other pages informed without re-running charts on every poll."""
    history, changed = sync_history(refresh)
    if changed:
        st.rerun()
    if history is None:
        st.warning(
            "Data update status is unavailable. Stored views remain available; "
            "open Data Management to check the connection."
        )
    elif history["active_run_id"]:
        st.info(
            "Data update in progress. Scores show the last computed index; "
            "evidence may change as stages finish. Follow progress in Data Management."
        )


def _date(value) -> str:
    date = pd.to_datetime(value, utc=True, errors="coerce")
    return date.strftime("%d %b %Y, %H:%M UTC") if pd.notna(date) else "—"


def _history_label(run: dict) -> str:
    date = pd.to_datetime(run.get("started_at"), utc=True, errors="coerce")
    when = date.strftime("%d %b · %H:%M UTC") if pd.notna(date) else "Unknown date"
    sources = " + ".join(
        {"earnings": "Earnings", "sgx_research": "Research"}[source]
        for source in run["sources"]
    )
    return f"{when} · {sources} · {STATUS_LABELS[run['status']]} · {run['run_id'][:8]}"


def _folder_label(folder: str) -> str:
    """A compact location hint; the API's full path stays in Folder locations."""
    parts = PurePosixPath(folder.replace("\\", "/")).parts
    return "/".join(parts[-2:])


def _outcome(run: dict):
    state = run["status"]
    if state == "completed":
        st.success("Update complete. The dashboard is refreshed.")
    elif state == "completed_with_warnings":
        st.warning("Update complete. Review the file warnings below.")
    elif state in {"failed", "interrupted"}:
        preflight_failed = any(
            stage["key"] == "preflight" and stage["status"] == "failed"
            for stage in run["stages"]
        )
        if preflight_failed:
            st.error("Setup check failed. Import did not start.")
            if "en_core_web_sm" in (run.get("error") or ""):
                st.markdown("**The English language model was missing.**")
                st.caption(
                    "If it has not been installed yet, run this on the API machine from the project folder:"
                )
                st.code(
                    ".venv-plp/bin/python3 -m spacy download en_core_web_sm",
                    language="bash",
                    wrap_lines=True,
                )
            else:
                st.caption(
                    run.get("error") or "See technical details for the setup issue."
                )
            st.caption(
                "This run added no documents. Once setup is fixed, start a new update."
            )
        else:
            st.error(run.get("error") or STATUS_LABELS[state])
            st.caption(
                "Earlier saved work remains. Resolve the issue, then start another update to finish pending analysis."
            )
    elif state == "queued":
        st.caption("Accepted · waiting for prerequisite checks")
    else:
        st.caption("Analysis is running. You can leave this page and return later.")


def _run_details(run: dict):
    state = run["status"]
    stages = run["stages"]
    completed = sum(stage["status"] == "completed" for stage in stages)
    st.markdown(
        '<div class="pipeline-run-heading"><div>'
        f'<h3>{"Update in progress" if state in client.ACTIVE else "Update summary"}</h3></div>'
        f'<span class="pipeline-state state-{state}">{STATUS_LABELS[state]}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Started {_date(run.get('started_at'))} · "
        + (
            f"Finished {_date(run['finished_at'])}"
            if run.get("finished_at")
            else "Updates every 2 seconds while this page is open"
        )
    )
    _outcome(run)
    st.progress(
        completed / len(stages) if stages else 0,
        text=f"{completed} of {len(stages)} stages complete",
    )
    steps = "".join(
        f'<div class="pipeline-step step-{html.escape(stage["status"])}">'
        f'<span class="pipeline-step-number">{index}</span><div>'
        f'<strong>{html.escape(stage["label"])}</strong>'
        f'</div><span class="pipeline-step-status">{("Not started" if state in client.TERMINAL and stage["status"] == "pending" else STATUS_LABELS[stage["status"]])}</span></div>'
        for index, stage in enumerate(stages, 1)
    )
    finished = state in {"completed", "completed_with_warnings"}
    stages_label = (
        f"Pipeline stages · {completed} of {len(stages)} complete"
        if finished
        else "Pipeline stages"
    )
    with st.expander(stages_label, expanded=not finished):
        st.markdown(
            f'<div class="pipeline-stages">{steps}</div>', unsafe_allow_html=True
        )
    files = [file for stage in stages for file in stage.get("files", [])]
    if files or run.get("imported_documents") or state.startswith("completed"):
        metrics = st.columns(3)
        metrics[0].metric("New documents", len(run.get("imported_documents", [])))
        metrics[1].metric(
            "Skipped PDFs",
            sum(file.get("status") == "already_stored" for file in files),
        )
        metrics[2].metric("Warnings", len(run.get("warnings", [])))
        st.caption("Counts recorded so far; skipped PDFs were already stored.")
    if run.get("warnings"):
        with st.expander(f"Warnings ({len(run['warnings'])})"):
            st.dataframe(
                pd.DataFrame(run["warnings"]), hide_index=True, width="stretch"
            )
    with st.expander("File outcomes and stage metrics"):
        if files:
            st.dataframe(pd.DataFrame(files), hide_index=True, width="stretch")
        else:
            st.caption("No PDF outcomes have been recorded yet.")
        for stage in stages:
            if stage.get("error"):
                st.error(f"{stage['label']}: {stage['error']}")
            if stage.get("metrics"):
                st.markdown(f"**{stage['label']}**")
                st.json(stage["metrics"], expanded=False)
    with st.expander("Technical details and imported documents"):
        st.caption(
            "Progress counts stages, not elapsed time. Some stages take longer than others."
        )
        if run.get("error"):
            st.code(run["error"], language=None, wrap_lines=True)
        st.caption(
            f"Model: {run.get('model_version') or 'Checked during prerequisites'}"
        )
        st.code(run["run_id"], language=None)
        for label, key in (
            ("Database", "db_path"),
            ("Stage log", "log_path"),
            ("Worker log", "worker_log_path"),
        ):
            if run.get(key):
                st.caption(label)
                st.code(run[key], language=None)
        if run.get("imported_documents"):
            st.dataframe(
                pd.DataFrame(run["imported_documents"]),
                hide_index=True,
                width="stretch",
            )


def render_guidance():
    st.markdown(
        "**Manual data updates**\n\n"
        "Place PDFs in the listed server folders, select sources and start a run. "
        "Existing document IDs are skipped; later stages finish all pending database "
        "work and rebuild the index. Existing trained models are used.\n\n"
        "Only one manual run can be active. Progress survives a page refresh or API "
        "restart. If a start response is lost, check run status before trying again."
    )


def _queue_run(sources: list[str]):
    st.session_state.pipeline_pending_sources = list(sources)


def _select_all_sources(keys: list[str]):
    st.session_state.pipeline_source_selection = (
        list(keys) if st.session_state.pipeline_all_sources else []
    )
    for key in keys:
        st.session_state[f"pipeline_select_{key}"] = (
            st.session_state.pipeline_all_sources
        )


def _sync_all_sources(keys: list[str]):
    st.session_state.pipeline_source_selection = [
        key for key in keys if st.session_state.get(f"pipeline_select_{key}", False)
    ]
    st.session_state.pipeline_all_sources = all(
        st.session_state.get(f"pipeline_select_{key}", False) for key in keys
    )


def _source_controls(history: dict | None, active_id: str | None, refresh: Callable):
    with st.container(border=True, height="stretch", key="pipeline_controls"):
        st.markdown(
            section_heading("Start a data update", "Local PDFs"), unsafe_allow_html=True
        )
        st.caption("Choose your sources. Existing documents are skipped automatically.")
        selected = []
        sources_ready = False
        try:
            sources = client.load_sources()
        except ApiError as exc:
            st.error(str(exc))
        else:
            sources_ready = True
            keys = [source["key"] for source in sources]
            all_present = all(source["exists"] for source in sources)
            blocked = bool(active_id) or history is None
            # Preserve choices when a start/completion rerun temporarily removes
            # widgets. Streamlit cleans up widget state, but keeps this data key.
            remembered = st.session_state.get("pipeline_source_selection", [])
            for source in sources:
                st.session_state[f"pipeline_select_{source['key']}"] = (
                    source["key"] in remembered and source["exists"]
                )
            st.session_state.pipeline_all_sources = all_present and all(
                st.session_state[f"pipeline_select_{key}"] for key in keys
            )
            st.checkbox(
                "All PDF sources",
                key="pipeline_all_sources",
                on_change=_select_all_sources,
                args=(keys,),
                disabled=blocked or not all_present,
            )
            for column, source in zip(st.columns(2), sources):
                with column.container(
                    border=True, key=f"pipeline_source_{source['key']}"
                ):
                    checked = st.checkbox(
                        client.SOURCES[source["key"]],
                        key=f"pipeline_select_{source['key']}",
                        on_change=_sync_all_sources,
                        args=(keys,),
                        disabled=blocked or not source["exists"],
                    )
                    availability = (
                        "PDFs found" if source["exists"] else "Folder missing"
                    )
                    st.markdown(
                        '<div class="pipeline-source-count">'
                        f'<strong>{source["pdf_count"]:,}</strong><span>{availability}</span></div>'
                        f'<div class="pipeline-folder">{html.escape(_folder_label(source["folder"]))}</div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        "Bank results · DBS / OCBC / UOB subfolders"
                        if source["key"] == "earnings"
                        else "Broker reports · place PDFs directly here"
                    )
                    if checked and source["exists"]:
                        selected.append(source["key"])
            count = sum(
                source["pdf_count"] for source in sources if source["key"] in selected
            )
            st.markdown(
                f'<div class="pipeline-selection"><strong>{len(selected)} of {len(sources)} sources selected</strong>'
                f"<span>{count:,} PDFs in these folders · includes already stored files</span></div>",
                unsafe_allow_html=True,
            )
        uncertain = st.session_state.get("pipeline_start_uncertain", False)
        notice = st.session_state.get("pipeline_start_notice")
        if notice:
            st.warning(notice)
        if uncertain and st.button("Check run status", key="pipeline_check_status"):
            checked_history, _ = sync_history(refresh)
            if checked_history is not None:
                st.session_state.pipeline_start_uncertain = False
                st.session_state.pop("pipeline_start_notice", None)
                st.rerun()
        st.button(
            "Run selected sources",
            type="primary",
            key="pipeline_start",
            on_click=_queue_run,
            args=(selected,),
            use_container_width=True,
            disabled=not selected
            or not sources_ready
            or history is None
            or bool(active_id)
            or uncertain,
        )
        if active_id:
            st.caption(
                "An update is already running. Follow its progress in Recent activity."
            )
        st.markdown(
            '<div class="pipeline-scope-note">Updates the current database using the existing trained models. '
            "After import, <strong>all pending analysis</strong> is completed and the index is refreshed.</div>",
            unsafe_allow_html=True,
        )
        if sources_ready:
            with st.expander("Folder locations"):
                st.caption(
                    "Detected on the API machine from its checkout location. Each teammate can clone the project to a different directory."
                )
                for source in sources:
                    st.caption(client.SOURCES[source["key"]])
                    st.code(source["folder"], language=None, wrap_lines=True)
                st.caption(
                    "These locations belong to the machine running the API; they may differ from the computer displaying this page."
                )
        with st.expander("What does All PDF sources include?"):
            st.markdown(
                "**Bank earnings and broker research PDFs.** This version imports the two local PDF folders. Online news and Reddit collection are separate workflows. Models are used for inference; they are not retrained."
            )


def _recent_activity(known: dict, history: dict | None, refresh: Callable):
    st.markdown(
        section_heading("Recent activity", "Latest 20 runs"), unsafe_allow_html=True
    )
    st.caption("Review progress, results and warnings from your saved updates.")
    runs = known["runs"]
    if not runs:
        st.markdown(
            '<div class="pipeline-empty"><span class="pipeline-empty-icon">↻</span>'
            "<h3>Your updates will appear here</h3>"
            "<p>Select a source to run your first update. Progress and results are saved, so you can return later.</p></div>",
            unsafe_allow_html=True,
        )
        return
    active_id = known["active_run_id"]
    by_id = {run["run_id"]: run for run in runs}
    if st.session_state.get("pipeline_follow_active") != active_id and active_id:
        st.session_state.pipeline_focus = active_id
    st.session_state.pipeline_follow_active = active_id
    if st.session_state.get("pipeline_focus") not in by_id:
        st.session_state.pipeline_focus = active_id or runs[0]["run_id"]
    run_id = st.selectbox(
        "Run to inspect",
        list(by_id),
        key="pipeline_focus",
        format_func=lambda key: _history_label(by_id[key]),
        label_visibility="collapsed",
    )
    if history is None:
        st.caption("Showing the last known run list; live status is unavailable.")
        return
    try:
        run = client.load_run(run_id)
    except ApiError as exc:
        st.error(str(exc))
        return
    if run["status"] in client.TERMINAL and run_id not in st.session_state.get(
        "pipeline_seen_terminal", []
    ):
        refresh()
        st.rerun()
    with st.container(key="pipeline_run"):
        _run_details(run)


@st.fragment(run_every=2)
def render(refresh: Callable):
    # Consume an explicit button submission once, before polling or rendering.
    # Timer reruns and navigation never enqueue a start themselves.
    pending = st.session_state.pop("pipeline_pending_sources", None)
    if pending is not None:
        try:
            run = client.start_run(pending)
        except ApiError as exc:
            st.session_state.pipeline_start_uncertain = True
            st.session_state.pipeline_start_notice = (
                "Another manual run is already active. Check run status to follow its progress."
                if exc.status_code == 409
                else f"{exc} The start could not be confirmed. Check run status before trying again; the request will not be retried automatically."
            )
        else:
            st.session_state.pipeline_focus = run["run_id"]
            st.session_state.pop("pipeline_start_notice", None)
        st.rerun()
    history, changed = sync_history(refresh)
    if changed:
        st.rerun()
    if history is None:
        st.error(st.session_state.pipeline_history_error)
        st.caption(
            "Run status cannot be confirmed. Starting another run is disabled until the API reconnects."
        )
    known = history or st.session_state.get(
        "pipeline_history", {"runs": [], "active_run_id": None}
    )
    with st.container(key="pipeline_workspace"):
        controls, activity = st.columns(2, gap="medium")
        with controls:
            _source_controls(history, known["active_run_id"], refresh)
        with activity:
            with st.container(border=True, height="stretch", key="pipeline_activity"):
                _recent_activity(known, history, refresh)
