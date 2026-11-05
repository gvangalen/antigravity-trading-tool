import struct
import zlib
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.services.finn_trade_analysis_service import evidence_context, validate_analysis
from backend.services.finn_trade_analysis_service import FinnTradeAnalysisService
from backend.services.finn_trade_review_service import FinnTradeReviewService
from backend.services.finn_trade_chart_service import historical_eur_chart
from backend.services.ai_usage_observability_service import get_ai_usage_context
from backend.services.finn_trade_screenshot import MAX_BYTES, PNG_SIGNATURE, validate_png


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def _png(width=1, height=1, extra=b""):
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", pixels) + extra + _chunk(b"IEND", b"")


def test_png_validation_accepts_small_rgb_image():
    data, width, height, digest = validate_png(_png())
    assert data == _png()
    assert (width, height) == (1, 1)
    assert len(digest) == 64


@pytest.mark.parametrize("data", [
    _png(width=5000),
    _png()[:-3],
    _png() + b"extra",
])
def test_png_validation_rejects_metadata_dimensions_truncation_and_trailing_data(data):
    with pytest.raises(HTTPException):
        validate_png(data)


def test_png_validation_rejects_oversized_body():
    with pytest.raises(HTTPException) as raised:
        validate_png(PNG_SIGNATURE + b"x" * MAX_BYTES)
    assert raised.value.status_code == 422


def test_png_metadata_is_stripped_before_private_storage():
    data, _, _, _ = validate_png(_png(extra=_chunk(b"tEXt", b"hidden")))
    assert b"hidden" not in data
    assert b"tEXt" not in data


def _analysis(text):
    return {"summary": text, "uncertainty": "Het plan ontbreekt.",
            "question": "Welke afweging maakte je bij de exit?",
            "suggested_lesson": "Leg je afweging vooraf vast.",
            "observations": [{"text": "De exit is geregistreerd.",
                              "evidence_ids": ["fill:1"], "theme": "exit_process"}]}


def test_trade_analysis_receives_bounded_owner_profile(monkeypatch):
    from backend.services import finn_trade_analysis_service as module

    class User:
        ai_preferences = {
            "trader_type": "swing_trader",
            "risk_profile": "conservative",
            "behavior_flags": ["fomo"],
            "trader_context": "Ik wil mijn exits rustig evalueren.",
        }

    class Repository:
        def __init__(self, session):
            pass

        async def get_by_id(self, user_id):
            assert user_id == 7
            return User()

    monkeypatch.setattr(module, "UserRepository", Repository)
    profile = asyncio.run(FinnTradeAnalysisService(object())._trader_profile_context(7))
    assert profile["source"] == "owner_profile"
    assert profile["preferences"]["trader_types"] == ["swing_trader"]
    assert profile["preferences"]["risk_profiles"] == ["conservative"]
    assert profile["preferences"]["behavior_flags"] == ["fomo"]
    assert profile["personal_context_untrusted"] == "Ik wil mijn exits rustig evalueren."


def test_ai_rejects_unbound_evidence_ids():
    result = _analysis("De trade is gesloten.")
    result["observations"][0]["evidence_ids"] = ["fill:999"]
    with pytest.raises(ValueError):
        validate_analysis(result, {"fill:1"})


def test_model_cannot_assess_plan_following_from_fills_without_original_plan():
    raw = _analysis("De trade is gesloten.")
    raw["observations"][0]["theme"] = "plan_followed"
    with pytest.raises(ValueError, match="Original plan"):
        validate_analysis(raw, {"fill:1"})
    with pytest.raises(ValueError, match="Original plan"):
        validate_analysis(raw, {"fill:1", "plan:snapshot"})
    raw["observations"][0]["evidence_ids"].append("plan:snapshot")
    assert validate_analysis(raw, {"fill:1", "plan:snapshot"})["observations"][0]["theme"] == "plan_followed"


def test_real_provider_selection_contract_retries_an_unbound_response(monkeypatch):
    from backend.services import finn_trade_analysis_service as module
    calls = []

    async def fake_ai(**kwargs):
        calls.append(kwargs)
        raw = _analysis("Modeltekst wordt niet getoond")
        if len(calls) == 1:
            raw["observations"][0]["evidence_ids"] = []
        return raw

    monkeypatch.setattr(module.openai_client, "ask_gpt_json_async", fake_ai)
    result = asyncio.run(module._validated_model_analysis(
        {"pnl_eur_before_fees": "10", "plan": None}, {"fill:1"}, image=None,
    ))
    assert len(calls) == 2
    assert calls[0]["model_override"] == "gpt-6-luna"
    assert '"allowed_evidence_ids": ["fill:1"]' in calls[0]["prompt"]
    assert '"plan_followed"' not in calls[0]["prompt"]
    assert "repair_instruction" in calls[1]["prompt"]
    assert result["observations"][0]["evidence_ids"] == ["fill:1"]


def test_provider_error_does_not_trigger_an_unbounded_repair_loop(monkeypatch):
    from backend.services import finn_trade_analysis_service as module
    calls = []

    async def fake_ai(**kwargs):
        calls.append(kwargs)
        return {"error": "provider_unavailable"}

    monkeypatch.setattr(module.openai_client, "ask_gpt_json_async", fake_ai)
    with pytest.raises(ValueError, match="AI unavailable"):
        asyncio.run(module._validated_model_analysis({}, {"fill:1"}, image=None))
    assert len(calls) == 1


def test_question_preserves_grounded_model_answer():
    context = {"origin": "bot_position", "environment": "paper", "entry_at": "2026-10-18T10:00:00Z",
               "exit_at": "2026-10-18T12:00:00Z", "entry_value_eur": "100.00",
               "exit_value_eur": "99.75", "pnl_eur_before_fees": "-0.25", "plan": None}
    result = validate_analysis(_analysis("De verkoop staat vast; je reden ontbreekt."),
                               {"fill:1"}, context, question_mode=True)
    assert result["summary"] == "De verkoop staat vast; je reden ontbreekt."
    assert result["analysis_source"] == "ai_generated"


def test_question_still_rejects_unbound_evidence_without_model_prose():
    with pytest.raises(ValueError, match="Ungrounded"):
        validate_analysis({"observations": [{"theme": "evidence_gap", "evidence_ids": ["fill:999"]}]},
                          {"fill:1"}, {}, question_mode=True)


def test_paper_review_status_describes_cash_flow_including_simulated_costs():
    row = {"execution_environment": "paper", "pnl_status": "before_fees_eur",
           "pnl_eur_before_fees": Decimal("-0.25"),
           "analysis_json": {"summary": "Het geregistreerde resultaat vóór kosten is €-0.25.",
                             "observations": [{"text": "De exit staat vast."}]}}
    presented = FinnTradeReviewService._presented_review(row)
    assert presented["pnl_status"] == "paper_cash_flow_including_simulated_costs"
    assert presented["pnl_eur_before_fees"] == Decimal("-0.25")
    assert "Paper-resultaat op basis van virtuele kassastromen" in presented["analysis_json"]["summary"]
    assert row["analysis_json"]["summary"] == "Het geregistreerde resultaat vóór kosten is €-0.25."
    assert row["pnl_status"] == "before_fees_eur"
    assert FinnTradeReviewService._presented_review({**row, "execution_environment": "live"})["pnl_status"] == "before_fees_eur"


def test_paper_ai_facts_label_result_including_simulated_costs():
    review = {
        "id": 26, "symbol": "BTC", "execution_environment": "Paper",
        "entry_at": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "exit_at": datetime(2026, 11, 3, tzinfo=timezone.utc),
        "pnl_eur_before_fees": Decimal("-0.03"), "fills": [],
    }
    facts, _ = evidence_context(review)
    assert facts["pnl_eur_including_simulated_costs"] == "-0.03"
    assert "pnl_eur_before_fees" not in facts
    assert facts["pnl_status"] == "paper_cash_flow_including_simulated_costs"
    assert facts["fees_unknown"] is False


def test_only_server_supplied_confirmed_lesson_can_be_rendered():
    context = {"prior_user_confirmed_lessons_untrusted": [{
        "review_id": 12, "symbol": "BTC", "lesson_text_untrusted": "Mijn bevestigde les",
        "confirmed_at": "2026-10-15T12:00:00+00:00",
        "relation_to_entry": "confirmed_before_entry",
    }]}
    raw = _analysis("Modeltekst is geen gebruikersles")
    raw["prior_lesson_review_id"] = 12
    result = validate_analysis(raw, {"fill:1"}, context)
    assert result["prior_lesson"]["lesson_text"] == "Mijn bevestigde les"
    assert result["prior_lesson"]["source"] == "user_confirmed_prior_reflection"
    assert result["summary"] == "Modeltekst is geen gebruikersles"
    raw["prior_lesson_review_id"] = 999
    assert "prior_lesson" not in validate_analysis(raw, {"fill:1"}, context)


def test_prior_lesson_query_is_owner_scoped_and_before_trade_entry():
    from types import SimpleNamespace

    entry = datetime(2026, 10, 16, tzinfo=timezone.utc)

    class Result:
        def fetchall(self):
            return [SimpleNamespace(review_id=8, symbol="BTC",
                                    lesson_text="Ik wil een reden vastleggen",
                                    evidence_revision=1,
                                    confirmed_at=datetime(2026, 10, 15, tzinfo=timezone.utc))]

    class Session:
        async def execute(self, query, params):
            sql = str(query)
            assert "l.user_id=:user_id" in sql and "r.user_id=l.user_id" in sql
            assert "l.confirmed_at<=:entry_at" in sql and "r.exit_at<:entry_at" in sql
            assert "l.evidence_revision=r.input_revision" in sql
            assert "LIMIT 5" in sql
            assert params == {"user_id": 77, "review_id": 9, "entry_at": entry,
                              "symbol": "BTC"}
            return Result()

    async def exercise():
        lessons = await FinnTradeAnalysisService(Session())._prior_confirmed_lessons(
            77, {"id": 9, "entry_at": entry, "symbol": "BTC"})
        assert len(lessons) == 1
        assert lessons[0]["relation_to_entry"] == "confirmed_before_entry"
        assert lessons[0]["authority"].startswith("user_confirmed")

    asyncio.run(exercise())


def test_confirmed_lesson_retry_is_noop_but_changed_evidence_requires_reconfirmation():
    from types import SimpleNamespace

    class Session:
        def __init__(self, evidence_revision):
            self.evidence_revision = evidence_revision
            self.writes = []

        async def execute(self, query, params=None):
            sql = str(query)
            if "pg_advisory_xact_lock" in sql:
                return _Result()
            if "SELECT input_revision FROM finn_trade_reviews" in sql:
                return _Result(2)
            if "SELECT lesson_text,status,evidence_revision" in sql:
                return _Result(SimpleNamespace(
                    lesson_text="Ik leg mijn exitreden vast", status="active",
                    evidence_revision=self.evidence_revision))
            if "SELECT id,analysis_json->'prior_lesson_candidate_ids'" in sql:
                return _Result([])
            self.writes.append((sql, params))
            return _Result()

        async def commit(self):
            pass

    async def exercise():
        for prior_revision, expected_writes in ((2, 0), (1, 1)):
            session = Session(prior_revision)
            service = FinnTradeReviewService(session)

            async def detail(*_):
                return {"id": 9}

            service.get_review = detail
            assert await service.set_lesson(77, 9, "Ik leg mijn exitreden vast") == {"id": 9}
            assert len(session.writes) == expected_writes
            if expected_writes:
                assert session.writes[0][1]["revision"] == 2

    asyncio.run(exercise())


def test_prior_lesson_change_invalidates_transitive_cached_analyses():
    from types import SimpleNamespace
    from backend.services.finn_trade_review_service import dependent_review_ids

    rows = [SimpleNamespace(id=2, candidate_ids=[1]),
            SimpleNamespace(id=3, candidate_ids=[2]),
            SimpleNamespace(id=4, candidate_ids=[3]),
            SimpleNamespace(id=5, candidate_ids=[99])]
    assert dependent_review_ids(1, rows) == [2, 3, 4]

    class Session:
        async def execute(self, query, params=None):
            sql = str(query)
            assert params["user_id"] == 77
            if "SELECT id,analysis_json" in sql:
                return _Result(rows)
            assert "UPDATE finn_trade_reviews" in sql
            assert params["review_ids"] == [2, 3, 4]
            assert "id=ANY(CAST(:review_ids AS BIGINT[]))" in sql
            return _Result()

    asyncio.run(FinnTradeReviewService(Session())._invalidate_lesson_dependents(77, 1))


def test_luna_writes_review_and_evidence_remains_bound():
    raw = _analysis("De automatische exit beperkte het verlies; de reden voor de instap is onbekend.")
    raw["observations"][0]["text"] = "De geregistreerde verkoop sloot de positie."
    result = validate_analysis(raw, {"fill:1"})
    assert result["format_version"] == 3
    assert result["analysis_source"] == "ai_generated"
    assert result["summary"] == raw["summary"]
    assert result["observations"][0]["text"] == raw["observations"][0]["text"]
    assert result["observations"][0]["evidence_ids"] == ["fill:1"]
    assert result["suggested_lesson"] == raw["suggested_lesson"]


def test_incomplete_model_prose_is_rejected():
    raw = _analysis("De trade is gesloten.")
    del raw["question"]
    with pytest.raises(ValueError, match="Invalid analysis question"):
        validate_analysis(raw, {"fill:1"})


def test_exchange_review_retains_user_attested_closure_boundary():
    raw = _analysis("De uitvoering is geregistreerd; de volledige sluiting is door jou bevestigd.")
    raw["observations"][0]["evidence_ids"] = ["exchange_fill:12", "closure:user-confirmed"]
    result = validate_analysis(raw, {"exchange_fill:12", "closure:user-confirmed"})
    assert result["summary"] == raw["summary"]
    assert result["observations"][0]["evidence_ids"] == ["exchange_fill:12", "closure:user-confirmed"]


def test_screenshot_claim_must_cite_uploaded_screenshot():
    raw = _analysis("De trade is gesloten.")
    raw["observations"][0]["evidence_ids"] = ["screenshot:user-upload"]
    with pytest.raises(ValueError, match="Ungrounded"):
        validate_analysis(raw, {"fill:1"})
    result = validate_analysis(raw, {"screenshot:user-upload"})
    assert result["observations"][0]["text"] == raw["observations"][0]["text"]


def test_question_path_persists_model_authored_answer(monkeypatch):
    from backend.services import finn_trade_analysis_service as module

    async def exercise():
        now = datetime.now(timezone.utc)
        review = {
            "id": 4, "symbol": "BTC", "execution_environment": "paper",
            "entry_at": now, "exit_at": now, "entry_value_eur": Decimal(100),
            "exit_value_eur": Decimal(110), "pnl_eur_before_fees": Decimal(10),
            "fills": [{"ledger_id": 1, "side": "sell", "at": now.isoformat(),
                       "qty": "1", "cash_eur": "110", "price_eur": "110"}],
            "plan_snapshot": None, "note": "", "candles_status": "unavailable",
            "candles_reason": "missing", "has_screenshot": False, "input_revision": 0,
        }

        class Session:
            def __init__(self): self.saved = []
            async def execute(self, query, params=None):
                sql = str(query)
                if "pg_advisory_xact_lock" in sql: return _Result()
                if "SELECT input_revision" in sql: return _Result(0)
                if "INSERT INTO finn_trade_review_messages" in sql:
                    self.saved.append(params); return _Result()
                raise AssertionError(sql)
            async def commit(self): pass

        session = Session(); service = FinnTradeAnalysisService(session)
        service.reviews.get_review = lambda *_: asyncio.sleep(0, result=review)
        service._reserve_user_ai_call = lambda *_args, **_kw: asyncio.sleep(0)
        service._prior_confirmed_lessons = lambda *_: asyncio.sleep(0, result=[])
        service._trader_profile_context = lambda *_: asyncio.sleep(0, result={"preferences": {"risk_profile": "conservative"}})
        async def fake_ai(**kwargs):
            assert "conservative" in kwargs["prompt"]
            return _analysis("De exit sloot de positie; waarom koos je destijds voor de instap?")
        monkeypatch.setattr(module.openai_client, "ask_gpt_json_async", fake_ai)
        result = await service.ask(77, 4, "Wat gebeurde er bij de exit?")
        assert result["summary"].startswith("De exit sloot")
        assert result["analysis_source"] == "ai_generated"
        assert "De exit sloot" in session.saved[-1]["content"]
        assert session.saved[-1]["model"] == "gpt-6-luna"
    asyncio.run(exercise())


def test_question_provider_failure_does_not_persist_fake_coach_analysis(monkeypatch):
    from backend.services import finn_trade_analysis_service as module
    async def exercise():
        now = datetime.now(timezone.utc)
        review = {"id": 4, "symbol": "BTC", "execution_environment": "paper",
                  "entry_at": now, "exit_at": now, "entry_value_eur": Decimal("100"),
                  "exit_value_eur": Decimal("99.75"), "pnl_eur_before_fees": Decimal("-0.25"),
                  "fills": [{"ledger_id": 1, "side": "sell", "at": now.isoformat(),
                             "qty": "1", "cash_eur": "99.75", "price_eur": "100"}],
                  "plan_snapshot": None, "note": "", "candles_status": "unavailable",
                  "has_screenshot": False, "input_revision": 0}
        class Session:
            def __init__(self): self.saved = []
            async def execute(self, query, params=None):
                sql = str(query)
                if "SELECT input_revision" in sql: return _Result(0)
                if "INSERT INTO finn_trade_review_messages" in sql: self.saved.append(params)
                elif "pg_advisory_xact_lock" not in sql: raise AssertionError(sql)
                return _Result()
            async def commit(self): pass
        service = FinnTradeAnalysisService(Session())
        service.reviews.get_review = lambda *_: asyncio.sleep(0, result=review)
        service._reserve_user_ai_call = lambda *_args, **_kw: asyncio.sleep(0)
        service._prior_confirmed_lessons = lambda *_: asyncio.sleep(0, result=[])
        service._trader_profile_context = lambda *_: asyncio.sleep(0, result={})
        monkeypatch.setattr(module.openai_client, "ask_gpt_json_async",
                            lambda **_: asyncio.sleep(0, result={"error": "provider_unavailable"}))
        with pytest.raises(HTTPException) as raised:
            await service.ask(77, 4, "Wat kan ik van deze trade leren?")
        assert raised.value.status_code == 503
        assert service.session.saved == []
    asyncio.run(exercise())


class _Result:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def scalar_one_or_none(self):
        return self.row

    def scalar_one(self):
        return self.row

    def fetchall(self):
        return self.row if isinstance(self.row, list) else []


class _OwnerSession:
    def __init__(self):
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((str(query), params))
        return _Result(None)


def test_foreign_owner_cannot_read_delete_or_analyze_review():
    async def exercise():
        session = _OwnerSession()
        reviews = FinnTradeReviewService(session)
        for action in (reviews.get_review(77, 4), reviews.get_screenshot(77, 4),
                       reviews.delete_screenshot(77, 4),
                       FinnTradeAnalysisService(session).analyze(77, 4)):
            with pytest.raises(HTTPException) as raised:
                await action
            assert raised.value.status_code == 404
        assert all(params == {"id": 4, "user_id": 77} for _, params in session.calls)
    asyncio.run(exercise())


def test_stale_analysis_is_not_returned_after_input_revision_change(monkeypatch):
    from backend.services import finn_trade_analysis_service as module

    async def exercise():
        now = datetime.now(timezone.utc)
        original = {
            "id": 4, "symbol": "BTC", "execution_environment": "paper",
            "entry_at": now, "exit_at": now, "entry_value_eur": Decimal(100),
            "exit_value_eur": Decimal(110), "pnl_eur_before_fees": Decimal(10),
            "fills": [{"ledger_id": 1, "side": "buy", "at": now.isoformat(),
                       "qty": "1", "cash_eur": "100", "price_eur": "100"}],
            "plan_snapshot": None, "note": "", "candles_status": "unavailable",
            "candles_reason": "missing", "has_screenshot": False,
            "analysis_status": "pending", "analysis_updated_at": None,
            "analysis_json": None, "analysis_reason": None, "input_revision": 0,
        }

        class Session:
            def __init__(self):
                self.queries = []

            async def execute(self, query, params=None):
                sql = str(query)
                self.queries.append(sql)
                if "pg_advisory_xact_lock" in sql or "INSERT INTO finn_trade_ai_call_attempts" in sql:
                    return _Result()
                if "SELECT input_revision" in sql:
                    return _Result(0)
                if "FROM finn_trade_ai_call_attempts" in sql:
                    return _Result(0)
                if "RETURNING analysis_updated_at" in sql:
                    return _Result((now,))
                if "UPDATE finn_trade_reviews SET analysis_status=:status" in sql:
                    assert params["input_revision"] == 0
                    return _Result(rowcount=0)
                raise AssertionError(sql)

            async def commit(self):
                pass

        session = Session()
        service = FinnTradeAnalysisService(session)
        calls = 0

        async def get_review(user_id, review_id):
            nonlocal calls
            calls += 1
            return original if calls == 1 else {**original, "input_revision": 1}

        async def fake_ai(**kwargs):
            context = get_ai_usage_context()
            assert context["user_id"] == 77
            assert context["entry_point"] == "finn_trade_review"
            return _analysis("De trade is gesloten.")

        service.reviews.get_review = get_review
        service._prior_confirmed_lessons = lambda *_: asyncio.sleep(0, result=[])
        service._trader_profile_context = lambda *_: asyncio.sleep(0, result={})
        monkeypatch.setattr(module.openai_client, "ask_gpt_json_async", fake_ai)
        result = await service.analyze(77, 4)
        assert result["status"] == "pending"
        assert result["analysis"] is None
        assert next(i for i, sql in enumerate(session.queries) if "pg_advisory_xact_lock" in sql) < next(
            i for i, sql in enumerate(session.queries) if "UPDATE finn_trade_reviews SET analysis_status='running'" in sql
        )
    asyncio.run(exercise())


def test_provider_failure_is_persisted_without_fake_trade_analysis(monkeypatch):
    from backend.services import finn_trade_analysis_service as module

    async def exercise():
        now = datetime.now(timezone.utc)
        review = {
            "id": 4, "symbol": "BTC", "execution_environment": "paper",
            "entry_at": now, "exit_at": now, "entry_value_eur": Decimal(100),
            "exit_value_eur": Decimal(99), "pnl_eur_before_fees": Decimal(-1),
            "fills": [{"ledger_id": 1, "side": "buy", "at": now.isoformat(),
                       "qty": "1", "cash_eur": "100", "price_eur": "100"}],
            "plan_snapshot": None, "note": "", "candles_status": "unavailable",
            "candles_reason": "missing", "has_screenshot": False,
            "analysis_status": "pending", "analysis_updated_at": None,
            "analysis_json": None, "analysis_reason": None, "input_revision": 0,
        }

        class Session:
            def __init__(self): self.saved = None
            async def execute(self, query, params=None):
                sql = str(query)
                if "pg_advisory_xact_lock" in sql or "INSERT INTO finn_trade_ai_call_attempts" in sql:
                    return _Result()
                if "FROM finn_trade_ai_call_attempts" in sql:
                    return _Result(0)
                if "SELECT input_revision" in sql:
                    return _Result(0)
                if "RETURNING analysis_updated_at" in sql:
                    return _Result((now,))
                if "UPDATE finn_trade_reviews SET analysis_status=:status" in sql:
                    self.saved = params
                    return _Result(rowcount=1)
                raise AssertionError(sql)
            async def commit(self): pass

        session = Session()
        service = FinnTradeAnalysisService(session)
        service.reviews.get_review = lambda *_: asyncio.sleep(0, result=review)
        service._prior_confirmed_lessons = lambda *_: asyncio.sleep(0, result=[])
        service._trader_profile_context = lambda *_: asyncio.sleep(0, result={})
        monkeypatch.setattr(module.openai_client, "ask_gpt_json_async",
                            lambda **_: asyncio.sleep(0, result={"error": "provider_unavailable"}))
        result = await service.analyze(77, 4)
        assert result["status"] == "unavailable"
        assert result["analysis"] is None
        assert session.saved["status"] == "unavailable"
        assert session.saved["analysis"] is None
        assert session.saved["model"] is None
        assert session.saved["user_id"] == 77
    asyncio.run(exercise())


def test_question_does_not_persist_after_screenshot_revision_change(monkeypatch):
    from backend.services import finn_trade_analysis_service as module

    async def exercise():
        now = datetime.now(timezone.utc)
        review = {
            "id": 4, "symbol": "BTC", "execution_environment": "paper",
            "entry_at": now, "exit_at": now, "entry_value_eur": Decimal(100),
            "exit_value_eur": Decimal(110), "pnl_eur_before_fees": Decimal(10),
            "fills": [{"ledger_id": 1, "side": "buy", "at": now.isoformat(),
                       "qty": "1", "cash_eur": "100", "price_eur": "100"}],
            "plan_snapshot": None, "note": "", "candles_status": "unavailable",
            "candles_reason": "missing", "has_screenshot": False,
            "input_revision": 0,
        }

        class Session:
            async def execute(self, query, params=None):
                if "pg_advisory_xact_lock" in str(query) or "INSERT INTO finn_trade_ai_call_attempts" in str(query):
                    return _Result()
                if "SELECT input_revision" in str(query):
                    return _Result(0 if not hasattr(self, "reserved") else 1)
                if "FROM finn_trade_ai_call_attempts" in str(query):
                    self.reserved = True
                    return _Result(0)
                raise AssertionError(str(query))

            async def rollback(self):
                pass

            async def commit(self):
                pass

        service = FinnTradeAnalysisService(Session())

        async def get_review(user_id, review_id):
            return review

        async def fake_ai(**kwargs):
            assert get_ai_usage_context()["user_id"] == 77
            return _analysis("De trade is gesloten.")

        service.reviews.get_review = get_review
        service._prior_confirmed_lessons = lambda *_: asyncio.sleep(0, result=[])
        service._trader_profile_context = lambda *_: asyncio.sleep(0, result={})
        monkeypatch.setattr(module.openai_client, "ask_gpt_json_async", fake_ai)
        with pytest.raises(HTTPException) as raised:
            await service.ask(77, 4, "Wat gebeurde er bij de exit?")
        assert raised.value.status_code == 409
    asyncio.run(exercise())


def test_chart_has_explicit_fallback_without_supported_eur_market():
    now = datetime.now(timezone.utc)
    chart, reason = asyncio.run(historical_eur_chart({
        "symbol": "UNKNOWN", "entry_at": now, "exit_at": now,
        "fills": [],
    }))
    assert chart is None
    assert "EUR" in reason


def test_analysis_waits_for_parallel_chart_load_without_model_call(monkeypatch):
    from backend.services import finn_trade_analysis_service as module

    async def exercise():
        class Session:
            async def execute(self, query, params=None):
                raise AssertionError("No AI claim or budget reservation while chart is loading")

        service = FinnTradeAnalysisService(Session())

        async def get_review(user_id, review_id):
            return {"candles_status": "loading"}

        async def get_chart(user_id, review_id):
            return {"status": "loading", "chart": None, "reason": None}

        async def fake_ai(**kwargs):
            raise AssertionError("Model called before historical chart resolved")

        service.reviews.get_review = get_review
        service.reviews.get_chart = get_chart
        monkeypatch.setattr(module.openai_client, "ask_gpt_json_async", fake_ai)
        assert (await service.analyze(77, 4))["status"] == "pending"
    asyncio.run(exercise())
