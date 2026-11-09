"""Synthetic source refs only; the protected collector never contacts production here."""

from datetime import datetime, timezone

from backend.scripts import probe_protected_source_time_parity as probe
from backend.scripts.run_finn_production_qa import profile_error_category


REF = {"market_id": 43, "measurement_id": 987,
       "source_observed_at_utc": "2026-11-08T09:30:00+00:00"}


def test_ref_validation_normalizes_offset_and_rejects_incomplete_identity():
    assert probe._normalized_ref({**REF,
        "source_observed_at_utc": "2026-11-08T10:30:00+01:00"}) == (
        43, 987, datetime(2026, 11, 8, 9, 30, tzinfo=timezone.utc),
    )
    assert probe._normalized_ref({**REF, "measurement_id": None}) is None
    assert probe._normalized_ref({**REF, "source_observed_at_utc": "2026-11-08T09:30:00"}) is None


def test_source_parity_runner_error_is_sanitized():
    assert profile_error_category("trader_source_time_parity", RuntimeError(
        "private market 987 secret-token")) == "paper_exit_probe_runtime_error"
    assert profile_error_category("trader_source_time_parity", RuntimeError(
        "paper_exit_source_parity_failed")) == "paper_exit_source_parity_failed"


def test_report_path_persists_the_product_snapshot_reference(monkeypatch):
    from backend.infrastructure import database
    from backend.infrastructure.repositories import daily_report_repository
    from backend.services import finn_unified_report_service

    saved = {}
    class Session:
        def commit(self):
            saved["committed"] = True
        def rollback(self):
            raise AssertionError("unexpected rollback")
        def close(self):
            pass
    class Writer:
        JSONB_FIELDS = ("score_source_snapshot",)
        def __init__(self, _session):
            pass
        def upsert_daily_report(self, **kwargs):
            saved.update(kwargs)
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(daily_report_repository, "DailyReportWriteRepository", Writer)
    monkeypatch.setattr(finn_unified_report_service,
        "generate_unified_daily_report_sections", lambda **_: {
            "score_source_snapshot": {"assets": [{"market_id": 43, "pair": "BTC/USDT",
                "market_snapshot": {"source_ref": REF}}]},
        })
    snapshot = probe._saved_report(7)
    assert saved["user_id"] == 7 and saved["committed"] is True
    assert saved["sections"]["score_source_snapshot"] == snapshot
    assert snapshot["assets"][0]["market_snapshot"]["source_ref"] == REF


def test_four_surface_collector_returns_only_fixed_checks(monkeypatch):
    def read_json(*, owner_id, path):
        assert owner_id == 7
        if path.startswith("/api/workspace/"):
            return {"market_id": 43, "quote": {"source_ref": REF,
                "as_of": REF["source_observed_at_utc"]}}
        assert path.startswith("/api/report/daily/latest")
        return {"score_source_snapshot": {"assets": [
            {"market_id": 43, "pair": "BTC/USDT", "market_snapshot": {"source_ref": REF,
                "as_of": REF["source_observed_at_utc"]}},
        ]}}

    async def finn(_owner):
        return {"source_ref": REF, "as_of": REF["source_observed_at_utc"]}

    async def browser(_owner, _source):
        return {f"{surface}_{zone}": True for surface in ("analysis", "report")
                for zone in ("amsterdam", "new_york", "tokyo")}

    monkeypatch.setattr(probe, "read_json", read_json)
    monkeypatch.setattr(probe, "_saved_report", lambda _owner: {})
    monkeypatch.setattr(probe, "_finn_market_read", finn)
    monkeypatch.setattr(probe, "_rendered_quote_times", browser)
    evidence = {"ui_projection": {"source_ref": REF,
               "source_price_at": REF["source_observed_at_utc"]}}
    result = probe.run(user_id=7, market_id=43,
                       paper_evidence=evidence, frozen_ref=REF)
    assert result == {"result": "PASS", "failed_checks": [], "gate_status": "PASS",
                      "browser_zones_checked": 6, "live_calls": 0}
    assert "987" not in str(result) and "2026" not in str(result)

    def wrong_analysis(*, owner_id, path):
        value = read_json(owner_id=owner_id, path=path)
        if path.startswith("/api/workspace/"):
            value["quote"]["source_ref"] = {**REF, "measurement_id": 988}
        return value

    monkeypatch.setattr(probe, "read_json", wrong_analysis)
    failed = probe.run(user_id=7, market_id=43,
                       paper_evidence=evidence, frozen_ref=REF)
    assert failed["failed_checks"] == ["analysis_source", "four_instant_display"] or (
        failed["failed_checks"] == ["analysis_source"]
    )
    assert "988" not in str(failed)
