import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.services.finn_trade_review_service import FinnTradeReviewService, build_closed_positions, build_weekly_review_patterns, completed_reflection_week, unrecorded_plan_theme


START = datetime(2026, 10, 16, tzinfo=timezone.utc)


def test_reflection_uses_completed_amsterdam_calendar_weeks_across_dst():
    # 19 October starts a new local week; the one ending on 26 October is
    # 169 UTC hours because Amsterdam returns to winter time on the Sunday.
    monday, end_date, start, end = completed_reflection_week(
        datetime(2026, 10, 26, 5, tzinfo=timezone.utc), date(2026, 10, 19))
    assert (monday, end_date) == (date(2026, 10, 19), date(2026, 10, 26))
    assert start == datetime(2026, 10, 18, 22, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 25, 23, tzinfo=timezone.utc)
    assert end - start == timedelta(hours=169)
    _, _, spring_start, spring_end = completed_reflection_week(
        datetime(2026, 3, 30, 5, tzinfo=timezone.utc), date(2026, 3, 23))
    assert spring_end - spring_start == timedelta(hours=167)
    assert completed_reflection_week(datetime(2026, 10, 18, 21, 59, tzinfo=timezone.utc))[0] == date(2026, 10, 5)
    assert completed_reflection_week(datetime(2026, 10, 18, 22, tzinfo=timezone.utc))[0] == date(2026, 10, 12)
    for invalid in (date(2026, 10, 13), date(2026, 10, 19)):
        try:
            completed_reflection_week(datetime(2026, 10, 19, 5, tzinfo=timezone.utc), invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Only completed Monday–Sunday weeks may be selected")


def test_weekly_reflection_is_owner_scoped_and_persisted():
    calls = []

    class Result:
        def __init__(self, row=None, rows=None):
            self.row = row
            self.rows = rows or []

        def fetchone(self):
            return SimpleNamespace(_mapping=self.row)

        def fetchall(self):
            return self.rows

        def scalar_one(self):
            return datetime(2026, 10, 19, 6, tzinfo=timezone.utc)

    class Session:
        async def execute(self, statement, params):
            calls.append((str(statement), params))
            index = len(calls)
            if index == 1:
                return Result({"trades": 1, "plans": 1, "notes": 0,
                               "analyzed": 1, "pending": 0, "unavailable": 0})
            if index == 2:
                return Result(rows=[SimpleNamespace(id=9, origin="bot_position", has_plan=True,
                                                    analysis_status="ready", analysis_json={"observations": [
                                                        {"theme": "plan_followed", "text": "Volgens plan uitgevoerd."}]})])
            return Result()

        async def commit(self):
            pass

    result = asyncio.run(FinnTradeReviewService(Session()).weekly_report(7, date(2026, 10, 12)))
    assert result["week_start"] == "2026-10-12" and result["week_end"] == "2026-10-19"
    assert result["trades"] == 1 and result["patterns"][0]["review_ids"] == [9]
    assert len(calls) == 5
    for sql, params in calls[:3]:
        assert "user_id=:user_id" in sql or "l.user_id=:user_id" in sql
        assert "exit_at >= :start" in sql and "exit_at < :end" in sql
        assert params["user_id"] == 7
    assert "ON CONFLICT (user_id, week_start) DO UPDATE" in calls[3][0]
    assert calls[3][1]["week_start"] == date(2026, 10, 12)


def test_weekly_report_selection_does_not_hide_current_week_trade_dossiers():
    calls = []

    class Result:
        def fetchone(self):
            return SimpleNamespace(legacy_or_ambiguous=0, inconsistent=0, projection_pending=False)

        def fetchall(self):
            return []

        def scalar_one(self):
            return 1

    class Session:
        async def execute(self, statement, params):
            calls.append((str(statement), params))
            return Result()

    service = FinnTradeReviewService(Session())

    async def no_projection(_user_id):
        raise AssertionError("GET must not project or write")

    async def prior_week(_user_id, _week_start, *, persist):
        assert persist is False
        return {"week_start": "2026-10-12"}

    service._project = no_projection
    service.weekly_report = prior_week
    asyncio.run(service.list_reviews(7, week_start=date(2026, 10, 12)))
    dossier_queries = [(sql, params) for sql, params in calls if "FROM finn_trade_reviews" in sql and "ORDER BY exit_at DESC" in sql]
    assert dossier_queries
    for sql, params in dossier_queries:
        assert "WHERE user_id=:user_id" in sql
        assert "exit_at >= :start" not in sql
        assert params["user_id"] == 7


def test_empty_trade_review_list_avoids_weekly_queries_and_writes():
    calls = []

    class Result:
        def fetchone(self):
            return SimpleNamespace(legacy_or_ambiguous=0, inconsistent=0, projection_pending=False)

        def fetchall(self):
            return []

        def scalar_one(self):
            return 0

    class Session:
        async def execute(self, statement, params):
            calls.append(str(statement))
            return Result()

        async def commit(self):
            raise AssertionError("GET must not commit")

    result = asyncio.run(FinnTradeReviewService(Session()).list_reviews(7, week_start=date(2026, 10, 12)))
    assert result["total"] == 0
    assert result["weekly"]["week_start"] == "2026-10-12"
    assert result["weeks"] == ["2026-10-12"]
    assert len(calls) == 3
    assert all(sql.lstrip().startswith("SELECT") for sql in calls)


def test_weekly_reflection_read_does_not_upsert_or_commit():
    calls = []
    saved_summary = {
        "trades": 1, "plans": 0, "notes": 0, "analyzed": 0,
        "pending": 1, "unavailable": 0, "patterns": [],
        "confirmed_lesson_repetitions": [], "patterns_truncated": False,
    }

    class Result:
        def fetchone(self):
            return SimpleNamespace(_mapping={"trades": 1, "plans": 0, "notes": 0,
                                             "analyzed": 0, "pending": 1, "unavailable": 0})

        def fetchall(self):
            return []

        def one_or_none(self):
            return SimpleNamespace(summary=saved_summary,
                                   generated_at=datetime(2026, 10, 19, 6, tzinfo=timezone.utc))

    class Session:
        async def execute(self, statement, params):
            calls.append(str(statement))
            return Result()

        async def commit(self):
            raise AssertionError("GET must not commit")

    result = asyncio.run(FinnTradeReviewService(Session()).weekly_report(
        7, date(2026, 10, 12), persist=False))
    assert result["trades"] == 1
    assert result["generated_at"] == "2026-10-19T06:00:00+00:00"
    assert len(calls) == 4
    assert all(sql.lstrip().startswith("SELECT") for sql in calls)
    saved_summary["trades"] = 0
    changed = asyncio.run(FinnTradeReviewService(Session()).weekly_report(
        7, date(2026, 10, 12), persist=False))
    assert changed["trades"] == 1
    assert changed["generated_at"] is None


def test_exchange_plan_not_recorded_is_evidence_gap_not_behavioral_missing_plan():
    assert unrecorded_plan_theme("exchange_user_attested") == "plan_not_recorded"
    assert unrecorded_plan_theme("bybit_derivative_user_attested") == "plan_not_recorded"
    assert unrecorded_plan_theme("bot_position") == "missing_plan"


def test_weekly_reflection_keeps_plan_facts_separate_from_finn_observations():
    rows = [
        SimpleNamespace(id=8, origin="exchange_user_attested", has_plan=False,
                        analysis_status="pending", analysis_json=None),
        SimpleNamespace(id=9, origin="bot_position", has_plan=True,
                        analysis_status="ready", analysis_json={"observations": [
                            {"theme": "timing", "text": "De instap kwam later dan gepland."}]}),
        SimpleNamespace(id=10, origin="bot_position", has_plan=True,
                        analysis_status="ready", analysis_json={"observations": [
                            {"theme": "timing", "text": "Ook hier volgde een late instap."}]}),
    ]
    result = {item["theme"]: item for item in build_weekly_review_patterns(rows)}

    assert result["plan_not_recorded"] == {
        "theme": "plan_not_recorded", "review_ids": [8], "count": 1,
        "basis": "plan_record", "example": None,
    }
    assert result["timing"] == {
        "theme": "timing", "review_ids": [9, 10], "count": 2,
        "basis": "finn_analysis", "example": "De instap kwam later dan gepland.",
    }


def test_derivative_review_never_enters_eur_market_chart():
    service = FinnTradeReviewService(None)

    async def derivative_review(_user_id, _review_id):
        return {"origin": "bybit_derivative_user_attested"}

    service.get_review = derivative_review
    result = asyncio.run(service.get_chart(7, 10))
    assert result["status"] == "unavailable"
    assert result["chart"] is None


def fill(index, qty, cash, *, environment="paper", status="filled", bot_id=5, symbol="BTC",
         source="bot", valuation_version=2, exchange_symbol=None, exchange_order_id=None):
    return {
        "ledger_id": index, "bot_id": bot_id, "symbol": symbol,
        "order_id": index // 2 + 1, "qty_delta": Decimal(str(qty)),
        "cash_delta_eur": Decimal(str(cash)),
        "price_eur": Decimal(str(abs(cash / qty))),
        "ts": START + timedelta(minutes=index),
        "environment": environment, "order_status": status,
        "source": source, "valuation_version": valuation_version,
        "exchange_symbol": exchange_symbol or (f"{symbol}/EUR" if environment == "live" else None),
        "exchange_order_id": exchange_order_id or (f"exchange-{index}" if environment == "live" else None),
        "plan_snapshot": {"risk": {"max": 20}} if index == 1 else None,
        "plan_captured_at": START if index == 1 else None,
        "plan_order_id": index // 2 + 1,
        "plan_decision_id": 4 if index == 1 else None,
    }


def test_partial_fills_and_partial_exits_become_one_completed_position():
    fills = [fill(1, 0.4, -40), fill(2, 0.6, -66), fill(3, -0.3, 36), fill(4, -0.7, 84)]
    reviews, excluded = build_closed_positions(fills, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    assert reviews[0]["opening_ledger_id"] == 1
    assert reviews[0]["closing_ledger_id"] == 4
    assert reviews[0]["pnl_eur_before_fees"] == Decimal(14)
    assert len(reviews[0]["fills"]) == 4
    assert reviews[0]["plan_snapshot"] == {"risk": {"max": 20}}
    assert excluded == {"legacy_or_ambiguous": 0, "inconsistent": 0}


def test_utc_plan_capture_and_naive_utc_ledger_timestamp_keep_entry_plan():
    rows = [fill(1, 1, -100), fill(2, -1, 110)]
    for row in rows:
        row["ts"] = row["ts"].replace(tzinfo=None)
    rows[0]["plan_captured_at"] = START
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert excluded == {"legacy_or_ambiguous": 0, "inconsistent": 0}
    assert len(reviews) == 1
    assert reviews[0]["plan_snapshot"] == {"risk": {"max": 20}}
    assert reviews[0]["plan_provenance"]["source"] == "bot_order_context"


def test_manual_entry_keeps_linked_plan_without_claiming_plan_adherence():
    rows = [fill(1, 1, -100, source="manual"),
            fill(2, -1, 110, source="manual")]
    rows[0]["plan_snapshot"] = {
        "linked_setup": {"id": 7, "min_benchmark_score": 61},
        "linked_strategy": {"id": 11, "name": "BTC plan"},
        "plan_adherence": "not_assessed",
    }
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert excluded == {"legacy_or_ambiguous": 0, "inconsistent": 0}
    assert reviews[0]["plan_snapshot"]["linked_strategy"]["name"] == "BTC plan"
    assert reviews[0]["plan_provenance"]["relation"] == "linked_plan_at_manual_entry_not_adherence"


def test_exit_order_plan_is_not_relabelled_as_original_entry_plan():
    rows = [fill(1, 1, -100), fill(2, -1, 110)]
    rows[0]["plan_snapshot"] = None
    rows[1]["plan_snapshot"] = {"entry_plan": "added after entry"}
    rows[1]["plan_captured_at"] = rows[1]["ts"] - timedelta(seconds=1)
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    assert reviews[0]["plan_snapshot"] is None
    assert reviews[0]["plan_provenance"] is None


def test_open_and_legacy_positions_do_not_get_reviews():
    rows = [fill(1, -0.5, 60), fill(2, 0.2, -20)]
    reviews, excluded = build_closed_positions(rows, {(5, "BTC"): Decimal("0.5")}, {(5, "BTC"): Decimal("0.2")})
    assert reviews == []
    assert excluded["legacy_or_ambiguous"] > 0


def test_new_complete_position_after_legacy_flat_is_reviewed():
    rows = [fill(1, -0.5, 60), fill(2, 1, -100), fill(3, -1, 110)]
    reviews, excluded = build_closed_positions(
        rows, {(5, "BTC"): Decimal("0.5")}, {(5, "BTC"): Decimal(0)},
    )
    assert [review["opening_ledger_id"] for review in reviews] == [2]
    assert excluded["legacy_or_ambiguous"] == 1


def test_unsettled_order_and_open_position_do_not_get_reviews():
    rows = [fill(1, 1, -100), fill(2, -1, 110, status="sent")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == []


def test_unknown_or_mixed_environment_is_excluded_until_flat():
    rows = [fill(1, 1, -100, environment=None), fill(2, -1, 120, environment="live")]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == []
    assert excluded["legacy_or_ambiguous"] == 1


def test_inconsistent_portfolio_blocks_projection():
    rows = [fill(1, 1, -100), fill(2, -1, 120)]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal("0.1")})
    assert reviews == []
    assert excluded["inconsistent"] == 1


def test_losses_are_reviewed_too():
    reviews, _ = build_closed_positions(
        [fill(1, 1, -100), fill(2, -1, 80)], {}, {(5, "BTC"): Decimal(0)},
    )
    assert len(reviews) == 1
    assert reviews[0]["pnl_eur_before_fees"] == Decimal(-20)


def test_manual_and_bot_orders_in_same_position_are_covered():
    rows = [fill(1, 1, -100, source="manual"), fill(2, -1, 110, source="bot")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    assert reviews[0]["execution_sources"] == ["bot", "manual"]
    assert reviews[0]["fills"][0]["source"] == "manual"


def test_manual_confirmed_decision_is_classified_manual_and_auto_decision_bot():
    rows = [fill(1, 1, -100, source="manual"), fill(2, -1, 110, source="bot")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews[0]["execution_sources"] == ["bot", "manual"]
    assert [part["source"] for part in reviews[0]["fills"]] == ["manual", "bot"]


def test_no_decision_manual_order_is_classified_manual():
    rows = [fill(1, 1, -100, source="manual"), fill(2, -1, 110, source="manual")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews[0]["execution_sources"] == ["manual"]


def test_unknown_decision_executor_does_not_invent_source():
    rows = [fill(1, 1, -100, source=None), fill(2, -1, 110, source="bot")]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == [] and excluded["legacy_or_ambiguous"] == 1


def test_unverified_paper_eur_amount_is_not_used_for_pnl():
    rows = [fill(1, 1, -100, valuation_version=1), fill(2, -1, 120)]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == [] and excluded["legacy_or_ambiguous"] == 1


def test_live_confirmed_eur_exchange_pair_is_required():
    rows = [fill(1, 1, -100, environment="live", valuation_version=1),
            fill(2, -1, 120, environment="live", valuation_version=1)]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    rows[1]["exchange_symbol"] = "BTC/USDT"
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == [] and excluded["legacy_or_ambiguous"] == 1
