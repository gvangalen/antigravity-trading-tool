import asyncio

import pytest

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


def test_create_strategy_auto_uses_exactly_one_owner_scoped_setup():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 293, "name": "Only Setup"},
    ])

    resolved = asyncio.run(service.resolve_contract_reference_inputs(
        user_id=388,
        selector={},
        required_inputs=("setup_id",),
        operation_id="create_strategy",
        message="Maak een strategie.",
    ))

    assert resolved == {"setup_id": 293}


def test_create_bot_requires_a_name_when_multiple_owner_strategies_exist():
    service = FinnV2EntityResolutionService(session=object())
    service.strategies = _FakeStrategyRepo()

    with pytest.raises(LookupError, match="strategy_ambiguous"):
        asyncio.run(service.resolve_contract_reference_inputs(
            user_id=388,
            selector={},
            required_inputs=("strategy_id",),
            operation_id="create_bot",
            message="Maak een paper-bot.",
        ))


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


def test_read_tool_selector_resolves_an_exact_owner_scoped_setup_name():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 12, "name": "Older Setup"},
        {"id": 42, "name": "FINN DCA Flow 1759C"},
    ])

    enriched = asyncio.run(service.enrich_tool_selector_from_message(
        user_id=388,
        selector={},
        message="Vat mijn setup FINN DCA Flow 1759C samen.",
    ))

    assert enriched["setup_id"] == 42


def test_canonical_target_explicit_visible_name_wins_stale_workspace_context():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 12, "name": "Stale Setup", "symbol": "ETH"},
        {"id": 42, "name": "Fresh Setup", "symbol": "BTC", "timeframe": "4H"},
    ])
    service.setups.get_setup_by_id = lambda setup_id, _user_id: asyncio.sleep(
        0,
        result={"id": setup_id, "name": "Stale Setup"} if setup_id == 12 else None,
    )

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="setup",
        message="Pas setup Fresh Setup aan van 4H naar 1D.",
        workspace_hints={"setup_id": 12},
    ))

    assert target.entity_id == 42
    assert target.display_name == "Fresh Setup"
    assert target.resolution_source == "explicit_name"
    assert target.relational_context == {"symbol": "BTC", "timeframe": "4H"}


def test_canonical_target_current_asset_requires_choice_before_stale_context():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 11, "name": "BTC DCA", "symbol": "BTC"},
        {"id": 12, "name": "BTC Swing", "symbol": "BTC"},
        {"id": 13, "name": "ETH Swing", "symbol": "ETH"},
    ])

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="setup",
        selector={"asset": "BTC", "asset_source": "explicit_message"},
        message="Verwijder mijn BTC setup.",
        conversation_context={"canonical_entity_target": {"entity_type": "setup", "entity_id": 13}},
    ))

    assert target.resolution_status == "ambiguous"
    assert target.resolution_source == "explicit_asset"
    assert target.candidate_names == ["BTC DCA", "BTC Swing"]


def test_setup_collection_read_returns_every_owner_asset_match():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 11, "name": "BTC DCA", "symbol": "BTC"},
        {"id": 12, "name": "BTC Swing", "symbol": "BTC"},
        {"id": 13, "name": "ETH Swing", "symbol": "ETH"},
    ])

    selector = asyncio.run(service.enrich_tool_selector_from_message(
        user_id=388,
        selector={"asset": "BTC"},
        message="Welke BTC setups heb ik?",
    ))
    resolved = asyncio.run(service.resolve_setup(user_id=388, selector=selector, asset="BTC"))

    assert selector["setup_collection_requested"] is True
    assert [row["name"] for row in resolved["setups"]] == ["BTC DCA", "BTC Swing"]
    assert resolved["resolution_source"] == "owner_setup_collection"


def test_canonical_target_uses_previous_action_result_before_workspace():
    service = FinnV2EntityResolutionService(session=object())
    service.strategies = _FakeStrategyRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="strategy",
        conversation_context={
            "previous_action_result": {
                "entity_type": "strategy",
                "entity_id": 309,
                "result_status": "succeeded",
            }
        },
        workspace_hints={"strategy_id": 310},
    ))

    assert target.entity_id == 309
    assert target.resolution_source == "previous_action_result"


def test_latest_action_result_wins_over_stale_active_runtime_target():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.setups.get_setup_by_id = lambda setup_id, user_id: asyncio.sleep(
        0,
        result={"id": setup_id, "name": "Apple Setup", "symbol": "AAPL"}
        if user_id == 388 and setup_id == 310 else None,
    )

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="setup",
        conversation_context={
            "previous_action_result": {
                "entity_type": "setup", "entity_id": 310,
                "result_status": "succeeded",
            },
            "canonical_entity_target": {
                "entity_type": "setup", "entity_id": 309, "owner_id": 388,
            },
        },
    ))

    assert target.entity_id == 310
    assert target.resolution_source == "previous_action_result"


def test_latest_action_result_wins_over_contextual_workspace_asset():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.setups.get_user_setups = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 309, "name": "BTC Setup", "symbol": "BTC"},
        {"id": 310, "name": "Apple Setup", "symbol": "AAPL"},
    ])
    service.setups.get_setup_by_id = lambda setup_id, user_id: asyncio.sleep(
        0,
        result={"id": 310, "name": "Apple Setup", "symbol": "AAPL"}
        if user_id == 388 and setup_id == 310 else None,
    )

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="setup",
        selector={"asset": "BTC", "asset_source": "workspace_context"},
        message="Wat kun je over deze setup vertellen?",
        conversation_context={
            "previous_action_result": {
                "entity_type": "setup", "entity_id": 310,
                "owner_user_id": 388, "result_status": "succeeded",
            },
        },
    ))

    assert target.entity_id == 310
    assert target.resolution_source == "previous_action_result"


def test_canonical_target_active_runtime_wins_stale_selector_id():
    service = FinnV2EntityResolutionService(session=object())
    service.strategies = _FakeStrategyRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="strategy",
        selector={"strategy_id": 310},
        conversation_context={
            "canonical_entity_target": {
                "entity_type": "strategy",
                "entity_id": 309,
                "owner_id": 388,
            }
        },
    ))

    assert target.entity_id == 309
    assert target.resolution_source == "active_runtime_context"


def test_canonical_target_uses_most_specific_overlapping_visible_name():
    service = FinnV2EntityResolutionService(session=object())
    service.bots = _FakeBotRepo()
    service.bots.get_bot_configs = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 170, "name": "Alpha", "strategy_id": 309},
        {"id": 171, "name": "Alpha Bot", "strategy_id": 310, "strategy_name": "Momentum"},
    ])

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="bot",
        message="Pauzeer Alpha Bot.",
    ))

    assert target.entity_id == 171
    assert target.display_name == "Alpha Bot"
    assert target.relational_context["strategy_name"] == "Momentum"


def test_canonical_target_returns_named_ambiguity_instead_of_guessing():
    service = FinnV2EntityResolutionService(session=object())
    service.bots = _FakeBotRepo()
    service.bots.get_bot_configs = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 170, "name": "Paper Alpha", "strategy_id": 309},
        {"id": 171, "name": "Paper Beta", "strategy_id": 310},
    ])

    target = asyncio.run(service.resolve_canonical_target(user_id=388, entity_type="bot"))

    assert target.resolution_status == "ambiguous"
    assert target.candidate_names == ["Paper Alpha", "Paper Beta"]


def test_canonical_target_rejects_cross_user_context_id():
    service = FinnV2EntityResolutionService(session=object())
    service.bots = _FakeBotRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=999,
        entity_type="bot",
        client_context={"bot_id": 170},
    ))

    assert target.resolution_status == "not_found"
    assert target.entity_id is None


def test_canonical_target_marks_an_existing_cross_user_id_forbidden():
    class _Result:
        @staticmethod
        def first():
            return (1,)

    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _Result()

    service = FinnV2EntityResolutionService(session=_Session())
    service.bots = _FakeBotRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=999,
        entity_type="bot",
        selector={"bot_id": 170},
    ))

    assert target.resolution_status == "forbidden"
    assert target.entity_id is None


def test_canonical_target_rejects_an_explicitly_wrong_entity_type():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="setup",
        selector={"entity_type": "bot", "setup_id": 42},
    ))

    assert target.resolution_status == "invalid_type"


def test_canonical_bot_target_follows_strategy_surface_relation():
    service = FinnV2EntityResolutionService(session=object())
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="bot",
        workspace_hints={"strategy_id": 309},
    ))

    assert target.entity_id == 170
    assert target.display_name == "Matrix Bot"
    assert target.resolution_source == "workspace_strategy_link"


def test_canonical_bot_target_follows_setup_surface_relation_when_unique():
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="bot",
        client_context={"setup_id": 293},
    ))

    assert target.entity_id == 170
    assert target.resolution_source == "workspace_setup_link"


def test_explicit_bot_name_wins_a_different_surface_relation():
    service = FinnV2EntityResolutionService(session=object())
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.bots.get_bot_configs = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 170, "name": "Matrix Bot", "strategy_id": 309},
        {"id": 171, "name": "Named Bot", "strategy_id": 310},
    ])

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="bot",
        message="Zet het budget van Named Bot op 1000 euro.",
        workspace_hints={"strategy_id": 309},
    ))

    assert target.entity_id == 171
    assert target.resolution_source == "explicit_name"


@pytest.mark.parametrize(
    "workspace_hints",
    [
        {"surface": "automation", "bot_id": 171},
        {"surface": "my_plan", "setup_id": 294},
        {"surface": "analysis", "strategy_id": 310},
        {"surface": "profile"},
    ],
)
def test_explicit_bot_name_is_canonical_across_surfaces(workspace_hints):
    service = FinnV2EntityResolutionService(session=object())
    service.setups = _FakeSetupRepo()
    service.strategies = _FakeStrategyRepo()
    service.bots = _FakeBotRepo()
    service.bots.get_bot_configs = lambda _user_id: asyncio.sleep(0, result=[
        {"id": 170, "name": "Audit BTC Paper", "strategy_id": 309},
        {"id": 171, "name": "Other Paper Bot", "strategy_id": 310},
    ])

    target = asyncio.run(service.resolve_canonical_target(
        user_id=388,
        entity_type="bot",
        message='Wat is het budget van "Audit BTC Paper"?',
        workspace_hints=workspace_hints,
    ))

    assert target.entity_id == 170
    assert target.display_name == "Audit BTC Paper"
    assert target.resolution_source == "explicit_name"
