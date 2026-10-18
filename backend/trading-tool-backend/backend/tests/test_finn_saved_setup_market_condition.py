import asyncio
from dataclasses import replace
from types import SimpleNamespace

from backend.domain.saved_setup_market_condition import saved_setup_market_condition
from backend.domain.setup_market_match import match_setup
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import SetupToolAdapter
from backend.services.finn_v2_tool_adapters.setup_inventory_tool_adapter import SetupInventoryToolAdapter


def test_all_five_presets_are_exact_saved_bounds_and_custom_is_not_mislabeled():
    bands = (
        ("heavy_pressure", 0, 25, "Zwaar onder druk"),
        ("pressure", 26, 45, "Onder druk"),
        ("no_direction", 46, 60, "Geen duidelijke richting"),
        ("gaining_strength", 61, 75, "De markt trekt aan"),
        ("strong", 76, 100, "Sterke markt"),
    )
    english = ("Heavy pressure", "Under pressure", "No clear direction", "Gaining strength", "Strong market")
    german = ("Stark unter Druck", "Unter Druck", "Keine klare Richtung", "Der Markt wird stärker", "Starker Markt")
    for index, (key, minimum, maximum, label) in enumerate(bands):
        condition = saved_setup_market_condition({
            "min_benchmark_score": minimum, "max_benchmark_score": maximum,
        })
        assert condition.pop("labels") == {
            "nl": label,
            "en": english[index],
            "de": german[index],
        }
        assert condition == {
            "kind": "preset", "source": "saved_score_bounds",
            "effect": "setup_eligibility_only", "purchase_guaranteed": False,
            "key": key,
            "benchmark_score_min": minimum, "benchmark_score_max": maximum,
        }
    custom = saved_setup_market_condition({"min_benchmark_score": 26})
    assert custom["kind"] == "custom"
    assert custom["benchmark_score_min"] == 26
    assert custom["benchmark_score_max"] is None
    assert saved_setup_market_condition({
        "min_benchmark_score": 26, "max_benchmark_score": 45, "min_macro_score": 30,
    })["kind"] == "preset"
    assert saved_setup_market_condition({})["kind"] == "none"


def test_saved_friday_dca_survives_new_session_and_owner_scoped_finn_read():
    rows = {}

    class Result:
        def __init__(self, row=None, inserted=False):
            self.row = row
            self.inserted = inserted

        def fetchone(self):
            return (41,) if self.inserted else None

        def mappings(self):
            return SimpleNamespace(first=lambda: self.row)

    class Session:
        async def execute(self, query, params):
            sql = str(query)
            if "INSERT INTO setups" in sql:
                rows[41] = {**params, "id": 41}
                return Result(inserted=True)
            if "SELECT * FROM setups WHERE id" in sql:
                row = rows.get(params["setup_id"])
                return Result(row if row and row["user_id"] == params["user_id"] else None)
            raise AssertionError(sql)

    async def run():
        saved_id = await SetupRepository(Session()).create_setup({
            "name": "Vrijdag BTC", "symbol": "BTC", "timeframe": "1D",
            "setup_type": "dca", "dca_frequency": "weekly", "dca_day": "5",
            "description": "Ik wil geduldig opbouwen; dit is mijn toelichting.",
            "min_benchmark_score": 26, "max_benchmark_score": 45,
        }, user_id=7, tags=[])
        assert saved_id == 41
        # A fresh repository/session represents a refresh or a new login.
        assert await SetupRepository(Session()).get_setup_by_id(saved_id, 8) is None
        reread = await SetupRepository(Session()).get_setup_by_id(saved_id, 7)
        active = (await SetupToolAdapter().execute(
            setup=reread, resolution_source="owner_setup_id",
        ))["data"].dict()
        listed = (await SetupInventoryToolAdapter().execute(
            setups=[reread], complete=True,
        ))["data"].setups[0]
        assert active["saved_market_condition"]["key"] == "pressure"
        assert listed["saved_market_condition"] == active["saved_market_condition"]
        assert active["description"] == reread["description"]
        assert active["dca_day_name"] == "friday"
        assert active["min_benchmark_score"] == 26
        assert active["max_benchmark_score"] == 45
        assert match_setup(reread, {"market": 30, "macro": 50, "technical": 50})["status"] == "matches"
        assert match_setup(reread, {"market": 50, "macro": 50, "technical": 50})["status"] == "outside_conditions"
        assert match_setup(reread, None)["status"] == "insufficient_data"
        reasoning_facts = FinnV2ReasoningContextService._sanitize_facts(
            None, active, "read_active_setup",
        )
        assert reasoning_facts["saved_market_condition"]["key"] == "pressure"
        assert reasoning_facts["description"] == reread["description"]
        assert reasoning_facts["dca_day_name"] == "friday"

        class Reads:
            async def execute_tool(self, **kwargs):
                assert kwargs["user_id"] == 7
                assert kwargs["selector"]["setup_id"] == saved_id
                is_strategy = kwargs["tool_name"] == "read_linked_strategy"
                return SimpleNamespace(
                    success=True, availability="available", freshness_status="unknown",
                    source="strategies" if is_strategy else "setups", asset="BTC",
                    result=({"strategy_id": 51, "setup_id": 41, "name": "BTC €100",
                             "base_amount": 100, "execution_mode": "fixed"}
                            if is_strategy else active), error_codes=[], as_of=None,
                )

        for run_id in ("first-turn", "second-session-turn"):
            executor = FinnResponsesReadExecutor(session=object(), user_id=7, run_id=run_id)
            executor.reads = Reads()
            tool = replace(
                FinnResponsesToolCatalog().validate("get_saved_setup", {"setup_name": "Vrijdag BTC"}),
                inputs={"setup_id": saved_id},
            )
            response = await executor(tool)
            evidence = response["results"][0]
            assert evidence["data"]["saved_market_condition"]["labels"]["nl"] == "Onder druk"
            assert evidence["data"]["description"] == reread["description"]
            assert evidence["data"]["dca_day_name"] == "friday"
            assert "not merely" in response["evidence_boundary"]
            assert "does not guarantee a purchase" in response["evidence_boundary"]

        executor = FinnResponsesReadExecutor(session=object(), user_id=7, run_id="plan-turn")
        executor.reads = Reads()
        plan_tool = replace(
            FinnResponsesToolCatalog().validate(
                "get_active_plan_and_strategy", {"setup_name": "Vrijdag BTC"},
            ),
            inputs={"setup_id": saved_id},
        )
        plan = await executor(plan_tool)
        setup_evidence, strategy_evidence = (item["data"] for item in plan["results"])
        assert setup_evidence["saved_market_condition"]["key"] == "pressure"
        assert setup_evidence.get("base_amount") is None
        assert strategy_evidence["base_amount"] == 100
        assert strategy_evidence.get("saved_market_condition") is None

    asyncio.run(run())
