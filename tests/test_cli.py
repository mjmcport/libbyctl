import pytest
from typer.testing import CliRunner

from libbyctl import cli
from libbyctl.cli.app import app
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
