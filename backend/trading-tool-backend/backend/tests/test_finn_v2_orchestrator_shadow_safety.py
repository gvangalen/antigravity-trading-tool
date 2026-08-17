from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_block4_shadow_path_has_single_internal_orchestrator_and_no_public_execute_endpoint():
    run_source = (ROOT / "services" / "finn_v2_run_service.py").read_text(encoding="utf-8")
    api_source = (ROOT / "api" / "finn_v2_api.py").read_text(encoding="utf-8")

    assert "self.orchestrator.execute_run" in run_source
    assert "execute_shadow_tool_chain" in run_source
    assert "/execute" not in api_source


def test_orchestrator_result_storage_is_append_only():
    source = (ROOT / "infrastructure" / "repositories" / "finn_v2_orchestrator_repository.py").read_text(encoding="utf-8")

    assert "get_for_run_version" in source
    assert "async def create" in source
    assert ".update(" not in source
