from __future__ import annotations

from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER, ToolDefinition


class FinnV2ToolRegistryService:
    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(name="read_profile", description="Read normalized trader profile."),
            ToolDefinition(name="read_user_preferences", description="Read stored FINN user preferences."),
            ToolDefinition(name="read_active_asset", description="Resolve the active asset context."),
            ToolDefinition(name="read_indicator_configuration", description="Read indicator preferences for the resolved asset."),
            ToolDefinition(name="read_asset_scores", description="Read the latest stored asset scores.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_market_snapshot", description="Read the latest market snapshot.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_macro_snapshot", description="Read the latest macro snapshot.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_technical_snapshot", description="Read the latest technical snapshot.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_active_setup", description="Read the active setup for the resolved asset.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_linked_strategy", description="Read the strategy linked to the active setup.", depends_on=["read_active_setup"]),
            ToolDefinition(name="read_linked_bot", description="Read the bot linked to the strategy.", depends_on=["read_linked_strategy"]),
            ToolDefinition(name="read_bot_status", description="Read the runtime status of the linked bot.", depends_on=["read_linked_bot"]),
            ToolDefinition(name="read_watchlist", description="Read the current user watchlist and whether the selected asset is already present.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_portfolio", description="Read the compact portfolio state."),
            ToolDefinition(name="read_latest_report", description="Read compact metadata for the latest report.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_review_history", description="Read review history when available.", depends_on=["read_active_asset"]),
        ]

    def get_tool(self, tool_name: str) -> ToolDefinition:
        for tool in self.list_tools():
            if tool.name == tool_name:
                return tool
        raise KeyError("tool_unknown")

    def ordered_tool_names(self) -> list[str]:
        return list(FINN_V2_TOOL_ORDER)
