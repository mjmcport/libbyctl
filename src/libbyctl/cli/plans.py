"""Read-only plan creation, inspection, and refresh commands."""

from __future__ import annotations

import json
from collections import Counter
from itertools import zip_longest
from typing import Annotated

import typer

from libbyctl.domain.models import PlanSnapshot
from libbyctl.services.planner import build_plan
from libbyctl.storage.plans import list_plans, load_plan, save_plan
from libbyctl.storage.reading_lists import load_list

app = typer.Typer(no_args_is_help=True, help="Inspect and refresh saved plans.")


def _create(list_id: str, *, parent_id: str | None = None) -> PlanSnapshot:
    from libbyctl.cli.app import _load_account
    from libbyctl.services.account import (
        cards_from_sync,
        require_resolved_libraries,
        website_ids_from_sync,
    )

    settings, _, libby, catalog, sync = _load_account()
    try:
        name, items = load_list(settings.database_path, list_id)
        websites = website_ids_from_sync(sync)
        libraries = catalog.libraries_by_website_ids(websites)
        require_resolved_libraries(websites, libraries)
        cards = cards_from_sync(sync, libraries)
        plan = build_plan(
            list_id, name, items, sync, cards, libraries, catalog,
            settings.preferred_formats, parent_id=parent_id,
        )
    finally:
        libby.close()
        catalog.close()
    save_plan(settings.database_path, plan)
    return plan


def _display(plan: PlanSnapshot, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(plan.model_dump(mode="json"), indent=2))
        return
    typer.echo(f"Plan {plan.id} for {plan.list_name} ({len(plan.entries)} items)")
    for entry in plan.entries:
        typer.echo(f"{entry.position + 1}. {entry.action}: {entry.title or entry.isbn}")
        for reason in entry.reasons:
            typer.echo(f"   {reason}")
    if plan.warnings:
        typer.echo("Warning: incomplete library searches: " + ", ".join(plan.warnings))


def plan_summary(plan: PlanSnapshot) -> dict:
    """A stable, aggregate view suitable for a local status integration."""
    return {
        "schema_version": 1,
        "plan_id": plan.id,
        "list_name": plan.list_name,
        "created_at": plan.created_at,
        "items": len(plan.entries),
        "actions": dict(Counter(entry.action.value for entry in plan.entries)),
        "incomplete_libraries": len(plan.warnings),
    }


@app.command("summary")
def show_summary(
    plan_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show an aggregate plan status without card or title identifiers."""
    from libbyctl.config.settings import Settings

    summary = plan_summary(load_plan(Settings.load().database_path, plan_id))
    if json_output:
        typer.echo(json.dumps(summary, indent=2))
    else:
        typer.echo(
            f"{summary['list_name']}: {summary['items']} items; "
            + ", ".join(f"{key} {count}" for key, count in summary["actions"].items())
        )


def create_plan(
    list_id: Annotated[str, typer.Argument(help="Saved reading-list ID")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create and save a read-only plan for a reading list."""
    _display(_create(list_id), json_output)


@app.command("show")
def show_plan(
    plan_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a saved plan without refreshing account or catalog state."""
    from libbyctl.config.settings import Settings

    _display(load_plan(Settings.load().database_path, plan_id), json_output)


@app.command("list")
def show_plans() -> None:
    """List saved plan snapshots."""
    from libbyctl.config.settings import Settings

    for plan_id, name, created_at in list_plans(Settings.load().database_path):
        typer.echo(f"{plan_id}  {created_at}  {name}")


@app.command("refresh")
def refresh_plan(
    plan_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a new snapshot from current account and catalog state."""
    from libbyctl.config.settings import Settings

    previous = load_plan(Settings.load().database_path, plan_id)
    current = _create(previous.list_id, parent_id=previous.id)
    changes = [
        {
            "position": (
                now.position if now is not None
                else old.position if old is not None else -1
            ),
            "before": old.action if old else None,
            "after": now.action if now else None,
        }
        for old, now in zip_longest(previous.entries, current.entries)
        if old is None or now is None
        or (old.action, old.title, old.title_id, old.card_id)
        != (now.action, now.title, now.title_id, now.card_id)
    ]
    if json_output:
        typer.echo(json.dumps(
            {"plan": current.model_dump(mode="json"), "changes": changes}, indent=2,
        ))
    else:
        typer.echo(f"Refreshed plan {current.id} from {previous.id}; {len(changes)} changed items.")
        _display(current, False)
