from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from types import SimpleNamespace

from backend.scripts import probe_protected_aapl_quote_coach as probe
from backend.scripts.run_finn_production_qa import ALLOWED_PROFILES, profile_error_category


def test_old_quote_is_rejected_only_when_mislabeled_current():
    assert probe._old_claimed_current("De actuele AAPL-koerssnapshot is USD 351,19.")
    assert not probe._old_claimed_current("Het historische rapport noemde USD 351,19 om 19:03 UTC.")
    assert not probe._old_claimed_current("USD 351,19 is niet actueel; het is de oude rapportkoers.")
    assert not probe._old_claimed_current("Oud rapport: USD 351,19; de actuele koers is USD 350,49.")
    assert probe._old_claimed_current("De oude rapportkoers USD 351,19 is ook de actuele koerssnapshot.")
    assert not probe._old_claimed_current("USD 351,19 is niet bevestigd als actuele koers.")
    assert not probe._old_claimed_current("USD 351,19 is **niet bevestigd als actuele koers**.")
    assert not probe._old_claimed_current("USD 351,19 is niet opnieuw bevestigd als de huidige AAPL-koers.")
    assert probe._old_claimed_current("USD 351,19 is niet oud maar wel de actuele AAPL-koers.")
    assert probe._old_claimed_current("USD 351,19 is niet oud en is de actuele koers.")
    assert probe._old_claimed_current("USD 351,19 is niet alleen de actuele koers, maar ook een rapportwaarde.")
    assert probe._old_claimed_current("USD 351,19 is niet bevestigd als actuele koers, maar is wel de huidige AAPL-koers.")


def test_market_and_owner_evidence_bind_both_distinct_moments():
    source = {"price": Decimal("350.49"),
              "at": datetime(2026, 11, 9, 20, 59, tzinfo=timezone.utc)}
    ids = {"setup": 2, "strategy": 3, "bot": 4, "decision": 5,
           "report_date": "2026-11-09"}
    rows = [
        {"scope": "read_market_snapshot", "status": "completed", "source": "market_data", "data": {
            "symbol": "AAPL", "price": 350.49, "quote_currency": "USD",
            "as_of": "2026-11-09T20:59:00+00:00"}},
        {"scope": "read_latest_report", "status": "completed", "source": "daily_reports", "data": {
            "report_date": "2026-11-09",
            "score_source_snapshot": {"assets": [{"symbol": "AAPL", "market_snapshot": {
                "price": 351.19, "quote_currency": "USD",
                "as_of": "2026-11-09T19:03:00+00:00"}}]}}},
        {"scope": "read_bot_status", "status": "completed", "source": "bot_configs", "data": {
            "bot_id": 4, "is_live": False,
            "latest_decision": {"decision_id": 5, "reason_code": "market_price_stale"}}},
    ]
    assert probe._market_evidence(rows, source)["source_match"] is True
    assert probe._market_evidence(rows + [dict(rows[0])], source)["source_match"] is True
    assert probe._owner_evidence(rows, ids) == {
        "old_report_match": True, "paper_bot_stale_reason": True,
    }
    rows[0]["data"]["as_of"] = "2026-11-09T19:03:00+00:00"
    assert probe._market_evidence(rows, source)["source_match"] is False
    rows[1]["data"]["score_source_snapshot"]["assets"][0]["market_snapshot"]["price"] = 350.49
    assert probe._owner_evidence(rows, ids)["old_report_match"] is False
    rows[1]["data"]["report_date"] = "2026-11-08"
    assert probe._owner_evidence(rows, ids)["old_report_match"] is False
    rows[1]["data"]["report_date"] = "2026-11-09"
    assert not probe._owner_evidence(rows + [{**rows[1], "source": "foreign_reports"}], ids)["old_report_match"]
    assert not probe._market_evidence(rows + [{**rows[0], "source": "other"}], source)["source_match"]
    assert not probe._market_evidence(rows + [{**rows[0], "data": {**rows[0]["data"], "price": 999}}], source)["source_match"]


def test_plan_and_score_reads_must_be_aapl_and_materialized():
    ids = {"setup": 2, "strategy": 3}
    sources = {"read_active_setup": "setups", "read_linked_strategy": "strategies",
               "read_asset_scores": "daily_scores_and_source_indicators"}
    rows = [{"scope": scope, "source": sources[scope], "status": "completed", "data": {
        "symbol": "AAPL", **({"setup_id": 2} if scope == "read_active_setup" else {}),
        **({"setup_id": 2, "strategy_id": 3} if scope == "read_linked_strategy" else {}),
        **({"reported_scores": {"macro_score": 20}} if scope == "read_asset_scores" else {})}}
        for scope in ("read_active_setup", "read_linked_strategy", "read_asset_scores")]
    assert probe._plan_score_evidence(rows, ids)
    assert probe._plan_score_evidence(rows + [dict(rows[-1])], ids)
    rows[-1]["data"]["reported_scores"] = {"macro_score": None}
    assert not probe._plan_score_evidence(rows, ids)
    rows[-1]["data"]["reported_scores"] = {"macro_score": 20}
    rows[0]["data"]["symbol"] = "ETH"
    assert not probe._plan_score_evidence(rows, ids)
    rows[0]["data"]["symbol"] = "AAPL"
    rows[0]["data"]["setup_id"] = 99
    assert not probe._plan_score_evidence(rows, ids)
    rows[0]["data"]["setup_id"] = 2
    assert not probe._plan_score_evidence(rows + [{**rows[0], "source": "foreign_setups"}], ids)


def test_owner_references_reject_foreign_duplicate_or_unowned_refs():
    ids = {"setup": 2, "strategy": 3, "bot": 4, "report_date": "2026-11-09"}
    refs = [SimpleNamespace(entity_type=kind, entity_id=str(value), source=source,
                            owned_by_user=True)
            for kind, source, value in (("setup", "setups", 2),
                                        ("strategy", "strategies", 3),
                                        ("bot", "bot_configs", 4),
                                        ("bot_status", "bot_configs", 4),
                                        ("latest_report", "daily_reports", 6),
                                        ("scores", "daily_scores_and_source_indicators", "AAPL"))]
    assert probe._owner_references(refs, ids)
    refs[1].entity_id = "999"
    assert not probe._owner_references(refs, ids)
    refs[1].entity_id = "3"
    refs[1].owned_by_user = False
    assert not probe._owner_references(refs, ids)
    refs[1].owned_by_user = True
    assert not probe._owner_references(refs + [refs[1]], ids)
    assert not probe._owner_references(refs[:-1], ids)
    assert not probe._owner_references(refs + [SimpleNamespace(
        entity_type="portfolio", entity_id="99", source="bot_portfolios", owned_by_user=False,
    )], ids)
    assert probe._owner_references(refs + [SimpleNamespace(
        entity_type="market_snapshot", entity_id="11", source="market_data", owned_by_user=False,
    )], ids)
    owner = {"old_report_match": True, "paper_bot_stale_reason": True}
    assert probe._owner_reference_check([], ids, plan_score=True, owner=owner)
    assert not probe._owner_reference_check([], ids, plan_score=False, owner=owner)
    assert not probe._owner_reference_check([], ids, plan_score=True,
                                            owner={**owner, "old_report_match": False})
    assert not probe._owner_reference_check(refs + [SimpleNamespace(
        entity_type="portfolio", entity_id="99", source="bot_portfolios", owned_by_user=False,
    )], ids, plan_score=True, owner=owner)


def test_source_selector_matches_product_and_fails_closed_on_null_currency_and_ties(monkeypatch):
    moment = datetime(2026, 11, 9, 20, 59, tzinfo=timezone.utc)
    received = []
    def quote(row_id, price="350.49", *, source=moment, stored=moment,
              currency="USD", symbol="AAPL", provider="twelve_data", final=False):
        return (Decimal(price) if price is not None else None, source, currency,
                row_id, stored, symbol, provider, final)

    rows = [quote(11)]

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql):
            received.append(sql)

        def fetchall(self):
            return rows

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(probe.fixture, "_connection", lambda: Connection())
    assert probe._source()["measurement_id"] == 11
    assert "quote_currency IS NOT NULL" not in received[-1]
    assert "price IS NOT NULL" not in received[-1]
    assert "ORDER BY source_observed_at DESC,timestamp DESC,id DESC LIMIT 4096" in received[-1]
    rows = [quote(13), quote(12), quote(11)]
    assert probe._source()["measurement_id"] == 13
    rows = [quote(12, None), quote(11, source=moment.replace(minute=58))]
    with pytest.raises(RuntimeError, match="^aapl_source_unavailable$"):
        probe._source()
    rows = [quote(12, currency=None), quote(11, source=moment.replace(minute=58))]
    with pytest.raises(RuntimeError, match="^aapl_source_unavailable$"):
        probe._source()
    rows = [quote(12, currency="EUR")]
    with pytest.raises(RuntimeError, match="^aapl_source_unavailable$"):
        probe._source()
    rows = [quote(12), quote(11, "350.50")]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(12), quote(11, currency="EUR")]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(12), quote(11, provider="other")]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(12), quote(11, symbol="OTHER")]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(12), quote(11, "350.50", stored=moment.replace(minute=58))]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    # A mutable quote at a candle's end belongs to the next minute. The
    # product chooses that quote even when the completed prior candle has a
    # later storage ID or a different close.
    rows = [quote(13, "350.81", final=True), quote(12, "350.82")]
    assert probe._source()["measurement_id"] == 12
    rows = [quote(13, "350.81", final=True), quote(12, "350.82"), quote(11, "350.83")]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(13, "350.81", final=True), quote(12, "350.82", final=True)]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(100 - index) for index in range(66)]
    assert probe._source()["measurement_id"] == 100
    rows[-1] = quote(35, "350.50")
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    rows = [quote(5000 - index) for index in range(4096)]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()
    # The cap applies to the complete highest instant, before candles are
    # filtered. A sole quote cannot hide the 4096th candidate.
    rows = [quote(5000 - index, final=True) for index in range(4095)] + [quote(1)]
    with pytest.raises(RuntimeError, match="^aapl_source_ambiguous$"):
        probe._source()


def test_source_advancement_requires_inconclusive_not_old_quote_failure():
    first = {"measurement_id": 11, "price": Decimal("350.49"),
             "at": datetime(2026, 11, 9, 20, 59, tzinfo=timezone.utc)}
    assert probe._same_source(first, dict(first))
    assert not probe._same_source(first, {**first, "measurement_id": 12})
    assert not probe._same_source(first, {**first, "price": Decimal("350.50")})
    assert probe._result(["market_source_mismatch"], source_advanced=True) == "INCONCLUSIVE"
    assert probe._result(["live_attempt"], source_advanced=True) == "FAIL"
    assert probe._result(["unexpected_business_write"], source_advanced=True) == "FAIL"


def test_answer_checks_require_current_price_and_distinct_source_moments():
    moment = datetime(2026, 11, 9, 20, 59, tzinfo=timezone.utc)
    answer = "Actuele AAPL-bron: USD 350,49 op 9 november 2026 om 20:59 UTC. Oud rapport: USD 351,19 op 9 november 2026 om 19:03 UTC."
    assert probe._answer_current_price(answer, Decimal("350.48999"))
    assert all(probe._answer_moments(answer, moment, Decimal("350.49")).values())
    assert not probe._old_claimed_current(answer)
    assert not probe._answer_current_price("USD 351,19 was de actuele koers.", Decimal("350.48999"))
    assert not all(probe._answer_moments("USD 350,49", moment, Decimal("350.49")).values())
    seconds = "Nieuwste bron is **USD 350,49**, gemeten op **9 november 2026 om 20:59:00 UTC**. Oud rapport **USD 351,19** op **9 november 2026 om 19:03:00 UTC**."
    assert all(probe._answer_moments(seconds, moment, Decimal("350.49")).values())
    wrong_zone = "Huidige AAPL-koers USD 350,49 op 9 november 2026 om 20:59 CET. Oud rapport USD 351,19 op 9 november 2026 om 19:03 UTC."
    assert not probe._answer_moments(wrong_zone, moment, Decimal("350.49"))["current_source_time_explained"]
    wrong_second = "Huidige AAPL-koers USD 350,49 op 9 november 2026 om 20:59:59 UTC. Oud rapport USD 351,19 op 9 november 2026 om 19:03:00 UTC."
    assert not probe._answer_moments(wrong_second, moment, Decimal("350.49"))["current_source_time_explained"]
    wrong_date = "Huidige AAPL-koers USD 350,49 op 8 november 2026 om 20:59:00 UTC. Oud rapport USD 351,19 op 9 november 2026 om 19:03:00 UTC."
    assert not probe._answer_moments(wrong_date, moment, Decimal("350.49"))["current_source_time_explained"]
    wrong_old = "Huidige AAPL-koers USD 350,49 op 9 november 2026 om 20:59:00 UTC. Oud rapport USD 351,19 op 8 november 2026 om 19:03:00 UTC."
    assert not probe._answer_moments(wrong_old, moment, Decimal("350.49"))["old_report_time_explained"]
    iso = "Nieuwste AAPL-koers USD 350,49 op 2026-11-09 20:59:00 UTC. Oud rapport USD 351,19 op 2026-11-09 19:03:00 UTC."
    assert all(probe._answer_moments(iso, moment, Decimal("350.49")).values())


def test_profile_is_protected_and_errors_are_allowlisted():
    assert "aapl_paper_quote_coach" in ALLOWED_PROFILES
    assert profile_error_category("aapl_paper_quote_coach", RuntimeError("aapl_source_unavailable")) == "aapl_source_unavailable"
    assert profile_error_category("aapl_paper_quote_coach", RuntimeError("secret owner=17")) == "aapl_probe_runtime_error"
    root = Path(__file__).resolve().parents[4]
    workflow = (root / ".github/workflows/finn-production-qa.yml").read_text()
    dispatcher = (root / "ops/qa/run_finn_production_qa.sh").read_text()
    assert "aapl_paper_quote_coach" in workflow and "aapl_paper_quote_coach" in dispatcher
    assert 'FINN_QA_ALLOW_AAPL_QUOTE_FIXTURE=0' in workflow
    assert 'FINN_QA_ALLOW_AAPL_QUOTE_FIXTURE=1' in workflow


def test_probe_rejects_unprotected_invocation(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_AAPL_QUOTE_FIXTURE", raising=False)
    with pytest.raises(RuntimeError, match="aapl_fixture_not_authorized"):
        probe.run("qa-123456-1-abcdef12-abcdef12")


def test_cleanup_failure_quarantines_inactive_child_and_fails_closed(monkeypatch):
    calls = []

    def fail_cleanup(*_args, **_kwargs):
        calls.append("cleanup")
        raise RuntimeError("private database detail")

    def quarantine(*_args, **_kwargs):
        calls.append("quarantine")

    monkeypatch.setattr(probe.fixture, "_cleanup", fail_cleanup)
    monkeypatch.setattr(probe.fixture, "_quarantine", quarantine)
    with pytest.raises(RuntimeError, match="^aapl_cleanup_failed$"):
        probe._finalize_fixture("qa-1-1-abcdef12-abcdef12", 2, 3, passed=True)
    assert calls == ["cleanup", "quarantine"]


def test_quarantine_failure_does_not_expose_driver_error(monkeypatch):
    def fail_quarantine(*_args, **_kwargs):
        raise RuntimeError("secret owner details")

    monkeypatch.setattr(probe.fixture, "_quarantine", fail_quarantine)
    with pytest.raises(RuntimeError, match="^aapl_quarantine_failed$"):
        probe._finalize_fixture("qa-1-1-abcdef12-abcdef12", 2, 3, passed=False)


def test_prepare_failure_reports_only_fixed_stage_and_class(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_args):
            raise RuntimeError("secret SQL and owner value")

    class Connection:
        def cursor(self):
            return Cursor()

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(probe.fixture, "_connection", lambda: Connection())
    with pytest.raises(RuntimeError, match="^aapl_prepare_identity_runtimeerror_failed$"):
        probe._prepare("qa-1-1-abcdef12-abcdef12", 2, 3)
    assert profile_error_category(
        "aapl_paper_quote_coach", RuntimeError("aapl_prepare_identity_runtimeerror_failed")
    ) == "aapl_prepare_identity_runtimeerror_failed"
    assert profile_error_category(
        "aapl_paper_quote_coach", RuntimeError("aapl_prepare_identity_secret_failed")
    ) == "aapl_probe_runtime_error"
