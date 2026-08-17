from datetime import datetime, timedelta, timezone

from backend.services.finn_v2_freshness_service import FinnV2FreshnessService


def test_freshness_service_marks_market_data_stale_after_threshold():
    service = FinnV2FreshnessService()
    stale = datetime.now(timezone.utc) - timedelta(seconds=901)
    fresh = datetime.now(timezone.utc) - timedelta(seconds=100)

    assert service.freshness_for("read_market_snapshot", stale) == "stale"
    assert service.freshness_for("read_market_snapshot", fresh) == "fresh"


def test_freshness_service_returns_not_applicable_for_profile():
    service = FinnV2FreshnessService()

    assert service.freshness_for("read_profile", None) == "not_applicable"

