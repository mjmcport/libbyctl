"""Persist plan snapshots as versioned JSON records."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from libbyctl.domain.models import PlanSnapshot
from libbyctl.exceptions import LibbyCtlError
from libbyctl.storage.database import initialize_database


def save_plan(path: Path, plan: PlanSnapshot) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO plans(id, name, created_at, payload_json) VALUES (?, ?, ?, ?)",
            (plan.id, plan.list_name, plan.created_at, plan.model_dump_json()),
        )


def load_plan(path: Path, plan_id: str) -> PlanSnapshot:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT payload_json FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        raise LibbyCtlError(f"Plan '{plan_id}' was not found.")
    return PlanSnapshot.model_validate_json(row[0])


def list_plans(path: Path) -> list[tuple[str, str, str]]:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT id, name, created_at FROM plans ORDER BY created_at DESC"
        ).fetchall()
