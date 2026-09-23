from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_lists (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_list_items (
                list_id TEXT NOT NULL REFERENCES reading_lists(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                author TEXT,
                isbn TEXT,
                PRIMARY KEY (list_id, position)
            );
            """
        )
        db.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        db.commit()


def database_ok(path: Path) -> bool:
    try:
        initialize_database(path)
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        return bool(row and row[0] == str(SCHEMA_VERSION))
    except sqlite3.Error:
        return False
