"""Prepare persistent search vectors using only the already-downloaded model."""

import argparse
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import tempfile

import numpy as np

from config.search_model import WIDTH
from docker.bootstrap import SetupError, log, validate_embeddings


def prepare(data: Path) -> dict:
    data = data.resolve()
    path = data / "search_embeddings.npz"
    database = data / "plp.db"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
        expected_ids = {row[0] for row in conn.execute("SELECT sentence_id FROM sentences")}
    reusable = False
    if path.is_file():
        try:
            validate_embeddings(path, expected_ids, width=WIDTH, allow_stale=True)
            with np.load(path, allow_pickle=False) as cache:
                held_ids = set(cache["sentence_ids"].tolist())
            if held_ids == expected_ids:
                log(f"Search cache ready: {len(held_ids):,} vectors reused; no rebuild needed.")
                return {"already_cached": len(held_ids), "newly_embedded": 0,
                        "pruned_stale": 0, "total": len(held_ids)}
            reusable = True
        except SetupError:
            log("Search cache is invalid; rebuilding it from the database.")
    log("Preparing MiniLM search vectors. First-time generation can take several minutes; no hosted API is called.")
    from chatbot import search_vectors
    from config.logging_config import setup_logging
    from ingest import db

    setup_logging()
    previous_database, previous_store = db.DB_PATH, search_vectors.STORE_PATH
    try:
        db.DB_PATH = str(database)
        with tempfile.TemporaryDirectory(dir=data, prefix=".search-") as workspace:
            # Never replace an invalid old cache until the new one is complete.
            target = path if reusable else Path(workspace) / path.name
            search_vectors.STORE_PATH = str(target)
            stats = search_vectors.update()
            count = validate_embeddings(target, expected_ids, width=WIDTH)
            if count != len(expected_ids):
                raise SetupError("Search cache preparation left sentences without vectors.")
            if target != path:
                os.replace(target, path)
    finally:
        db.DB_PATH, search_vectors.STORE_PATH = previous_database, previous_store
    log(f"Search cache ready: {stats['total']:,} vectors; {stats['newly_embedded']:,} newly embedded.")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.data)
        return 0
    except (OSError, ValueError, sqlite3.Error, SetupError) as exc:
        log(f"ERROR: Cannot prepare search vectors ({type(exc).__name__}). Check the cached MiniLM model and available disk space, then retry setup.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
