from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER
from backend.services.finn_v2_tool_registry_service import FinnV2ToolRegistryService
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from types import SimpleNamespace
import asyncio


def test_financial_tool_chain_preserves_required_execution_order():
    service = FinnV2ToolRegistryService()

    assert service.ordered_tool_names() == FINN_V2_TOOL_ORDER
    assert FINN_V2_TOOL_ORDER.index("read_active_asset") < FINN_V2_TOOL_ORDER.index("read_market_snapshot")
    assert FINN_V2_TOOL_ORDER.index("read_active_setup") < FINN_V2_TOOL_ORDER.index("read_linked_strategy")
    assert FINN_V2_TOOL_ORDER.index("read_linked_strategy") < FINN_V2_TOOL_ORDER.index("read_linked_bot")


def test_setup_strategy_bot_linkage_stays_user_scoped(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(
        service.setups,
        "get_setup_by_id",
        lambda setup_id, user_id: asyncio.sleep(0, result={"id": setup_id, "symbol": "BTC"} if user_id == 7 else None),
    )
    monkeypatch.setattr(
        service.strategies,
        "get_raw_strategy_with_setup",
        lambda strategy_id, user_id: asyncio.sleep(0, result={"id": strategy_id, "setup_id": 11} if user_id == 7 else None),
    )
    monkeypatch.setattr(
        service.bots,
        "get_bot_config",
        lambda user_id, bot_id: asyncio.sleep(0, result={"id": bot_id, "strategy_id": 22} if user_id == 7 else None),
    )

    setup = asyncio.run(service.resolve_setup(user_id=7, selector={"setup_id": 11}, asset="BTC"))
    strategy = asyncio.run(service.resolve_strategy(user_id=7, selector={"strategy_id": 22}, setup=setup["setup"]))
    bot = asyncio.run(service.resolve_bot(user_id=7, selector={"bot_id": 33}, strategy=strategy["strategy"]))

    assert setup["setup"]["id"] == 11
    assert strategy["strategy"]["setup_id"] == 11
    assert bot["bot"]["strategy_id"] == 22
