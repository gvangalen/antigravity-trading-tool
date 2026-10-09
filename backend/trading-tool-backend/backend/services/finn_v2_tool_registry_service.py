from __future__ import annotations

from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER, ToolDefinition


class FinnV2ToolRegistryService:
    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(name="read_profile", description="Read normalized trader profile."),
            ToolDefinition(name="read_user_preferences", description="Read stored FINN user preferences."),
            ToolDefinition(name="read_active_asset", description="Resolve the active asset context."),
            ToolDefinition(name="read_indicator_configuration", description="Read the owner's saved market, macro and technical indicator configuration for the resolved asset, including empty categories. This proves what is configured, not current indicator values."),
            ToolDefinition(name="read_asset_scores", description="Read current source-verified market, macro and technical scores and the weighted benchmark. Missing or stale components remain null; no historical score fallback.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_setup_market_matches", description="Compare saved setups with today's verified market, macro and technical scores. Pass an asset for one asset; omit it to inspect all of the owner's setup assets. Returns the owner's current Analyse-weighted total benchmark separately from each setup's weighted condition fit, match status and source date. A match is not an entry signal."),
            ToolDefinition(name="read_market_snapshot", description="Read the latest price and the owner's saved daily market score for the explicitly requested asset. Price time and score report date are separate. A saved score is not proof that all benchmark source indicators are fresh; use read_setup_market_matches for a verified current match. For a question comparing current prices of multiple assets, call this separately for each asset.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_macro_snapshot", description="Read the latest macro snapshot.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_technical_snapshot", description="Read current measured technical indicator values for the resolved asset, when a fresh source is available. This is distinct from saved indicator configuration.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_active_setup", description="Read the owner's saved setup, including its market, macro and technical score boundaries and optional user-written description. These setup fields can be read without selecting a linked strategy. The description is the user's rationale, not a verified entry condition or strategy rule.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_saved_setup_inventory", description="Read the complete owner-scoped list of saved setups and their optional user-written descriptions, optionally filtered by asset. Descriptions are rationale, not verified entry conditions. Use this for counts, names, comparisons and questions about any of several setups; no active setup is selected."),
            ToolDefinition(name="read_linked_strategies", description="Read all owner-scoped strategies linked to the selected saved setup, including names and their distinct stored amount and trade fields. This collection never selects one strategy for an action.", depends_on=["read_active_setup"]),
            ToolDefinition(name="read_linked_strategy", description="Read the strategy linked to the active setup.", depends_on=["read_active_setup"]),
            ToolDefinition(name="read_linked_bot", description="Read the bot linked to the strategy.", depends_on=["read_linked_strategy"]),
            ToolDefinition(name="read_bot_status", description="Read the runtime status of the linked bot.", depends_on=["read_linked_bot"]),
            ToolDefinition(name="read_watchlist", description="Read the current user watchlist and whether the selected asset is already present.", depends_on=["read_active_asset"]),
            ToolDefinition(
                name="read_portfolio",
                description=(
                    "Read owner-scoped Paper-bot portfolio valuation, budgets, balances and exposure. "
                    "This source does not contain trade transaction history, tax records or tax calculations."
                ),
            ),
            ToolDefinition(name="read_latest_report", description="Read compact metadata for the latest report.", depends_on=["read_active_asset"]),
            ToolDefinition(name="read_review_history", description="Read historical reviews and decisions when available, not recently saved setup or strategy details.", depends_on=["read_active_asset"]),
        ]

    def get_tool(self, tool_name: str) -> ToolDefinition:
        for tool in self.list_tools():
            if tool.name == tool_name:
                return tool
        raise KeyError("tool_unknown")

    def ordered_tool_names(self) -> list[str]:
        return list(FINN_V2_TOOL_ORDER)
