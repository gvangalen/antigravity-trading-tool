import asyncio
from types import SimpleNamespace

from backend.infrastructure.repositories.onboarding_repository import OnboardingRepository
from backend.services.onboarding_service import DEFAULT_FLOW, OnboardingService


class FakeOnboardingRepository:
    def __init__(self, *, steps=None, inferred_completed=None):
        self.steps = steps or []
        self.inferred_completed = inferred_completed or {}
        self.inserted_steps = []
        self.marked_steps = []
        self.marked_flow_completed = False
        self.pipeline_started = []

    async def get_user_steps(self, user_id: int, flow: str):
        assert flow == DEFAULT_FLOW
        return self.steps

    async def insert_steps(self, user_id: int, flow: str, step_keys):
        assert flow == DEFAULT_FLOW
        self.inserted_steps.append(list(step_keys))
        for step_key in step_keys:
            self.steps.append(
                SimpleNamespace(
                    step_key=step_key,
                    completed=False,
                    pipeline_started=False,
                )
            )

    async def infer_completed_steps(self, user_id: int):
        return dict(self.inferred_completed)

    async def mark_steps_completed(self, user_id: int, flow: str, step_keys):
        assert flow == DEFAULT_FLOW
        self.marked_steps.append(list(step_keys))
        step_key_set = set(step_keys)
        for step in self.steps:
            if step.step_key in step_key_set:
                step.completed = True

    async def mark_flow_completed(self, user_id: int, flow: str):
        assert flow == DEFAULT_FLOW
        self.marked_flow_completed = True
        for step in self.steps:
            step.completed = True

    async def mark_pipeline_started(self, user_id: int, flow: str, step_key: str):
        assert flow == DEFAULT_FLOW
        self.pipeline_started.append(step_key)
        for step in self.steps:
            if step.step_key == step_key:
                step.pipeline_started = True


def test_get_status_dict_backfills_legacy_completion_from_existing_user_data():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="asset", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="bot", completed=False, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "asset": True,
            "market": True,
            "macro": True,
            "technical": True,
            "setup": True,
            "strategy": True,
            "bot": True,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=42))

    assert repo.marked_steps == [["profile", "asset", "market", "macro", "technical", "setup", "strategy", "bot"]]
    assert status.has_profile is True
    assert status.has_asset is True
    assert status.has_market is True
    assert status.has_macro is True
    assert status.has_technical is True
    assert status.has_setup is True
    assert status.has_strategy is True
    assert status.has_bot is True
    assert status.onboarding_complete is True


def test_get_status_dict_only_backfills_missing_legacy_steps():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="asset", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="bot", completed=False, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "asset": True,
            "market": False,
            "macro": False,
            "technical": True,
            "setup": True,
            "strategy": False,
            "bot": False,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=7))

    assert repo.marked_steps == [["asset", "technical", "setup"]]
    assert status.has_profile is True
    assert status.has_asset is True
    assert status.has_market is False
    assert status.has_macro is False
    assert status.has_technical is True
    assert status.has_setup is True
    assert status.has_strategy is False
    assert status.has_bot is False
    assert status.onboarding_complete is False


def test_get_status_dict_keeps_new_flow_incomplete_without_profile():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="asset", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="bot", completed=True, pipeline_started=False),
        ],
        inferred_completed={
            "profile": False,
            "asset": True,
            "market": True,
            "macro": True,
            "technical": True,
            "setup": True,
            "strategy": True,
            "bot": True,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=2))

    assert repo.marked_steps == [["asset"]]
    assert status.has_profile is False
    assert status.has_asset is True
    assert status.has_market is True
    assert status.has_macro is True
    assert status.has_technical is True
    assert status.has_setup is True
    assert status.has_strategy is True
    assert status.has_bot is True
    assert status.onboarding_complete is False
    assert status.current_phase == "profile"


def test_finish_onboarding_does_not_force_complete_incomplete_flow():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="asset", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="bot", completed=False, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "asset": True,
            "market": False,
            "macro": False,
            "technical": False,
            "setup": False,
            "strategy": False,
            "bot": False,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.finish_onboarding(user_id=11))

    assert repo.marked_flow_completed is False
    assert repo.pipeline_started == []
    assert status.has_profile is True
    assert status.has_asset is True
    assert status.has_market is False
    assert status.has_bot is False
    assert status.onboarding_complete is False


def test_finish_onboarding_keeps_completed_flow_and_starts_pipeline(monkeypatch):
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="asset", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="bot", completed=True, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "asset": True,
            "market": True,
            "macro": True,
            "technical": True,
            "setup": True,
            "strategy": True,
            "bot": True,
        },
    )

    service = OnboardingService(repo)
    kickstarted = []

    async def _fake_kickstart(user_id: int):
        kickstarted.append(user_id)

    monkeypatch.setattr(service, "_kickstart_user_pipeline", _fake_kickstart)

    status = asyncio.run(service.finish_onboarding(user_id=99))

    assert repo.marked_flow_completed is False
    assert kickstarted == [99]
    assert status.onboarding_complete is True


def test_status_marks_automation_complete_without_exchange_for_v1_onboarding():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="asset", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="bot", completed=True, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "asset": True,
            "market": True,
            "macro": True,
            "technical": True,
            "setup": True,
            "strategy": True,
            "bot": True,
        },
    )

    async def _fake_infer_onboarding_state(user_id: int):
        return {
            "active_asset": "BTC",
            "has_profile": True,
            "has_asset": True,
            "has_market": True,
            "has_macro": True,
            "has_technical": True,
            "has_setup": True,
            "has_strategy": True,
            "has_bot": True,
            "has_exchange": False,
        }

    repo.infer_onboarding_state = _fake_infer_onboarding_state
    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=5))

    assert status.phases_completed["automation"] is True
    assert status.phases_completed["complete"] is True
    assert status.current_phase == "complete"
    assert status.next_route == "/dashboard?symbol=BTC"


def test_infer_onboarding_state_requires_explicit_asset_and_symbol_scoped_indicator_rows():
    class FakeUser:
        ai_preferences = {}

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            return self._value

    class FakeColumnsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: [
                "id",
                "user_id",
                "indicator",
                "category",
                "symbol",
                "asset_class",
                "priority",
                "enabled",
                "created_at",
            ])

    class FakeSession:
        async def get(self, model, user_id):
            return FakeUser()

        async def execute(self, query, params=None):
            sql = str(query)
            if "information_schema.columns" in sql:
                return FakeColumnsResult()
            if "FROM exchange_keys" in sql:
                return FakeScalarResult(False)
            if "FROM setups" in sql or "FROM strategies" in sql or "FROM bot_configs" in sql:
                return FakeScalarResult(False)
            raise AssertionError(f"Unexpected query executed for blank onboarding state: {sql}")

    repo = OnboardingRepository(FakeSession())

    state = asyncio.run(repo.infer_onboarding_state(user_id=42))

    assert state["active_asset"] is None
    assert state["has_asset"] is False
    assert state["has_market"] is False
    assert state["has_macro"] is False
    assert state["has_technical"] is False
    assert state["has_setup"] is False
    assert state["has_strategy"] is False
    assert state["has_bot"] is False


def test_onboarding_repository_schema_probe_failure_uses_legacy_safe_columns():
    class ProbeFailureSession:
        async def execute(self, query, params=None):
            raise RuntimeError("probe failed")

    repo = OnboardingRepository(ProbeFailureSession())

    columns = asyncio.run(repo._get_user_config_columns())

    assert columns == {
        "id",
        "user_id",
        "indicator",
        "category",
        "created_at",
    }
