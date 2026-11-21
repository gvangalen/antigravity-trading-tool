from backend.services.finn_report_attention import report_attention
from backend.services.finn_coach_feed_service import _fallback
from backend.services.finn_v2_tool_execution_service import _selected_report_scope


def test_report_attention_prefers_missing_exact_pair_over_available_pair():
    report = {"score_source_snapshot": {"assets": [
        {"symbol": "BTC", "pair": "BTC/EUR", "score_status": "available", "benchmark_score": 61},
        {"symbol": "ETH", "pair": "ETH/USDT", "score_status": "missing", "benchmark_score": None},
    ]}}
    evidence = report_attention(report)
    assert evidence == {"attention_kind": "benchmark_unavailable", "attention_pair": "ETH/USDT"}
    copy = _fallback("daily_report_ready", "Dagrapport", {"report_date": "2026-11-20", **evidence})
    assert "ETH/USDT" in copy["nl"]["body"]
    assert "momentopname" in copy["nl"]["body"]


def test_report_attention_uses_available_pair_without_claiming_trade():
    report = {"score_source_snapshot": {"assets": [
        {"symbol": "BTC", "pair": "BTC/USDT", "score_status": "available", "benchmark_score": 52},
    ]}}
    evidence = report_attention(report)
    assert evidence == {"attention_kind": "benchmark_available", "attention_pair": "BTC/USDT"}
    body = _fallback("periodic_report_ready", "weekly", {"report_type": "weekly", **evidence})["nl"]["body"]
    assert "BTC/USDT" in body
    assert "koop" not in body


def test_report_attention_never_uses_unverified_pair_or_prose():
    report = {"score_source_snapshot": {"assets": [
        {"symbol": "BTC", "pair": "BTC/USDT; DROP", "score_status": "missing"},
    ]}}
    assert report_attention(report) == {}


def test_selected_feed_report_binds_date_type_and_asset_after_owner_read():
    scope, asset = _selected_report_scope({"event_type": "periodic_report_ready", "evidence": {
        "report_type": "weekly", "report_date": "2026-11-20", "attention_pair": "BTC/USDT",
    }})
    assert scope == {"report_type": "weekly_reports", "report_date": "2026-11-20"}
    assert asset == "BTC"
    assert _selected_report_scope({"event_type": "watchlist_added", "evidence": {
        "report_type": "weekly", "report_date": "2026-11-20", "attention_pair": "BTC/USDT",
    }}) == ({}, None)
    assert _selected_report_scope({"event_type": "daily_report_ready", "evidence": {
        "report_type": "weekly_reports;DROP", "report_date": "2026-11-20", "attention_pair": "BTC/USDT",
    }}) == ({}, None)
