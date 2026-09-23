import json
from datetime import datetime, timedelta

import pytest
from typer.testing import CliRunner

from libbyctl.cli.app import app
from libbyctl.exceptions import LibbyCtlError
from libbyctl.services.timeline import summarize_timeline


def test_timeline_counts_borrows_and_returns_by_library(tmp_path):
    export = tmp_path / "timeline.csv"
    # CSV fields containing commas are quoted in Libby's actual export.
    export.write_text(
        "Cover,Title,Author,Publisher,Isbn,Date,Activity,Details,Library\n"
        ',Pride and Prejudice,Jane Austen,,,"September 23, 2026 09:00",'
        'Borrowed,21 days,City Library\n'
        ',Pride and Prejudice,Jane Austen,,,"September 23, 2026 10:00",Returned,,City Library\n'
        ',Emma,Jane Austen,,,"September 22, 2026 12:00",Borrowed,21 days,County Library\n'
        ',Emma,Jane Austen,,,"September 22, 2026 13:00",Renewed,,County Library\n'
        ',Old book,Jane Austen,,,"September 15, 2026 09:00",Borrowed,21 days,County Library\n',
        encoding="utf-8",
    )
    report = summarize_timeline(export, now=datetime(2026, 9, 23, 12))
    assert (report.borrowed, report.returned) == (2, 1)
    assert report.by_library == {
        "City Library": {"borrowed": 1, "returned": 1},
        "County Library": {"borrowed": 1, "returned": 0},
    }
    assert [event.activity for event in report.events] == ["returned", "borrowed", "borrowed"]


def test_timeline_rejects_missing_columns_and_unreadable_dates(tmp_path):
    export = tmp_path / "timeline.csv"
    export.write_text("Title,Date,Activity\nBook,2026-09-23,Borrowed\n", encoding="utf-8")
    with pytest.raises(LibbyCtlError, match="Library columns"):
        summarize_timeline(export)

    export.write_text("Title,Date,Activity,Library\nBook,not a date,Borrowed,Library\n")
    with pytest.raises(LibbyCtlError, match="row 2"):
        summarize_timeline(export)


def test_timeline_cli_json_is_aggregate_only(tmp_path):
    export = tmp_path / "timeline.csv"
    export.write_text(
        "Title,Date,Activity,Library\n"
        f"Private title,{datetime.now() - timedelta(days=1):%Y-%m-%d %H:%M},"
        "Borrowed,City Library\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["circulation", "activity", str(export), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert set(parsed) == {"since", "until", "borrowed", "returned", "by_library"}
    assert parsed["borrowed"] == 1
    assert "Private title" not in result.stdout
