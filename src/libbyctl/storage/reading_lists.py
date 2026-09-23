"""Local storage for imported reading lists; no account data is stored here."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from libbyctl.exceptions import LibbyCtlError
from libbyctl.services.reading_lists import ReadingListItem
from libbyctl.storage.database import initialize_database


def save_list(
    path: Path, list_id: str, name: str, source: str, items: list[ReadingListItem]
) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        if db.execute("SELECT 1 FROM reading_lists WHERE id=?", (list_id,)).fetchone():
            raise LibbyCtlError(f"List '{list_id}' already exists. Choose another name.")
        db.execute(
            "INSERT INTO reading_lists(id, name, source, imported_at) VALUES (?, ?, ?, ?)",
            (list_id, name, source, datetime.now(UTC).isoformat()),
        )
        db.executemany(
            "INSERT INTO reading_list_items(list_id, position, title, author, isbn) "
            "VALUES (?, ?, ?, ?, ?)",
            [(list_id, i, item.title, item.author, item.isbn) for i, item in enumerate(items)],
        )


def load_list(path: Path, list_id: str) -> tuple[str, list[ReadingListItem]]:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT name FROM reading_lists WHERE id=?", (list_id,)).fetchone()
        if not row:
            raise LibbyCtlError(f"List '{list_id}' was not found.")
        rows = db.execute(
            "SELECT title, author, isbn FROM reading_list_items "
            "WHERE list_id=? ORDER BY position", (list_id,),
        ).fetchall()
    return row[0], [ReadingListItem(*value) for value in rows]
