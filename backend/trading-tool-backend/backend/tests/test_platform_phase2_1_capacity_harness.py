from __future__ import annotations

import importlib.util
import json
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
    assert "no execute endpoints" in source
    assert "manual-order preview only when an explicit fixture is supplied" in source
