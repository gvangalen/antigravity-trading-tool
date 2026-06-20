from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "backend"
    / "trading-tool-backend"
    / "backend"
    / "scripts"
    / "run_platform_capacity_profiles.py"
)
DOC_PATH = (
    REPO_ROOT
    / "docs"
    / "operations"
    / "platform-phase-2-1-capacity-harness.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_platform_capacity_profiles", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_default_profiles_are_safe_by_construction():
    module = _load_script_module()

    for profile in ["read-heavy", "ai-heavy", "bot-execution-heavy"]:
        requests = module.build_profile_requests(profile, iterations=1, manual_order_preview_fixture=None)
        assert requests, f"Expected requests for profile {profile}"
        for request in requests:
            assert "/api/assistant/actions/execute" not in request["path"]
            assert "/api/orders/manual" not in request["path"]
            assert "/api/report/daily/generate" not in request["path"]


def test_mixed_load_distribution_matches_target_user_mix():
    module = _load_script_module()

    distribution = module.allocate_profile_mix(
        virtual_users=100,
        read_share=80,
        ai_share=15,
        bot_share=5,
    )

    assert distribution == {
        "read-heavy": 80,
        "ai-heavy": 15,
        "bot-execution-heavy": 5,
    }


def test_mixed_load_requests_stay_safe_and_user_scoped():
    module = _load_script_module()

    requests, distribution = module.build_mixed_profile_requests(
        virtual_users=20,
        iterations_per_user=1,
        read_share=80,
        ai_share=15,
        bot_share=5,
        manual_order_preview_fixture=None,
    )

    assert distribution == {
        "read-heavy": 16,
        "ai-heavy": 3,
        "bot-execution-heavy": 1,
    }
    assert requests
    for request in requests:
        assert request["profile"] == "mixed-load"
        assert request["scenario_profile"] in {"read-heavy", "ai-heavy", "bot-execution-heavy"}
        assert request["virtual_user"] >= 1
        assert request["scheduled_at_offset_s"] >= 0
        assert "/api/assistant/actions/execute" not in request["path"]
        assert "/api/orders/manual" not in request["path"]
        assert "/api/report/daily/generate" not in request["path"]

    ai_offsets_by_user = defaultdict(list)
    for request in requests:
        if request["scenario_profile"] == "ai-heavy":
            ai_offsets_by_user[request["virtual_user"]].append(request["scheduled_at_offset_s"])
    assert ai_offsets_by_user
    for offsets in ai_offsets_by_user.values():
        assert offsets == sorted(offsets)
        assert len(offsets) >= 2
        assert any(b - a >= 2.5 for a, b in zip(offsets, offsets[1:]))


def test_bot_execution_profile_only_uses_preview_when_fixture_is_present(tmp_path: Path):
    module = _load_script_module()

    requests_without_fixture = module.build_profile_requests(
        "bot-execution-heavy",
        iterations=1,
        manual_order_preview_fixture=None,
    )
    assert all(request["path"] != "/api/orders/preview" for request in requests_without_fixture)

    fixture_path = tmp_path / "manual_order_preview_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "bot_id": 9,
                "symbol": "BTC",
                "side": "buy",
                "quantity": 0.001,
                "price": 50000,
            }
        ),
        encoding="utf-8",
    )
    fixture = module.load_manual_order_preview_fixture(fixture_path)
    requests_with_fixture = module.build_profile_requests(
        "bot-execution-heavy",
        iterations=1,
        manual_order_preview_fixture=fixture,
    )
    assert any(request["path"] == "/api/orders/preview" for request in requests_with_fixture)


def test_capacity_harness_doc_references_script_and_safe_profiles():
    source = DOC_PATH.read_text(encoding="utf-8")

    assert "run_platform_capacity_profiles.py" in source
    assert "read-heavy" in source
    assert "ai-heavy" in source
    assert "bot-execution-heavy" in source
    assert "mixed-load" in source
    assert "80% dashboard/read" in source
    assert "human-like pacing" in source
    assert "no execute endpoints" in source
    assert "manual-order preview only when an explicit fixture is supplied" in source
