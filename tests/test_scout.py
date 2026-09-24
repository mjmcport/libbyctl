import json
from datetime import date

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from libbyctl.cli.app import app
from libbyctl.domain.models import (
    Availability,
    CatalogItem,
    PlanEntry,
    PlanSnapshot,
    ProposedAction,
)
from libbyctl.services.reading_lists import ReadingListItem
from libbyctl.services.scout import CandidateLibrary, compare_candidate, rank_comparisons
from libbyctl.storage.registry import load_candidates, save_candidates


class Catalog:
    def search_library(self, key, query, *, per_page):
        if query == "Missing":
            return [CatalogItem(id="one", title="Missing", creators=["Writer"],
                                media_type="ebook")]
        if query == "Waiting":
            return [CatalogItem(id="two", title="Waiting", creators=["Writer"],
                                media_type="audiobook")]
        return []

    def availability(self, key, title_id):
        return Availability(
            library_key=key, title_id=title_id, owned_copies=1,
            is_available=title_id == "one", estimated_wait_days=0 if title_id == "one" else 5,
        )


def candidate(**changes):
    values = dict(
        name="Example Library", library_key="example", eligibility_area="Michigan",
        eligibility_rule="Residents may apply; verify current terms on the official site.",
        membership_fee_usd=25, term_months=12, online_join=True, libby_access=True,
        official_source_url="https://example.org/library-card", verified_on=date(2026, 9, 23),
    )
    values.update(changes)
    return CandidateLibrary(**values)


def test_source_validation_and_registry_round_trip(tmp_path):
    with pytest.raises(ValidationError):
        candidate(official_source_url="http://example.org/library-card")
    with pytest.raises(ValidationError):
        candidate(membership_fee_usd=-1)
    path = tmp_path / "registry.db"
    save_candidates(path, [candidate()])
    assert load_candidates(path) == [candidate()]


def test_scout_reports_marginal_value_and_unverified_eligibility():
    baseline = PlanSnapshot(
        id="plan", list_id="list", list_name="List", created_at="2026-09-23T00:00:00Z",
        entries=[
            PlanEntry(position=0, title="Missing", author="Writer",
                      action=ProposedAction.NOT_OWNED),
            PlanEntry(position=1, title="Waiting", author="Writer",
                      action=ProposedAction.HOLD, estimated_wait_days=21),
        ],
    )
    items = [ReadingListItem("Missing", "Writer"), ReadingListItem("Waiting", "Writer")]
    result = compare_candidate(candidate(), items, baseline, Catalog(), ["audiobook"], area="Ohio")
    assert result.eligibility_status == "eligibility_unverified"
    assert result.newly_covered == 1
    assert result.newly_available_now == 1
    assert result.improved_waits == 1
    assert result.preferred_format_coverage == 1
    assert result.failures == 0
    assert result.source_age_days >= 0
    assert rank_comparisons([result]) == [result]


def test_registry_cli_import_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path / "data"))
    source = tmp_path / "candidates.json"
    source.write_text(json.dumps([candidate().model_dump(mode="json")]))
    runner = CliRunner()
    imported = runner.invoke(app, ["libraries", "import", str(source)])
    assert imported.exit_code == 0
    listed = runner.invoke(app, ["libraries", "list"])
    assert listed.exit_code == 0
    assert "https://example.org/library-card" in listed.stdout
