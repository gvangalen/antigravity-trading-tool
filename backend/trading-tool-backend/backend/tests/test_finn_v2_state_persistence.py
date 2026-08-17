from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService


def test_state_persistence_source_is_append_only():
    source = open("backend/trading-tool-backend/backend/infrastructure/repositories/finn_v2_state_repository.py", "r", encoding="utf-8").read()

    assert "next_revision" in source
    assert ".update(" not in source

