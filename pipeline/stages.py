"""Adapters for existing pipeline functions; model imports stay in the worker."""

import importlib.util
import os
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from pipeline.collection import ONLINE_SOURCES, collection_window, collect

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "earnings": "Bank earnings PDFs",
    "sgx_research": "Broker research PDFs",
    "google_news": "Google News",
    "arctic_shift": "Reddit",
}


def selected_sources(sources) -> list[str]:
    if isinstance(sources, str):
        raise ValueError("sources must be a list of source keys")
    values = list(sources)
    if not values or any(
        not isinstance(value, str) or value not in SOURCES for value in values
    ):
        raise ValueError(f"Select at least one supported source: {', '.join(SOURCES)}")
    return [source for source in SOURCES if source in values]


def source_module(source: str):
    if source == "earnings":
        from ingest import earnings_extract

        return earnings_extract
    if source == "sgx_research":
        from ingest import sgx_research_extract

        return sgx_research_extract
    raise ValueError(f"Unsupported source: {source}")


def describe_sources(sources: list[str] | None = None) -> list[dict]:
    out = []
    for source in selected_sources(sources) if sources is not None else SOURCES:
        label = SOURCES[source]
        if source in ONLINE_SOURCES:
            out.append(
                {
                    "key": source,
                    "label": label,
                    "kind": "online",
                    "folder": "",
                    "exists": True,
                    "pdf_count": 0,
                }
            )
            continue
        folder = Path(source_module(source).PDF_DIR)
        folders = [folder]
        if source == "earnings":
            from ingest.base import BANKS

            folders = [folder / bank for bank in BANKS]
        count = sum(
            1
            for bank_folder in folders
            if bank_folder.is_dir()
            for path in bank_folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )
        out.append(
            {
                "key": source,
                "label": label,
                "kind": "local_pdf",
                "folder": str(folder),
                "exists": folder.is_dir(),
                "pdf_count": count,
            }
        )
    return out


def _model_files(folder: Path) -> None:
    required = [folder / "config.json", folder / "model.safetensors"]
    missing = [str(path) for path in required if not path.is_file()]
    if not any((folder / name).is_file() for name in ("tokenizer.json", "vocab.txt")):
        missing.append(f"{folder}: tokenizer.json or vocab.txt")
    if missing:
        raise RuntimeError("Missing model files: " + "; ".join(missing))


def _cached_finbert() -> Path:
    from huggingface_hub import snapshot_download

    try:
        folder = Path(snapshot_download("ProsusAI/finbert", local_files_only=True))
    except Exception as exc:
        raise RuntimeError(
            "ProsusAI/finbert is not cached locally. Cache its tokenizer and model before running."
        ) from exc
    if (
        not (folder / "config.json").is_file()
        or not any(
            (folder / name).is_file()
            for name in ("model.safetensors", "pytorch_model.bin")
        )
        or not any(
            (folder / name).is_file() for name in ("tokenizer.json", "vocab.txt")
        )
    ):
        raise RuntimeError(
            "The cached ProsusAI/finbert is incomplete; cache its tokenizer and model first."
        )
    return folder


def _check_ollama(model: str) -> None:
    import requests

    address = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        response = requests.get(f"{address}/api/tags", timeout=(3, 5))
        response.raise_for_status()
        models = {item["name"] for item in response.json()["models"]}
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            "Cannot read Ollama's models. Start Ollama before assigning topics."
        ) from exc
    if model not in models and f"{model}:latest" not in models:
        raise RuntimeError(
            f"Ollama model {model!r} is unavailable. Pull the configured topic model first."
        )


def preflight(sources: list[str]) -> dict:
    """Check prerequisites before an import can change the corpus. No downloads."""
    from ingest import db

    inventory = describe_sources(sources)
    for item in inventory:
        if not item["exists"]:
            raise RuntimeError(f"Source folder is missing: {item['folder']}")
    path = Path(db.DB_PATH).resolve()
    # mode=ro also avoids accidentally creating a blank database for a typo.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("SELECT doc_id FROM documents LIMIT 1").fetchall()
    dependencies = [
        "spacy",
        "en_core_web_sm",
        "torch",
        "transformers",
        "yaml",
    ]
    if any(source not in ONLINE_SOURCES for source in sources):
        dependencies.append("pdfplumber")
    if ONLINE_SOURCES.intersection(sources):
        dependencies.append("requests")
    if "google_news" in sources:
        dependencies.append("feedparser")
    if "sgx_research" in sources:
        dependencies.extend(["pypdfium2", "rapidocr_onnxruntime", "wordninja"])
    missing = [name for name in dependencies if importlib.util.find_spec(name) is None]
    if missing:
        message = "Missing dependencies: " + ", ".join(missing)
        if "en_core_web_sm" in missing:
            message += (
                ". Install the English model on the API host: "
                ".venv-plp/bin/python3 -m spacy download en_core_web_sm"
            )
        raise RuntimeError(message)
    from config import aspect_taxonomy, model_version

    config = aspect_taxonomy.load()
    method = config.get("assignment_method", "centroid")
    if method not in ("centroid", "llm"):
        raise ValueError(f"Unknown assignment_method: {method}")
    _cached_finbert()
    if model_version.MODEL_VERSION != model_version.BASE_VERSION:
        spec = model_version.FINETUNED.get(model_version.MODEL_VERSION)
        if not spec or not spec["models"]:
            raise RuntimeError(
                "The served sentiment version has no configured fine-tuned models."
            )
        for model in spec["models"]:
            _model_files(ROOT / model)
    if method == "llm":
        _check_ollama(config["llm_model"])
    return {
        "sources": inventory,
        "assignment_method": method,
        "model_version": model_version.MODEL_VERSION,
    }


def import_sources(sources: list[str], *, report, before_insert, window=None) -> dict:
    from ingest import db

    with closing(db.get_connection()) as conn:
        known = {row[0] for row in conn.execute("SELECT doc_id FROM documents")}
    summary = {}
    for source in sources:
        if source in ONLINE_SOURCES:
            summary[source] = collect(
                source,
                window or collection_window(sources),
                report=report,
                before_insert=before_insert,
            )
            continue
        events = []

        def on_file(event):
            events.append(event)
            report(event)

        docs = source_module(source).pull(skip_doc_ids=known, report=on_file)
        # Persist candidates BEFORE the commit; interrupted-run recovery can
        # reconcile them against the DB even if the worker dies just after it.
        before_insert(docs)
        attempted, inserted = db.upsert_documents(docs)
        known.update(doc["doc_id"] for doc in docs)
        summary[source] = {
            "files": dict(Counter(item["status"] for item in events)),
            "documents_attempted": attempted,
            "documents_inserted": inserted,
        }
    if summary and all(item.get("status") == "failed" for item in summary.values()):
        raise RuntimeError(
            "All selected online sources failed. Check source results and retry the same collection dates."
        )
    return summary


def imported_documents(run: dict) -> list[dict]:
    """Read the candidate manifest back against committed documents, including on failure."""
    candidates = run.get("import_candidates", [])
    if not candidates:
        return []
    path = Path(run["db_path"])
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        held = {row[0] for row in conn.execute("SELECT doc_id FROM documents")}
    return [item for item in candidates if item["doc_id"] in held]


def preprocess() -> dict:
    from preprocess.pipeline import run

    return run()


def assign_topics() -> dict:
    from aspects.assign import run

    return run()


def score_sentiment() -> dict:
    from sentiment.score import run

    return run()


def aggregate() -> dict:
    from aggregate.index import run

    return {"index_rows": run()}
