import asyncio
from types import SimpleNamespace

from backend.services.onboarding_service import DEFAULT_FLOW, OnboardingService


class FakeOnboardingRepository:
    def __init__(self, *, steps=None, inferred_completed=None):
        self.steps = steps or []
        self.inferred_completed = inferred_completed or {}
        self.inserted_steps = []
        self.marked_steps = []

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


def test_get_status_dict_backfills_legacy_completion_from_existing_user_data():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=False, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "market": True,
            "macro": True,
            "technical": True,
            "setup": True,
            "strategy": True,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=42))

    assert repo.marked_steps == [["profile", "market", "macro", "technical", "setup", "strategy"]]
    assert status.has_profile is True
    assert status.has_market is True
    assert status.has_macro is True
    assert status.has_technical is True
    assert status.has_setup is True
    assert status.has_strategy is True
    assert status.onboarding_complete is True


def test_get_status_dict_only_backfills_missing_legacy_steps():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=False, pipeline_started=False),
        ],
        inferred_completed={
            "profile": True,
            "market": False,
            "macro": False,
            "technical": True,
            "setup": True,
            "strategy": False,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=7))

    assert repo.marked_steps == [["technical", "setup"]]
    assert status.has_profile is True
    assert status.has_market is False
    assert status.has_macro is False
    assert status.has_technical is True
    assert status.has_setup is True
    assert status.has_strategy is False
    assert status.onboarding_complete is False


def test_get_status_dict_marks_legacy_user_complete_without_profile_if_core_steps_exist():
    repo = FakeOnboardingRepository(
        steps=[
            SimpleNamespace(step_key="profile", completed=False, pipeline_started=False),
            SimpleNamespace(step_key="market", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="macro", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="technical", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="setup", completed=True, pipeline_started=False),
            SimpleNamespace(step_key="strategy", completed=True, pipeline_started=False),
        ],
        inferred_completed={
            "profile": False,
            "market": True,
            "macro": True,
            "technical": True,
            "setup": True,
            "strategy": True,
        },
    )

    service = OnboardingService(repo)

    status = asyncio.run(service.get_status_dict(user_id=2))

    assert repo.marked_steps == []
    assert status.has_profile is False
    assert status.has_market is True
    assert status.has_macro is True
    assert status.has_technical is True
    assert status.has_setup is True
    assert status.has_strategy is True
    assert status.onboarding_complete is True
