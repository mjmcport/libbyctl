import pytest
from typer.testing import CliRunner

from libbyctl import cli
from libbyctl.cli.app import app
from libbyctl.cli.circulation import _select_card
from libbyctl.domain.models import Card
from libbyctl.exceptions import LibbyCtlError

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "libbyctl 0.1.0" in result.stdout


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Search and plan Libby access" in result.stdout


def test_main_reports_cli_errors_without_traceback(monkeypatch, capsys):
    def raise_cli_error():
        raise LibbyCtlError("Libby is not connected. Run: libbyctl setup")

    monkeypatch.setattr(cli.app, "app", raise_cli_error)
    with pytest.raises(SystemExit) as result:
        cli.app.main()

    assert result.value.code == 2
    captured = capsys.readouterr()
    assert "Libby is not connected" in captured.err
    assert captured.out == ""


def test_hold_selects_linked_partner_card_by_library_key():
    cards = [
        Card(id="home", library_key="minuteman"),
        Card(id="visitor", library_key="bpl"),
    ]
    assert _select_card(cards, None, "BPL").id == "visitor"
    with pytest.raises(LibbyCtlError, match="visitor-card setup"):
        _select_card(cards, None, "mvlc")
    with pytest.raises(LibbyCtlError, match="different cards"):
        _select_card(cards, 1, "bpl")


def test_hold_requires_card_number_when_same_library_has_multiple_cards():
    cards = [Card(id="a", library_key="bpl"), Card(id="b", library_key="bpl")]
    with pytest.raises(LibbyCtlError, match="More than one card"):
        _select_card(cards, None, "bpl")
    assert _select_card(cards, 2, "bpl").id == "b"
