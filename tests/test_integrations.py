import json

import pytest
from typer.testing import CliRunner

from libbyctl.cli.app import app
from libbyctl.domain.models import PlanEntry, PlanSnapshot, ProposedAction
from libbyctl.storage.plans import save_plan


def _saved_plan(path):
    plan = PlanSnapshot(
        id="safe-plan", list_id="list", list_name="Sample",
        created_at="2026-09-23T00:00:00Z",
        entries=[PlanEntry(
            position=0, title="Private title", card_id="private-card",
            title_id="private-title", action=ProposedAction.HOLD,
        )],
    )
    save_plan(path, plan)


def test_summary_cli_excludes_card_and_title_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path))
    _saved_plan(tmp_path / "libbyctl.db")
    result = CliRunner().invoke(app, ["plans", "summary", "safe-plan", "--json"])
    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert value["actions"] == {"HOLD": 1}
    assert value["schema_version"] == 1
    assert "private-card" not in result.stdout
    assert "Private title" not in result.stdout


def test_mcp_server_exposes_read_only_local_tools(tmp_path, monkeypatch):
    mcp = pytest.importorskip("mcp")
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path))
    _saved_plan(tmp_path / "libbyctl.db")
    from libbyctl.integrations.mcp_server import build_server

    async def inspect():
        async with mcp.Client(build_server()) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {
                "list_saved_plans", "get_plan_summary", "list_candidate_libraries"
            }
            result = await client.call_tool("get_plan_summary", {"plan_id": "safe-plan"})
            assert not result.is_error
            assert "private-card" not in str(result)
            assert "Private title" not in str(result)

    import anyio

    anyio.run(inspect)
