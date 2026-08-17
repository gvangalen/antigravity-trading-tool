from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verifier_repositories_and_service_use_owner_scoped_reads():
    repo_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_verified_response_repository.py").read_text(encoding="utf-8")
    service_source = (ROOT / "services" / "finn_v2_response_verifier_service.py").read_text(encoding="utf-8")

    assert "user_id" in repo_source
    assert "get_by_id_for_user" in service_source or "run_id=run_id, user_id=user_id" in service_source
