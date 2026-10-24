"""Prepare persistent BankPulse files before starting the application.

Only selected runtime files are restored. Existing data is never replaced.
Run with --data-only to validate/restore a bundle without network/model work.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile, is_zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = {"plp.db", "sentence_embeddings.npz", "search_embeddings.npz", "cna/articles.jsonl", "cna/candidates.json"}
MODEL_FILES = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "input_format.json")


class SetupError(RuntimeError):
    """An actionable setup problem, safe to display without credentials."""


def log(message: str) -> None:
    print(f"[setup] {message}", flush=True)


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify_archive_hash(path: Path, expected: str) -> None:
    if expected:
        if len(expected) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected):
            raise SetupError("PLP_DATA_SHA256 must contain exactly 64 hexadecimal characters.")
        if sha256(path) != expected.lower():
            raise SetupError("data/data.zip failed SHA-256 verification. Obtain the supplied bundle again.")


def download_archive(path: Path, url: str, expected: str = "", token: str = "") -> None:
    import requests

    address = urlsplit(url)
    if address.scheme != "https" or not address.netloc or address.username or address.password:
        raise SetupError("PLP_DATA_URL must be an HTTPS download link without embedded login credentials.")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".bundle-", delete=False) as target:
            temporary = Path(target.name)
            log("Downloading the dataset bundle (the download URL and credentials are not logged).")
            with requests.get(url, headers=headers, stream=True, timeout=(20, 120)) as response:
                response.raise_for_status()
                for block in response.iter_content(1024 * 1024):
                    target.write(block)
        verify_archive_hash(temporary, expected)
        if not is_zipfile(temporary):
            raise SetupError("The dataset download is not a ZIP. Use a direct file download link.")
        os.replace(temporary, path)
    except requests.RequestException as exc:
        raise SetupError("Dataset download failed. Check PLP_DATA_URL, access credentials and internet connection.") from exc
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)


def archive_members(archive: ZipFile) -> dict[str, str]:
    """Accept flat bundles and data/-prefixed ZIPs, rejecting ambiguous paths."""
    selected = {}
    for item in archive.infolist():
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in item.filename or stat.S_ISLNK(item.external_attr >> 16):
            raise SetupError("Dataset ZIP contains an unsafe path or symbolic link.")
        if item.is_dir():
            continue
        relative = str(path.relative_to("data")) if path.parts and path.parts[0] == "data" else str(path)
        if relative not in RUNTIME_FILES and not (
            relative.startswith("aspect_llm/") and len(PurePosixPath(relative).parts) == 2 and relative.endswith(".jsonl")
        ):
            continue
        if relative in selected:
            raise SetupError(f"Dataset ZIP contains duplicate runtime file: {relative}")
        selected[relative] = item.filename
    return selected


def validate_database(path: Path, model_version: str) -> set[str]:
    if not path.is_file():
        raise SetupError("Missing database. Place the supplied ZIP at data/data.zip and start again.")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise SetupError("The database failed its SQLite integrity check. Restore a valid team bundle.")
            for table in ("documents", "sentences", "sentence_aspects", "aspect_sentiment", "sentiment_index", "analyst_consensus"):
                conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchall()
            for table in ("aspect_sentiment", "sentiment_index"):
                found = conn.execute(f"SELECT 1 FROM {table} WHERE model_version=? LIMIT 1", (model_version,)).fetchone()
                if not found:
                    raise SetupError(f"The database has no {table} rows for {model_version}. Use the matching team dataset.")
            return {row[0] for row in conn.execute("SELECT sentence_id FROM sentences")}
    except sqlite3.Error as exc:
        raise SetupError("The database is unreadable or its schema is incomplete. Use a valid team dataset.") from exc


def validate_embeddings(path: Path, sentence_ids: set[str], *, width: int = 768, allow_stale: bool = False) -> int:
    import numpy as np

    try:
        with np.load(path, allow_pickle=False) as cache:
            ids, vectors = cache["sentence_ids"], cache["vectors"]
            if ids.ndim != 1 or ids.dtype.kind not in "US" or vectors.shape != (len(ids), width):
                raise ValueError("invalid shape or sentence IDs")
            identifiers = set(ids.tolist())
            if (len(identifiers) != len(ids) or (not allow_stale and not identifiers.issubset(sentence_ids))
                    or not np.isfinite(vectors).all()):
                raise ValueError("invalid or stale entries")
            if sentence_ids and not len(ids):
                raise ValueError("empty embedding cache")
            return len(ids)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile) as exc:
        raise SetupError("The embedding cache is invalid or belongs to another database. Supply a matching database/cache bundle.") from exc


def publish_missing(source: Path, destination: Path) -> bool:
    """Atomic, non-overwriting installation on the same persistent filesystem."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.parent.is_symlink():
        raise SetupError(f"Runtime destination must not be a symbolic link: {destination.name}")
    try:
        os.link(source, destination)
    except FileExistsError:
        return False
    return True


def prepare_data(data: Path, model_version: str) -> dict:
    data.mkdir(parents=True, exist_ok=True)
    archive_path = data / "data.zip"
    essential_missing = not (data / "plp.db").is_file() or not (data / "sentence_embeddings.npz").is_file()
    if not archive_path.is_file() and essential_missing:
        url = os.environ.get("PLP_DATA_URL", "").strip()
        if url:
            download_archive(archive_path, url, os.environ.get("PLP_DATA_SHA256", ""), os.environ.get("PLP_DATA_TOKEN", ""))
        else:
            raise SetupError("Place the supplied data.zip at data/data.zip (no manual extraction), then run docker compose up --build again. A direct PLP_DATA_URL is also supported.")
    restored = []
    with tempfile.TemporaryDirectory(dir=data, prefix=".setup-") as workspace:
        staging = Path(workspace)
        if archive_path.is_file():
            verify_archive_hash(archive_path, os.environ.get("PLP_DATA_SHA256", ""))
            try:
                with ZipFile(archive_path) as archive:
                    for relative, member in archive_members(archive).items():
                        if (data / relative).exists():
                            continue
                        target = staging / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output, 1024 * 1024)
            except (BadZipFile, EOFError) as exc:
                raise SetupError("data/data.zip is damaged or is not a ZIP. Obtain the supplied bundle again.") from exc
        database = data / "plp.db" if (data / "plp.db").exists() else staging / "plp.db"
        embeddings = data / "sentence_embeddings.npz" if (data / "sentence_embeddings.npz").exists() else staging / "sentence_embeddings.npz"
        identifiers = validate_database(database, model_version)
        embedded = validate_embeddings(embeddings, identifiers)
        # Publish the database last, after the matching cache and all checks pass.
        files = sorted(p for p in staging.rglob("*") if p.is_file() and p.name != "plp.db")
        if (staging / "plp.db").is_file():
            files.append(staging / "plp.db")
        for source in files:
            relative = source.relative_to(staging)
            destination = data / relative
            if not destination.resolve().is_relative_to(data.resolve()):
                raise SetupError("Runtime destination points outside the data folder.")
            if publish_missing(source, destination):
                restored.append(str(relative))
        (data / "run").mkdir(exist_ok=True)
        (data / "logs").mkdir(exist_ok=True)
        (data / "preview").mkdir(exist_ok=True)
    log(f"Data ready: {len(identifiers):,} sentences; {embedded:,} embeddings; {len(restored)} files restored. Existing files preserved.")
    return {"sentences": len(identifiers), "embeddings": embedded, "restored": restored}


def valid_checkpoint(folder: Path, expected: str) -> bool:
    if not all((folder / name).is_file() for name in MODEL_FILES):
        return False
    try:
        for name in MODEL_FILES:
            if name.endswith(".json"):
                json.loads((folder / name).read_text())
        return sha256(folder / "model.safetensors") == expected
    except (OSError, ValueError):
        return False


def prepare_models(root: Path) -> dict:
    from huggingface_hub import snapshot_download
    from config.model_version import BASE_MODEL_DOWNLOAD_PATTERNS, MODEL_VERSION, FINETUNED

    manifest = json.loads((ROOT / "docker/models.json").read_text())
    base, fine = manifest["base"], manifest["finetuned"]
    expected_paths = {f"{fine['destination']}/{seed}/final" for seed in fine["weights_sha256"]}
    active_paths = set(FINETUNED.get(MODEL_VERSION, {}).get("models", []))
    if fine["model_version"] != MODEL_VERSION or expected_paths != active_paths:
        raise SetupError("docker/models.json does not match the served model configuration. Update its revision, paths and checksums together with config/model_version.py.")
    revision = os.environ.get("FINBERT_REVISION") or base["revision"]
    options = {"token": os.environ.get("HF_TOKEN") or False}
    base_patterns = BASE_MODEL_DOWNLOAD_PATTERNS
    try:
        log("Checking the public base FinBERT model and tokenizer.")
        try:
            cached = Path(snapshot_download(base["repo"], revision=revision, local_files_only=True,
                                            allow_patterns=base_patterns, **options))
            base_ready = (
                (cached / "config.json").is_file()
                and any((cached / name).is_file() for name in ("model.safetensors", "pytorch_model.bin"))
                and any((cached / name).is_file() for name in ("tokenizer.json", "vocab.txt"))
            )
        except Exception:
            base_ready = False
        if not base_ready:
            snapshot_download(base["repo"], revision=revision, allow_patterns=base_patterns, **options)
        destinations = {seed: root / fine["destination"] / seed / "final" for seed in fine["weights_sha256"]}
        missing = [seed for seed, folder in destinations.items() if not valid_checkpoint(folder, fine["weights_sha256"][seed])]
        if missing:
            log(f"Downloading/verifying fine-tuned FinBERT checkpoints: {', '.join(missing)}.")
            downloaded = Path(snapshot_download(
                fine["repo"], revision=fine["revision"],
                allow_patterns=[f"{fine['source']}/{seed}/final/{name}" for seed in missing for name in MODEL_FILES],
                **options,
            ))
            for seed in missing:
                source = downloaded / fine["source"] / seed / "final"
                if not valid_checkpoint(source, fine["weights_sha256"][seed]):
                    raise SetupError(f"FinBERT {seed} is incomplete or failed its recorded SHA-256 checksum.")
                target = destinations[seed]
                target.mkdir(parents=True, exist_ok=True)
                for name in MODEL_FILES:
                    with tempfile.NamedTemporaryFile(dir=target, prefix=".model-", delete=False) as output:
                        temporary = Path(output.name)
                        with (source / name).open("rb") as stream:
                            shutil.copyfileobj(stream, output, 1024 * 1024)
                    os.replace(temporary, target / name)
        # Verify exactly the files consumed by the pipeline, with network disabled.
        previous = os.environ.get("FINBERT_REVISION")
        os.environ["FINBERT_REVISION"] = revision
        try:
            from pipeline.stages import _cached_finbert

            _cached_finbert()
        finally:
            if previous is None:
                os.environ.pop("FINBERT_REVISION", None)
            else:
                os.environ["FINBERT_REVISION"] = previous
        log("FinBERT ready: tokenizer/base cache and all three verified checkpoints.")
        return {"base_revision": revision, "finetuned_revision": fine["revision"]}
    except SetupError:
        raise
    except Exception as exc:
        # Library HTTP errors may include signed URLs; keep credentials out of logs.
        raise SetupError("FinBERT preparation failed. Check internet access and the public model repository; HF_TOKEN is optional if access is restricted. Re-run to resume downloads.") from exc


def prepare_search_model() -> None:
    from huggingface_hub import snapshot_download
    from config.search_model import DOWNLOAD_PATTERNS, MODEL_NAME, MODEL_REVISION, WIDTH
    from pipeline.stages import _cached_search_model

    spec = json.loads((ROOT / "docker/models.json").read_text())["search"]
    if (spec["repo"], spec["revision"], spec["width"]) != (MODEL_NAME, MODEL_REVISION, WIDTH):
        raise SetupError("The search model manifest does not match config/search_model.py. Update both together.")
    log("Checking the public MiniLM search model and tokenizer.")
    try:
        try:
            _cached_search_model()
        except RuntimeError:
            snapshot_download(MODEL_NAME, revision=MODEL_REVISION, allow_patterns=DOWNLOAD_PATTERNS,
                              token=os.environ.get("HF_TOKEN") or False)
            _cached_search_model()
    except Exception as exc:
        raise SetupError("MiniLM preparation failed. Check internet access and re-run setup to resume the public model download.") from exc
    log("MiniLM search model ready for offline use.")


def prepare_search_cache(data: Path) -> None:
    # Release the search model and its inference memory before warming Ollama.
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                   "PLP_DB_PATH": str((data / "plp.db").resolve()),
                   "PLP_SEARCH_EMBEDDINGS_PATH": str((data / "search_embeddings.npz").resolve())}
    result = subprocess.run([sys.executable, "-m", "docker.search_cache", "--data", str(data)], env=environment)
    if result.returncode:
        raise SetupError("Search cache preparation failed. Review the setup logs and re-run; the database is preserved.")


def ollama_models() -> list[str]:
    import yaml
    from chatbot import settings

    aspects = yaml.safe_load((ROOT / "config/aspects.yaml").read_text())
    models = [settings.get("models.intent"), settings.get("models.ollama")]
    if aspects.get("assignment_method") == "llm":
        models.append(aspects["llm_model"])
    models.extend(x.strip() for x in os.environ.get("PLP_EXTRA_OLLAMA_MODELS", "").split(",") if x.strip())
    return list(dict.fromkeys(models))


def prepare_ollama(address: str) -> list[str]:
    import requests

    address = address.rstrip("/")
    try:
        response = requests.get(f"{address}/api/tags", timeout=(5, 10))
        response.raise_for_status()
        known = {item["name"] for item in response.json()["models"]}
        for model in ollama_models():
            if model in known or f"{model}:latest" in known:
                log(f"Ollama {model}: already downloaded.")
                continue
            log(f"Downloading Ollama {model}. The first download can be several GB.")
            last = 0.0
            with requests.post(f"{address}/api/pull", json={"model": model, "stream": True}, stream=True, timeout=(10, 600)) as response:
                response.raise_for_status()
                success = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise SetupError(f"Ollama could not download {model}. Check the model name, disk space and internet connection.")
                    if event.get("status") == "success":
                        success = True
                    if time.monotonic() - last >= 10:
                        total = event.get("total", 0)
                        progress = f" ({event.get('completed', 0) * 100 // total}%)" if total else ""
                        log(f"Ollama {model}: {event.get('status', 'downloading')}{progress}")
                        last = time.monotonic()
                if not success:
                    raise SetupError(f"Ollama {model} download ended before completion. Start again to resume it.")
            known.add(model)
        return ollama_models()
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise SetupError("Cannot prepare Ollama models. Check that Ollama is running and reachable; in native Mac mode start the Ollama app first. Re-run to resume downloads.") from exc


def warm_intent() -> None:
    """Prime the shared classifier prompt before advertising application readiness."""
    from chatbot.intent import classify_intent

    started = time.monotonic()
    log("Warming the local intent classifier. A CPU-only cold start can take several minutes; no hosted API is called.")
    if classify_intent("What is the overall sentiment on DBS?") != "in_scope":
        raise SetupError("Ollama intent warm-up failed. Check its logs and available memory; on a Mac use native Ollama for GPU acceleration. Re-run setup to retry.")
    log(f"Local intent classifier ready ({time.monotonic() - started:.1f}s).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-only", action="store_true", help="restore/validate data without model downloads")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    data = args.root / "data"
    try:
        import fcntl
        from config.model_version import MODEL_VERSION

        data.mkdir(parents=True, exist_ok=True)
        with (data / ".docker-setup.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            prepare_data(data, MODEL_VERSION)
            if not args.data_only:
                prepare_models(args.root)
                prepare_search_model()
                prepare_search_cache(data)
                prepare_ollama(os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"))
                if os.environ.get("PLP_WARM_INTENT", "1").strip().lower() not in ("0", "false", "no"):
                    warm_intent()
        log("Setup complete. FastAPI and the dashboard can now start.")
        return 0
    except (SetupError, OSError) as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
