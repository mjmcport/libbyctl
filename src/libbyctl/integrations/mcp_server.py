"""Optional local MCP stdio server with read-only stored-data tools."""

from __future__ import annotations

from libbyctl.cli.plans import plan_summary
from libbyctl.config.settings import Settings
from libbyctl.exceptions import LibbyCtlError
from libbyctl.storage.plans import list_plans, load_plan
from libbyctl.storage.registry import load_candidates


def build_server():
    try:
        from mcp.server import MCPServer
    except ImportError:
        raise LibbyCtlError("MCP support is not installed. Install libbyctl[mcp].") from None

    server = MCPServer("libbyctl")

    @server.tool()
    def list_saved_plans() -> list[dict[str, str]]:
        """List locally saved reading plans without contacting Libby."""
        return [
            {"id": plan_id, "name": name, "created_at": created_at}
            for plan_id, name, created_at in list_plans(Settings.load().database_path)
        ]

    @server.tool()
    def get_plan_summary(plan_id: str) -> dict:
        """Return aggregate proposed action counts; no card or title IDs."""
        return plan_summary(load_plan(Settings.load().database_path, plan_id))

    @server.tool()
    def list_candidate_libraries() -> list[dict]:
        """List locally reviewed library candidates and their source dates."""
        return [value.model_dump(mode="json")
                for value in load_candidates(Settings.load().database_path)]

    return server


def run() -> None:
    build_server().run(transport="stdio")
