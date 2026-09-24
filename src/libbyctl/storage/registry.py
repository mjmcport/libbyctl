"""Local, user-reviewed registry records with provenance attached."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from libbyctl.services.scout import CandidateLibrary
from libbyctl.storage.database import initialize_database


def save_candidates(path: Path, candidates: list[CandidateLibrary]) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        db.executemany(
            """INSERT INTO candidate_libraries(library_key, payload_json) VALUES (?, ?)
               ON CONFLICT(library_key) DO UPDATE SET payload_json=excluded.payload_json""",
            [(candidate.library_key, candidate.model_dump_json()) for candidate in candidates],
        )


def load_candidates(path: Path) -> list[CandidateLibrary]:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT payload_json FROM candidate_libraries ORDER BY library_key"
        ).fetchall()
    return [CandidateLibrary.model_validate_json(row[0]) for row in rows]
