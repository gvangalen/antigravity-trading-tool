from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from backend.scripts import probe_protected_manual_trade_fixture_prepare as fixture


REPO_ROOT = Path(__file__).resolve().parents[4]


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalars(self):
        return self

    def one(self):
        assert len(self.rows) == 1
        return self.rows[0]


def test_target_setups_are_additive_idempotent_and_drift_checked(monkeypatch):
    rows = [
        {"id": 1, "name": "Original BTC 1", "description": None},
        {"id": 2, "name": "Original BTC 2", "description": None},
    ]
    created = []

    class Session:
        async def execute(self, statement, params):
            assert str(statement).lstrip().upper().startswith("SELECT")
            assert params["owner"] == 42
            return _Rows([{"state": dict(row)} for row in rows])

    async def create(_self, payload, owner, tags):
        assert owner == 42 and tags == [fixture.MARKER]
        assert payload["market_id"] == 7 and payload["symbol"] == "BTC"
        created.append(dict(payload))
        rows.append({
            "id": 3, "user_id": owner, "name": payload["name"],
            "symbol": "BTC", "market_id": 7, "timeframe": "1d",
            "setup_type": "trade", "dca_frequency": None, "dca_day": None,
            "dca_month_day": None, "account_type": None,
            "min_investment": None, "tags": [fixture.MARKER],
            "trend": None, "score_logic": None, "favorite": False,
            "explanation": fixture.MARKER, "description": fixture.MARKER,
            "action": None, "category": None,
            "min_macro_score": None, "max_macro_score": None,
            "min_technical_score": None, "max_technical_score": None,
            "min_market_score": None, "max_market_score": None,
            "min_benchmark_score": 0, "max_benchmark_score": 100,
        })
        return 3

    monkeypatch.setattr(fixture.SetupRepository, "create_setup", create)

    async def check():
        assert await fixture._setup(Session(), 42, "BTC", "EUR", 7) == (3, True)
        assert await fixture._setup(Session(), 42, "BTC", "EUR", 7) == (3, False)
        assert len(created) == 1
        assert rows[:2] == [
            {"id": 1, "name": "Original BTC 1", "description": None},
            {"id": 2, "name": "Original BTC 2", "description": None},
        ]
        rows[-1]["max_benchmark_score"] = 99
        with pytest.raises(RuntimeError, match="manual_trade_target_setup_drift"):
            await fixture._setup(Session(), 42, "BTC", "EUR", 7)
        rows[-1]["max_benchmark_score"] = 100
        rows[-1]["min_investment"] = 1
        with pytest.raises(RuntimeError, match="manual_trade_target_setup_drift"):
            await fixture._setup(Session(), 42, "BTC", "EUR", 7)

    asyncio.run(check())


def test_aapl_reading_must_be_bound_to_marked_config():
    class Session:
        def __init__(self, ids, source_record_id):
            self.ids = ids
            self.source_record_id = source_record_id

        async def execute(self, statement, params):
            assert params["owner"] == 42
            if "FROM market_data_indicators" in str(statement):
                return _Rows(self.ids)
            return _Rows([{"provenance": fixture.MARKER,
                           "source_record_id": self.source_record_id}])

    async def check():
        assert await fixture._aapl_reading_scope(Session([], None), 42) is None
        assert await fixture._aapl_reading_scope(Session([11], 11), 42) == 11
        for ids, linked in (([11], None), ([11], 12), ([11, 12], 11), ([], 11)):
            with pytest.raises(RuntimeError, match="manual_trade_aapl_reading_"):
                await fixture._aapl_reading_scope(Session(ids, linked), 42)

    asyncio.run(check())


@pytest.mark.parametrize("score,expected_reduced,expected_wait", [
    (0, [1, 100], [100, 100]),
    (49.5, [51, 100], [100, 100]),
    (50, [51, 100], [100, 100]),
    (98, [99, 100], [0, 0]),
    (100, [0, 99], [0, 0]),
])
def test_qa_bands_derive_from_measured_score(score, expected_reduced, expected_wait):
    assert fixture._scenario_band(score, "reduced_risk") == expected_reduced
    assert fixture._scenario_band(score, "wait") == expected_wait
    with pytest.raises(RuntimeError, match="manual_trade_benchmark_score_invalid"):
        fixture._scenario_band(float("nan"), "wait")


def test_protected_prepare_requires_flag_before_journal_or_writes(tmp_path, monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE", raising=False)
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    journal = tmp_path / "prepare.journal.json"
    with pytest.raises(RuntimeError, match="manual_trade_fixture_not_authorized"):
        asyncio.run(fixture.run(
            journal_path=journal, release_sha="a" * 40,
            fixture_namespace="qa-123-1-aaaaaaaa-bbbbbbbb"))
    assert not journal.exists()


def test_failed_protected_prepare_keeps_private_phase_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    journal = tmp_path / "prepare.journal.json"

    async def configured(owner):
        assert owner == 42
        return {"markets": {"BTC": 7, "ETH": 8, "AAPL": None},
                "btc_setup_hash": "abc", "profile_created": True,
                "setups_created": 3, "configs_created": 9}

    async def source_ready():
        return None

    async def failed_refresh(owner, markets):
        assert owner == 42 and markets["BTC"] == 7
        raise RuntimeError("manual_trade_macro_source_unavailable")

    monkeypatch.setattr(fixture, "configure_bound_fixture", configured)
    monkeypatch.setattr(fixture, "_source_preflight", source_ready)
    monkeypatch.setattr(fixture, "refresh_genuine_sources", failed_refresh)
    with pytest.raises(RuntimeError, match="manual_trade_macro_source_unavailable"):
        asyncio.run(fixture.run(
            journal_path=journal, release_sha="a" * 40,
            fixture_namespace="qa-123-1-aaaaaaaa-bbbbbbbb"))
    content = json.loads(journal.read_text())
    assert content["phase"] == "failed"
    assert content["setups_created"] == 3
    assert os.stat(journal).st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="manual_trade_macro_source_unavailable"):
        asyncio.run(fixture.run(
            journal_path=journal, release_sha="a" * 40,
            fixture_namespace="qa-123-1-aaaaaaaa-bbbbbbbb"))
    assert json.loads(journal.read_text())["phase"] == "failed"


def test_wrong_namespace_and_owner_never_create_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE", "1")
    journal = tmp_path / "prepare.journal.json"
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    with pytest.raises(RuntimeError, match="manual_trade_fixture_namespace_invalid"):
        asyncio.run(fixture.run(
            journal_path=journal, release_sha="a" * 40,
            fixture_namespace="unbound"))
    monkeypatch.setenv("FINN_QA_USER_ID", "not-a-bound-owner")
    with pytest.raises(RuntimeError, match="fixture_binding_invalid"):
        asyncio.run(fixture.run(
            journal_path=journal, release_sha="a" * 40,
            fixture_namespace="qa-123-1-aaaaaaaa-bbbbbbbb"))
    assert not journal.exists()


def test_missing_real_plan_source_blocks_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    journal = tmp_path / "prepare.journal.json"

    async def unavailable():
        raise ValueError("manual_trade_candles_stale")

    async def must_not_configure(_owner):
        raise AssertionError("configuration_written_before_source_check")

    monkeypatch.setattr(fixture, "_source_preflight", unavailable)
    monkeypatch.setattr(fixture, "configure_bound_fixture", must_not_configure)
    with pytest.raises(ValueError, match="manual_trade_candles_stale"):
        asyncio.run(fixture.run(
            journal_path=journal, release_sha="a" * 40,
            fixture_namespace="qa-123-1-aaaaaaaa-bbbbbbbb"))
    assert json.loads(journal.read_text())["phase"] == "failed"


def test_source_preflight_preserves_only_pair_and_typed_source_reason(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as suggestion

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def rollback(self):
            return None

    async def candles(_session, *, asset, quote_currency):
        if asset == "AAPL":
            raise ValueError("twelve_data_unavailable:429")
        return 1, []

    monkeypatch.setattr(fixture, "async_session_factory", Session)
    monkeypatch.setattr(suggestion, "_source_candles", candles)
    monkeypatch.setattr(suggestion, "derive_suggested_plan", lambda **_kwargs: {})
    with pytest.raises(RuntimeError, match="^manual_trade_fixture_source_preflight_failed$") as caught:
        asyncio.run(fixture._source_preflight())
    assert caught.value.manual_trade_asset == "AAPL"
    assert caught.value.manual_trade_source_reason == "twelve_data_unavailable:429"


def test_read_only_preflight_artifact_redacts_provider_failure(tmp_path, monkeypatch):
    from backend.scripts import run_finn_production_qa as runner

    report_path = tmp_path / "report.json"
    args = SimpleNamespace(
        release_sha="a" * 40, run_label="preflight-test", runner_revision=None,
        report_path=str(report_path), workflow_run_id="local", profile="manual_trade_fixture_preflight",
        manifest_id="none", manifest_bundle_path=None, checkout=str(tmp_path),
        release_marker=str(tmp_path / "release"), base_url="https://example.invalid",
        dry_preflight=False, fixture_namespace=None,
    )
    monkeypatch.setattr(runner, "parse_args", lambda: args)
    monkeypatch.setattr(runner, "release_identity", lambda **_kwargs: {"matches": True})
    monkeypatch.setattr(runner, "issue_fixture_token", lambda **_kwargs: "local-token")
    monkeypatch.setattr(runner, "authenticated_preflight",
                        lambda **_kwargs: {"fixture_authenticated": True})

    def fail_preflight():
        error = ValueError("private provider token=secret")
        error.manual_trade_failed_phase = "source_candles"
        error.manual_trade_asset = "AAPL"
        error.manual_trade_source_reason = str(error)
        raise error

    monkeypatch.setattr(runner, "manual_trade_fixture_preflight", fail_preflight)
    assert runner.main() == 1
    report = json.loads(report_path.read_text())
    assert report["error_category"] == "manual_trade_fixture_preflight_runtime_error"
    assert report["manual_trade_failure_diagnostic"] == {
        "failed_phase": "source_candles", "asset": "AAPL",
        "source_reason": "source_unavailable",
    }
    assert "secret" not in report_path.read_text()


def test_prepare_profile_has_distinct_protected_authorization_boundary():
    from backend.scripts import run_finn_production_qa as runner

    assert "manual_trade_fixture_prepare" in runner.ALLOWED_PROFILES
    assert runner.profile_error_category(
        "manual_trade_fixture_prepare", RuntimeError("private owner details"),
    ) == "manual_trade_fixture_prepare_runtime_error"
    source_error = RuntimeError("manual_trade_fixture_source_preflight_failed")
    source_error.manual_trade_failed_phase = "source_preflight"
    source_error.manual_trade_asset = "AAPL"
    source_error.manual_trade_source_reason = "twelve_data_unavailable:429"
    assert runner.profile_error_category("manual_trade_fixture_prepare", source_error) == (
        "manual_trade_fixture_source_preflight_failed"
    )
    assert runner.safe_manual_trade_failure_diagnostic(
        "manual_trade_fixture_prepare", source_error,
    ) == {"failed_phase": "source_preflight", "asset": "AAPL",
          "source_reason": "twelve_data_unavailable:429"}
    source_error.manual_trade_source_reason = "private provider token=secret"
    assert runner.safe_manual_trade_failure_diagnostic(
        "manual_trade_fixture_prepare", source_error,
    )["source_reason"] == "source_unavailable"
    workflow = (REPO_ROOT / ".github/workflows/finn-production-qa.yml").read_text()
    assert "FINN_QA_ALLOW_MANUAL_TRADE_PREPARE=1" in workflow
    assert '"$ALLOW_SAFE_FIXTURE_EXECUTION" != "false"' in workflow
    script = REPO_ROOT / "ops/qa/run_finn_production_qa.sh"
    env = os.environ.copy()
    env.pop("FINN_QA_ALLOW_FIXTURE_ACTIONS", None)
    env.pop("FINN_QA_ALLOW_FIXTURE_EXECUTION", None)
    rejected = subprocess.run(
        [str(script), "a" * 40, "manual_trade_fixture_prepare", "none", "qa-prepare"],
        env=env, capture_output=True, text=True,
    )
    assert rejected.returncode == 2
