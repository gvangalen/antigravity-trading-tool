import asyncio

from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService


class _FakeSetupRepo:
    async def get_setup_by_id(self, setup_id, user_id):
        if setup_id == 293 and user_id == 388:
            return {"id": 293, "symbol": "BTC", "timeframe": "4H"}
        return None

    async def get_active_setup(self, user_id):
        if user_id == 388:
            return {"setup_id": 293, "symbol": "BTC", "timeframe": "4H"}
        return None

    async def get_user_setups(self, user_id):
        if user_id == 389:
            return [{"id": 294, "symbol": "AAPL", "timeframe": "1D"}]
        return []


class _FakeStrategyRepo:
    async def get_raw_strategy_with_setup(self, strategy_id, user_id):
        if strategy_id == 309 and user_id == 388:
            return {"id": 309, "setup_id": 293, "setup_symbol": "BTC"}
        return None

    async def query_strategies(self, user_id, _filters):
        if user_id == 388:
            return [
                {"id": 309, "name": "Matrix Strategy", "setup_id": 293},
                {"id": 310, "name": "Other Strategy", "setup_id": 293},
            ]
        return []


class _FakeBotRepo:
    async def get_bot_config(self, user_id, bot_id):
        if user_id == 388 and bot_id == 170:
            return {"id": 170, "strategy_id": 309, "symbol": "BTC"}
        return None

    async def get_bot_configs(self, user_id):
        if user_id == 388:
            return [{"id": 170, "name": "Matrix Bot", "strategy_id": 309}]
        return []


def test_entity_resolution_prefers_explicit_graph_links_for_asset():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()

    from_setup = asyncio.run(service.resolve_asset(user_id=388, selector={"setup_id": 293}, workspace_hints={"workspace_asset": "AAPL"}, client_context={}))
    from_strategy = asyncio.run(service.resolve_asset(user_id=388, selector={"strategy_id": 309}, workspace_hints={"workspace_asset": "AAPL"}, client_context={}))
    from_bot = asyncio.run(service.resolve_asset(user_id=388, selector={"bot_id": 170}, workspace_hints={"workspace_asset": "AAPL"}, client_context={}))

    assert from_setup == {"asset": "BTC", "resolution_source": "explicit_setup_link"}
    assert from_strategy == {"asset": "BTC", "resolution_source": "explicit_strategy_link"}
    assert from_bot == {"asset": "BTC", "resolution_source": "explicit_bot_link"}


def test_entity_resolution_can_resolve_setup_without_explicit_asset():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()

    active = asyncio.run(service.resolve_setup(user_id=388, selector={}, asset=None))
    single = asyncio.run(service.resolve_setup(user_id=389, selector={}, asset=None))

    assert active["setup"]["setup_id"] == 293
    assert active["resolution_source"] == "active_setup"
    assert single["setup"]["id"] == 294
    assert single["resolution_source"] == "single_user_setup"


def test_entity_resolution_selects_the_asset_specific_active_setup_before_other_candidates():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()

    service.setups.get_active_setup = lambda _user_id: asyncio.sleep(0, result={"setup_id": 293, "symbol": "BTC"})
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 294, "symbol": "ETH", "is_active": True},
        {"id": 295, "symbol": "ETH"},
    ])

    resolved = asyncio.run(service.resolve_setup(user_id=388, selector={}, asset="ETH"))

    assert resolved == {
        "setup": {"id": 294, "symbol": "ETH", "is_active": True},
        "resolution_source": "asset_active_setup",
    }


def test_entity_resolution_resolves_explicit_quoted_names_owner_scoped():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 293, "name": "Matrix Setup", "symbol": "BTC"},
    ])

    setup = asyncio.run(service.resolve_setup(user_id=388, selector={"setup_name": "matrix setup"}, asset=None))
    strategy = asyncio.run(service.resolve_strategy(user_id=388, selector={"strategy_name": "MATRIX STRATEGY"}, setup=None))
    bot = asyncio.run(service.resolve_bot(user_id=388, selector={"bot_name": "matrix bot"}, strategy=None))

    assert setup["setup"]["id"] == 293
    assert setup["resolution_source"] == "explicit_setup_name"
    assert strategy["strategy"]["id"] == 309
    assert strategy["resolution_source"] == "explicit_strategy_name"
    assert bot["bot"]["id"] == 170
    assert bot["resolution_source"] == "explicit_bot_name"


def test_entity_resolution_projects_only_registry_required_named_ids():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 293, "name": "Matrix Setup", "symbol": "BTC"},
    ])

    resolved = asyncio.run(service.resolve_contract_reference_inputs(
        user_id=388,
        selector={
            "setup_name": "Matrix Setup",
            "strategy_name": "Matrix Strategy",
            "bot_name": "Matrix Bot",
        },
        required_inputs=("setup_id", "strategy_id", "bot_id"),
    ))

    assert resolved == {"setup_id": 293, "strategy_id": 309, "bot_id": 170}


def test_entity_resolution_resolves_unquoted_owner_scoped_names_from_user_message():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 293, "name": "Matrix Setup", "symbol": "BTC"},
    ])

    resolved = asyncio.run(service.resolve_contract_reference_inputs(
        user_id=388,
        selector={},
        required_inputs=("setup_id", "strategy_id", "bot_id"),
        message="Werk Matrix Setup, Matrix Strategy en Matrix Bot vandaag bij.",
    ))

    assert resolved == {"setup_id": 293, "strategy_id": 309, "bot_id": 170}


def test_entity_resolution_rejects_ambiguous_explicit_quoted_name():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 1, "name": "Duplicate"},
        {"id": 2, "name": "duplicate"},
    ])

    try:
        asyncio.run(service.resolve_setup(user_id=388, selector={"setup_name": "Duplicate"}, asset=None))
    except LookupError as exc:
        assert str(exc) == "setup_ambiguous"
    else:
        raise AssertionError("ambiguous owner-scoped name must not resolve")


def test_entity_resolution_follows_explicit_child_identity_to_its_parent_setup():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()

    from_strategy = asyncio.run(
        service.resolve_setup(user_id=388, selector={"strategy_name": "Matrix Strategy"}, asset=None)
    )
    from_bot = asyncio.run(
        service.resolve_setup(user_id=388, selector={"bot_name": "Matrix Bot"}, asset=None)
    )
    strategy_from_bot = asyncio.run(
        service.resolve_strategy(user_id=388, selector={"bot_name": "Matrix Bot"}, setup=None)
    )

    assert from_strategy["setup"]["id"] == 293
    assert from_strategy["resolution_source"] == "explicit_strategy_link"
    assert from_bot["setup"]["id"] == 293
    assert from_bot["resolution_source"] == "explicit_bot_link"
    assert strategy_from_bot["strategy"]["id"] == 309
    assert strategy_from_bot["resolution_source"] == "explicit_bot_link"
