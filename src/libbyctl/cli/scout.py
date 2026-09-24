"""Import sourced membership records and compare their public catalogs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from libbyctl.config.settings import Settings
from libbyctl.exceptions import LibbyCtlError
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.services.scout import CandidateLibrary, compare_candidate, rank_comparisons
from libbyctl.storage.plans import list_plans, load_plan
from libbyctl.storage.reading_lists import load_list
from libbyctl.storage.registry import load_candidates, save_candidates

app = typer.Typer(no_args_is_help=True, help="Manage sourced candidate library records.")


@app.command("connected")
def connected_library_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List home and partner collections available through saved cards."""
    from libbyctl.cli.app import _load_account
    from libbyctl.services.connected_libraries import connected_libraries

    _, _, libby, catalog, sync = _load_account()
    try:
        entries = connected_libraries(sync, catalog)
    finally:
        libby.close()
        catalog.close()
    if json_output:
        typer.echo(json.dumps([
            {
                "name": entry.library.name,
                "key": entry.library.key,
                "website_id": entry.library.website_id,
                "access": entry.access,
                "via_home_keys": list(entry.via_home_keys),
            }
            for entry in entries
        ], indent=2))
        return
    home_names = {
        entry.library.key: entry.library.name
        for entry in entries if entry.access == "home"
    }
    homes = [entry for entry in entries if entry.access == "home"]
    partners = [entry for entry in entries if entry.access == "partner"]
    typer.echo(f"{len(homes)} home collection(s), {len(partners)} partner collection(s)")
    for entry in homes:
        typer.echo(f"Home: {entry.library.name} ({entry.library.key})")
    for entry in partners:
        via = ", ".join(home_names[key] for key in entry.via_home_keys)
        typer.echo(f"Partner: {entry.library.name} ({entry.library.key}) — via {via}")


@app.command("import")
def import_registry(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)],
) -> None:
    """Import reviewed JSON records with official eligibility and fee sources."""
    if path.stat().st_size > 1_000_000:
        raise LibbyCtlError("Library registry file is limited to 1 MB.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise LibbyCtlError("Library registry must be a JSON array.")
        candidates = [CandidateLibrary.model_validate(value) for value in raw]
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        raise LibbyCtlError(f"Library registry is invalid: {exc}") from None
    if len({candidate.library_key for candidate in candidates}) != len(candidates):
        raise LibbyCtlError("Library registry has duplicate catalog keys.")
    save_candidates(Settings.load().database_path, candidates)
    typer.echo(f"Saved {len(candidates)} sourced library record(s).")


@app.command("list")
def list_registry() -> None:
    """Show stored candidates and their source verification dates."""
    for candidate in load_candidates(Settings.load().database_path):
        typer.echo(
            f"{candidate.library_key}: {candidate.name} — "
            f"verified {candidate.verified_on} — {candidate.official_source_url}"
        )


def scout(
    list_id: Annotated[str, typer.Argument(help="Saved reading-list ID")],
    plan_id: Annotated[
        str | None, typer.Option(help="Saved plan to compare against; defaults to latest for list")
    ] = None,
    area: Annotated[str | None, typer.Option(help="Your eligibility area, if known")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare a list with sourced candidate catalogs; membership still needs verification."""
    settings = Settings.load()
    _, items = load_list(settings.database_path, list_id)
    if plan_id is None:
        for candidate_id, _, _ in list_plans(settings.database_path):
            if load_plan(settings.database_path, candidate_id).list_id == list_id:
                plan_id = candidate_id
                break
    if plan_id is None:
        raise LibbyCtlError("Create a plan for this list first: libbyctl plan " + list_id)
    baseline = load_plan(settings.database_path, plan_id)
    if baseline.list_id != list_id:
        raise LibbyCtlError("The selected plan belongs to a different reading list.")
    candidates = [candidate for candidate in load_candidates(settings.database_path)
                  if candidate.libby_access]
    if not candidates:
        raise LibbyCtlError("No sourced Libby candidate libraries saved. Import a registry first.")
    with ThunderCatalogProvider(
        settings.thunder_base_url, settings.thunder_client_id, settings.timeout_seconds
    ) as catalog:
        comparisons = rank_comparisons([
            compare_candidate(
                candidate, items, baseline, catalog, settings.preferred_formats, area=area
            ) for candidate in candidates
        ])
    if json_output:
        typer.echo(json.dumps([item.model_dump(mode="json") for item in comparisons], indent=2))
        return
    for value in comparisons:
        candidate = value.library
        typer.echo(f"{candidate.name} ({candidate.library_key})")
        typer.echo(
            f"  Newly covered: {value.newly_covered}; available now: "
            f"{value.newly_available_now}; shorter waits: {value.improved_waits}; "
            f"preferred format: {value.preferred_format_coverage}"
        )
        typer.echo(
            f"  Fee: ${candidate.membership_fee_usd:g} for {candidate.term_months} months; "
            f"online join: {'yes' if candidate.online_join else 'no'}"
        )
        typer.echo(
            f"  Eligibility: {value.eligibility_status}. {candidate.eligibility_rule}"
        )
        typer.echo(
            f"  Source: {candidate.official_source_url} (verified {candidate.verified_on}; "
            f"{value.source_age_days} days old)"
        )
        if value.failures:
            typer.echo(f"  Warning: {value.failures} catalog checks were incomplete.")
