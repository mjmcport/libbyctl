import json

import pytest
from typer.testing import CliRunner

from libbyctl.cli.app import app
from libbyctl.domain.models import CatalogItem, Library
from libbyctl.exceptions import LibbyCtlError
from libbyctl.services.reading_lists import ReadingListItem, match_item, parse_list
from libbyctl.storage.reading_lists import load_list


def test_booker_csv_imports_thirteen_items_without_account_access(monkeypatch, tmp_path):
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "examples/booker-2026-longlist.csv"
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path))
    result = CliRunner().invoke(app, ["lists", "import", str(source), "--name", "Booker 2026"])
    assert result.exit_code == 0
    name, items = load_list(tmp_path / "libbyctl.db", "booker-2026")
    assert name == "Booker 2026"
    assert len(items) == 13
    assert items[0] == ReadingListItem("The Shadow of the Object", "Chloe Aridjis")


def test_isbn_import_rejects_bad_check_digit():
    assert parse_list("0-306-40615-2", "isbn") == [ReadingListItem(isbn="0306406152")]
    with pytest.raises(LibbyCtlError, match="Invalid ISBN"):
        parse_list("0-306-40615-3", "isbn")


def test_match_groups_editions_across_libraries_and_flags_ambiguity():
    libraries = [
        Library(website_id=1, name="One", key="one"),
        Library(website_id=2, name="Two", key="two"),
    ]
    exact = CatalogItem(id="e1", title="The Palm House", creators=["Gwendoline Riley"])
    other_edition = CatalogItem(id="e2", title="The Palm House", creators=["Gwendoline Riley"])
    match = match_item(
        ReadingListItem("The Palm House", "Gwendoline Riley"),
        list(zip(libraries, [exact, other_edition], strict=True)),
    )
    assert match.status == "matched"
    assert match.candidates[0].editions == (("one", "e1"), ("two", "e2"))

    alternate = CatalogItem(id="e3", title="The Palm House", creators=["Gwendolyn Riley"])
    ambiguous = match_item(
        ReadingListItem("The Palm House"),
        [(libraries[0], exact), (libraries[0], alternate)],
    )
    assert ambiguous.status == "ambiguous"
    assert len(ambiguous.candidates) == 2


def test_failed_library_marks_match_incomplete():
    match = match_item(ReadingListItem("Switzy"), [], ("one",))
    assert match.status == "incomplete"
    assert match.failed_libraries == ("one",)


def test_list_show_json_is_stable(monkeypatch, tmp_path):
    source = tmp_path / "list.txt"
    source.write_text("The Palm House — Gwendoline Riley\n", encoding="utf-8")
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    assert runner.invoke(app, ["lists", "import", str(source), "--name", "Demo"]).exit_code == 0
    result = runner.invoke(app, ["lists", "show", "demo", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"] == [
        {"title": "The Palm House", "author": "Gwendoline Riley", "isbn": ""}
    ]


def test_url_import_requires_review_and_rejects_local_address(monkeypatch, tmp_path):
    import httpx

    from libbyctl.cli import lists as lists_module

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="title,author\nSwitzy,Emma Cline\n")
    )
    original_client = httpx.Client
    monkeypatch.setattr(
        lists_module.httpx, "Client",
        lambda *args, **kwargs: original_client(transport=transport),
    )
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    url = "https://example.org/books.csv"
    preview = runner.invoke(app, ["lists", "import-url", url, "--name", "Remote"])
    assert preview.exit_code == 0
    assert "Switzy" in preview.stdout
    assert not (tmp_path / "libbyctl.db").exists()
    digest = preview.stdout.split("--confirm ", 1)[1].split()[0]
    confirmed = runner.invoke(
        app, ["lists", "import-url", url, "--name", "Remote", "--confirm", digest]
    )
    assert confirmed.exit_code == 0
    assert len(load_list(tmp_path / "libbyctl.db", "remote")[1]) == 1
    changed = runner.invoke(
        app, ["lists", "import-url", url, "--name", "Changed", "--confirm", "0" * 64]
    )
    assert isinstance(changed.exception, LibbyCtlError)

    rejected = runner.invoke(
        app, ["lists", "import-url", "https://127.0.0.1/books.csv", "--name", "Local"]
    )
    assert isinstance(rejected.exception, LibbyCtlError)
