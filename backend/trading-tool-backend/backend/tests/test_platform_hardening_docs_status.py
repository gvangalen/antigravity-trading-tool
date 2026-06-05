from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
STATUS_DOC = REPO_ROOT / "docs" / "operations" / "platform-hardening-status.md"
PHASE6_DOC = REPO_ROOT / "docs" / "operations" / "platform-hardening-phase6-qa.md"


def test_platform_status_reflects_latest_deployed_hardening_baseline():
    source = STATUS_DOC.read_text()

    assert "`404b4ec` - `Stabilize deploy and rollback recovery flow`" in source
    assert "`Platform hardening baseline is live on Oracle`" in source
    assert (
        "`pytest -q backend/trading-tool-backend/backend/tests/test_enterprise_hardening_step6.py "
        "backend/trading-tool-backend/backend/tests/test_runtime_reliability_hardening.py`: `10 passed`"
        in source
    )
    assert "Step 5 - Frontend Cache/Polling" in source
    assert "Step 6 - Enterprise Safety Slice" in source
    assert "Step 7 - Multi-Instance Cache Coordination" in source
    assert "Step 8 - Replay/Exactly-Once Hardening" in source
    assert "Security Hardening Slice" in source
    assert "authenticated frontend flows clear stale local user/token state" in source
    assert "market-data read routes no longer perform forward-return sync writes" in source
    assert 'externally: `401 {"detail":"Missing access token"}`' in source
    assert "LAST_GOOD_COMMIT" in source
    assert "rollback_live.sh <commit>" in source


def test_platform_status_does_not_reintroduce_old_push_service_risk_claim():
    status_source = STATUS_DOC.read_text()
    phase6_source = PHASE6_DOC.read_text()

    stale_claim = "PushService still uses sync SQLAlchemy style internally"
    assert stale_claim not in status_source
    assert stale_claim not in phase6_source
    assert "PushService is async-first" in status_source
    assert "must not reintroduce sync SQLAlchemy query logic" in phase6_source
