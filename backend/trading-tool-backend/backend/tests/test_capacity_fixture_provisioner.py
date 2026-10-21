import json
import os
import stat
import asyncio
import runpy
from datetime import timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.scripts import provision_capacity_fixtures as fixtures
from backend.main import app
from backend.utils.auth_utils import CAPACITY_FIXTURE_ROUTES, create_token, decode_token, get_current_user


def test_fixture_collision_is_rejected_before_mutation():
    row = {
        "email": fixtures.fixture_email("capacity-check", 1),
        "role": "user",
        "first_name": "Capacity",
        "last_name": "Fixture",
        "ai_preferences": {"capacity_fixture": {
            "campaign": "another-run", "index": 1, "kind": fixtures.FIXTURE_KIND,
        }},
    }
    with pytest.raises(RuntimeError, match="collision"):
        fixtures.validate_fixture(row, "capacity-check", 1)


def test_token_file_is_private_outside_repo_and_cannot_be_replaced(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    output = directory / "fixtures.json"
    path = fixtures.private_output_path(output)
    fixtures.write_private_json(path, [{"user_id": 7, "access_token": "test-token"}])
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == [{"user_id": 7, "access_token": "test-token"}]
    with pytest.raises(ValueError, match="already exists"):
        fixtures.private_output_path(output)
    with pytest.raises(FileExistsError):
        fixtures.write_private_json(path, [{"user_id": 8, "access_token": "replacement"}])
    assert json.loads(output.read_text())[0]["user_id"] == 7


def test_token_file_rejects_world_readable_directory_and_repo_path(tmp_path):
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    os.chmod(public, 0o755)
    with pytest.raises(ValueError, match="mode 0700"):
        fixtures.private_output_path(public / "fixtures.json")
    with pytest.raises(ValueError, match="outside the repository"):
        fixtures.private_output_path(fixtures.REPO_ROOT / "fixtures.json")


def test_fixture_token_is_limited_to_load_get_routes():
    token = create_token({"sub": "42", "role": "user", "capacity_fixture": {
        "kind": fixtures.FIXTURE_KIND, "campaign": "capacity-check",
    }}, timedelta(minutes=20), "access")
    with pytest.raises(ValueError, match="not valid for this operation"):
        decode_token(token)

    def authenticate(method, path):
        request = Request({"type": "http", "method": method, "path": path,
                           "query_string": b"", "headers": []})
        return asyncio.run(get_current_user(request, access_token=None,
                                             authorization=f"Bearer {token}"))

    assert CAPACITY_FIXTURE_ROUTES == {
        "/api/auth/me", "/api/workspace/asset", "/api/assistant/v2/conversations", "/api/bot/trade-reviews",
    }
    for path in CAPACITY_FIXTURE_ROUTES:
        assert authenticate("GET", path) == {"id": 42, "role": "user"}
        with pytest.raises(HTTPException) as blocked:
            authenticate("POST", path)
        assert blocked.value.status_code == 403
    for path in ("/api/bot/orders", "/api/auth/refresh", "/api/bot/trade-reviews/7"):
        with pytest.raises(HTTPException) as blocked:
            authenticate("GET", path)
        assert blocked.value.status_code == 403


def test_capacity_load_routes_exist_and_match_token_scope():
    routes = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))["ROUTES"]

    configured = {path.split("?", 1)[0] for _, method, path, _ in routes if method == "GET"}
    available = {route.path for route in app.routes if "GET" in getattr(route, "methods", ())}
    assert configured | {"/api/auth/me"} == CAPACITY_FIXTURE_ROUTES
    assert configured <= available


def test_owner_canary_seed_binds_rows_to_two_exact_marked_users(monkeypatch):
    from contextlib import nullcontext
    from backend.scripts import probe_capacity_owner_canary as canary

    class Result:
        def mappings(self):
            return self

        def one(self):
            return {"watchlists": 0, "conversations": 0, "runs": 0}

    class Connection:
        def __init__(self):
            self.writes = []

        def execute(self, statement, params):
            sql = str(statement)
            if "SELECT" in sql:
                return Result()
            self.writes.append((sql, dict(params)))
            return Result()

    connection = Connection()
    monkeypatch.setattr(canary, "sync_engine", type("Engine", (), {"begin": lambda _self: nullcontext(connection)})())
    monkeypatch.setattr(canary, "checked_rows", lambda *_args, **_kwargs: {
        fixtures.fixture_email("owner-check", 1): {"id": 101, "is_active": True},
        fixtures.fixture_email("owner-check", 2): {"id": 202, "is_active": True},
    })
    result = canary.seed("owner-check")
    assert result["seeded_users"] == 2
    assert len(connection.writes) == 6
    assert [params["user_id"] for _, params in connection.writes] == [101, 101, 101, 202, 202, 202]
    assert [params["symbol"] for sql, params in connection.writes if "INSERT INTO watchlists" in sql] == ["XRP", "ADA"]


def test_owner_canary_public_probe_rejects_cross_account_content(monkeypatch):
    monkeypatch.syspath_prepend(str(fixtures.REPO_ROOT / "ops/load"))
    probe = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/owner_canary.py"))
    valid_workspace = {"watchlist": {"rows": [{"symbol": "XRP"}]}}
    own = [{"id": "capacity-owner-owner-check-1",
            "title": "Capacity owner canary owner-check account 1"}]
    probe["assert_owner_content"](1, "owner-check", valid_workspace, own)
    with pytest.raises(RuntimeError, match="workspace watchlist isolation"):
        probe["assert_owner_content"](1, "owner-check", {"watchlist": {"rows": [{"symbol": "ADA"}]}}, own)
    with pytest.raises(RuntimeError, match="FINN conversation isolation"):
        probe["assert_owner_content"](1, "owner-check", valid_workspace, own + [
            {"id": "capacity-owner-owner-check-2", "title": "another owner's title"},
        ])


def test_owner_canary_cleanup_refuses_changed_run_before_delete(monkeypatch):
    from contextlib import nullcontext
    from backend.scripts import probe_capacity_owner_canary as canary

    class Result:
        def __init__(self, row=None, count=None):
            self.row = row
            self.count = count

        def mappings(self):
            return self

        def one_or_none(self):
            return self.row

        def scalar_one(self):
            return self.count

    class Connection:
        def execute(self, statement, params):
            sql = str(statement)
            if sql.lstrip().startswith("DELETE"):
                pytest.fail("Cleanup must not delete any row after a changed run")
            if "FROM finn_v2_runs" in sql and "FOR UPDATE" in sql:
                return Result({"user_id": params["user_id"],
                               "conversation_id": params["conversation_id"],
                               "message": params["message"], "status": "running"})
            if "FROM finn_v2_conversations" in sql:
                return Result(None)
            if "COUNT(*) FROM finn_v2_runs" in sql:
                return Result(count=1)
            if "FROM watchlists" in sql:
                return Result(None)
            raise AssertionError(sql)

    connection = Connection()
    monkeypatch.setattr(canary, "sync_engine", type("Engine", (), {"begin": lambda _self: nullcontext(connection)})())
    monkeypatch.setattr(canary, "checked_rows", lambda *_args, **_kwargs: {
        fixtures.fixture_email("owner-check", 1): {"id": 101},
        fixtures.fixture_email("owner-check", 2): {"id": 202},
    })
    with pytest.raises(RuntimeError, match="Canary run changed"):
        canary.cleanup("owner-check")


def test_owner_canary_run_dependency_blocks_cleanup(monkeypatch):
    from backend.scripts import probe_capacity_owner_canary as canary

    class Result:
        def __init__(self, rows=None, count=None):
            self.rows = rows
            self.count = count

        def mappings(self):
            return self

        def all(self):
            return self.rows

        def scalar_one(self):
            return self.count

    class Connection:
        dialect = type("Dialect", (), {"identifier_preparer": type("Preparer", (), {"quote": staticmethod(lambda name: f'"{name}"')})()})()

        def execute(self, statement, params=None):
            sql = str(statement)
            if "pg_constraint" in sql:
                return Result(rows=[{"schema_name": "public", "table_name": "finn_v2_run_traces", "columns": ["run_id"]}])
            if '"finn_v2_run_traces"' in sql:
                return Result(count=1)
            raise AssertionError(sql)

    with pytest.raises(RuntimeError, match="dependent rows"):
        canary.assert_no_run_dependents(Connection(), "capacity-owner-run-owner-check-1")


@pytest.mark.parametrize("module_name,action", [
    ("probe_capacity_owner_canary", "seed"),
    ("probe_capacity_owner_canary", "cleanup"),
    ("provision_capacity_fixtures", "create"),
    ("provision_capacity_fixtures", "issue"),
    ("provision_capacity_fixtures", "deactivate"),
])
def test_capacity_mutations_require_explicit_production_flag(monkeypatch, capsys, module_name, action):
    import importlib
    import sys

    module = importlib.import_module(f"backend.scripts.{module_name}")
    args = [module_name, action, "--campaign", "owner-check",
        "--expected-db-host", module.db_host,
        "--expected-db-port", module.db_port,
        "--expected-db-name", module.db_name,
        "--apply"]
    if module_name == "provision_capacity_fixtures":
        args.extend(["--count", "2"])
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exit_info:
        module.main()
    assert exit_info.value.code == 2
    assert "--allow-production" in capsys.readouterr().err


def test_capacity_fixture_email_is_accepted_by_auth_response_schema():
    from pydantic import EmailStr, parse_obj_as

    email = fixtures.fixture_email("capacity-check", 1)
    assert parse_obj_as(EmailStr, email) == email


def test_enabled_review_diagnostic_requires_real_enabled_empty_body():
    from types import SimpleNamespace
    from backend.scripts.probe_capacity_enabled_reviews import enabled_empty_review

    enabled = {"items": [], "total": 0, "weekly": {"status": "complete", "week_start": "2026-10-12"}}
    assert enabled_empty_review(SimpleNamespace(status_code=200, json=lambda: enabled))
    assert not enabled_empty_review(SimpleNamespace(status_code=200, json=lambda: {
        **enabled, "status": "disabled",
    }))
    assert not enabled_empty_review(SimpleNamespace(status_code=200, json=lambda: {"items": [], "total": 0}))
    assert not enabled_empty_review(SimpleNamespace(status_code=503, json=lambda: enabled))


def test_enabled_review_process_override_is_restored(monkeypatch):
    from backend.scripts.probe_capacity_enabled_reviews import process_local_review_rollout

    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "allowlist")
    monkeypatch.setenv("FINN_TRADE_REVIEW_USER_IDS", "7")
    with process_local_review_rollout():
        assert os.environ["FINN_TRADE_REVIEW_ROLLOUT"] == "all"
        assert "FINN_TRADE_REVIEW_USER_IDS" not in os.environ
    assert os.environ["FINN_TRADE_REVIEW_ROLLOUT"] == "allowlist"
    assert os.environ["FINN_TRADE_REVIEW_USER_IDS"] == "7"


def test_enabled_review_interim_latency_abort_stays_latched():
    import time
    from backend.scripts.probe_capacity_enabled_reviews import monitor_stage, percentile

    samples = [(200, 2000.0, True)] * 20
    stop = asyncio.Event()
    aborted = []
    asyncio.run(monitor_stage(samples, 1000, time.monotonic() + 0.01, stop, aborted))
    assert stop.is_set() and aborted == ["interim_steady_p95_breach"]
    samples.extend([(200, 10.0, True)] * 500)
    assert percentile([sample[1] for sample in samples], 0.95) == 10.0
    assert aborted == ["interim_steady_p95_breach"]


def test_enabled_review_identity_preflight_times_out_hanging_inprocess_request():
    from backend.scripts.probe_capacity_enabled_reviews import identity_preflight

    class HangingClient:
        async def get(self, *_args, **_kwargs):
            await asyncio.Event().wait()

    started = __import__("time").monotonic()
    with pytest.raises(RuntimeError, match="Identity preflight failed"):
        asyncio.run(identity_preflight(HangingClient(), [{
            "user_id": 1, "email": "capacity+review-check-0001@load.example",
            "access_token": "test-token",
        }], timeout=0.02))
    assert __import__("time").monotonic() - started < 1


def test_enabled_review_resource_stop_gates_are_concrete():
    from copy import deepcopy
    from backend.scripts.probe_capacity_enabled_reviews import resource_stop_reason

    baseline = {"db_free": 50, "lock_waiters": 0, "long_idle_transactions": 0,
                "mem_available_mib": 4096, "queues": {
                    "execution_critical": {"depth": 0, "oldest_age_seconds": None},
                    "finn_interactive": {"depth": 0, "oldest_age_seconds": None},
                }}
    assert resource_stop_reason(baseline, baseline, minimum_db_free=43) is None
    for change, reason in [
        ({"db_free": 19}, "database_headroom"),
        ({"lock_waiters": 1}, "database_lock_or_long_transaction"),
        ({"long_idle_transactions": 1}, "database_lock_or_long_transaction"),
        ({"mem_available_mib": 1000}, "host_memory"),
    ]:
        snapshot = {**baseline, **change}
        assert resource_stop_reason(snapshot, baseline) == reason
    queued = deepcopy(baseline)
    queued["queues"]["execution_critical"] = {"depth": 6, "oldest_age_seconds": 5}
    assert resource_stop_reason(queued, baseline) == "critical_queue_depth"
    aging = deepcopy(baseline)
    aging["queues"]["finn_interactive"] = {"depth": 1, "oldest_age_seconds": 31}
    assert resource_stop_reason(aging, baseline) == "queue_age_growth"
    unknown = deepcopy(baseline)
    unknown["queues"]["execution_critical"] = {"depth": 1, "oldest_age_seconds": None}
    assert resource_stop_reason(unknown, baseline) == "queue_age_unavailable"


def test_capacity_load_origin_rejects_unapproved_token_destinations():
    validate = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))["validate_base_url"]
    assert validate("http://127.0.0.1:8000", allow_production=False) == "http://127.0.0.1:8000"
    assert validate("https://tradamind.com/", allow_production=True) == "https://tradamind.com"
    for url in ("http://tradamind.com", "https://api.tradamind.com",
                "https://tradamimd.com", "https://tradamind.com.evil.test",
                "https://tradamind.com@evil.test", "https://tradamind.com/path"):
        with pytest.raises(ValueError):
            validate(url, allow_production=True)
    with pytest.raises(ValueError):
        validate("https://tradamind.com", allow_production=False)


def test_capacity_load_identity_and_error_gate():
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    identity_matches = harness["identity_matches"]
    fixture = {"user_id": 42, "email": "capacity+test-0042@load.example"}
    response = SimpleNamespace(status_code=200, json=lambda: {"id": 42, "email": fixture["email"]})
    assert identity_matches(response, fixture)
    assert not identity_matches(SimpleNamespace(status_code=200, json=lambda: {
        "id": 43, "email": fixture["email"],
    }), fixture)
    assert not identity_matches(SimpleNamespace(status_code=200, json=lambda: {
        "id": 42, "email": "another-user@example.test",
    }), fixture)
    summary = harness["report"]("test", {"workspace": [(200, 100), (503, 250)]})
    assert summary["workspace"]["p95_ms"] == 100
    assert summary["workspace"]["p95_all_ms"] == 250
    assert harness["stage_has_blocking_errors"](summary)
    assert harness["stage_exceeds_latency_limit"](summary, {"workspace": 200}) == ["workspace"]
    assert harness["stage_exceeds_latency_limit"](summary, {"workspace": 300}) == []
    assert harness["stage_exceeds_latency_limit"]({}, {"workspace": 200}) == ["workspace"]


def test_capacity_load_reports_backend_timing_and_slow_trace():
    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    summary = harness["report"]("diagnostic", {
        "workspace": [(200, 1200, 800, "trace-one", 123.1, 124.3), (200, 100, 40, "trace-two", 125.1, 125.2)],
    })["workspace"]
    assert summary["backend_p95_ms"] == 800
    assert summary["backend_timing_samples"] == 2
    assert summary["slow_traces"][0] == {
        "trace_id": "trace-one", "client_ms": 1200, "backend_ms": 800,
        "start_utc_epoch": 123.1, "end_utc_epoch": 124.3,
    }


def test_capacity_load_keeps_bearer_header_across_requests():
    import time
    from collections import defaultdict
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    stop = asyncio.Event()

    class Client:
        def __init__(self):
            self.request_headers = []

        async def request(self, _method, _path, *, headers, json):
            self.request_headers.append(dict(headers))
            if len(self.request_headers) == 2:
                stop.set()
            return SimpleNamespace(status_code=200, headers={
                "server-timing": "app;dur=5.0", "x-trace-id": "trace-from-server",
            })

    client = Client()
    results = defaultdict(list)
    asyncio.run(harness["virtual_user"](
        client, {"user_id": 42, "access_token": "fixture-token"},
        time.monotonic() + 1, 0.01, None, results, stop,
    ))

    assert all(item["Authorization"] == "Bearer fixture-token" for item in client.request_headers)
    assert len({item["X-Trace-Id"] for item in client.request_headers}) == 2
    assert all(item["X-Trace-Id"].startswith("cap-") for item in client.request_headers)
    assert sum(map(len, results.values())) == 2
    assert all(sample[2:4] == (5.0, "trace-from-server") for route in results.values() for sample in route)
    assert all(sample[4] <= sample[5] for route in results.values() for sample in route)


def test_chat_load_requires_a_verified_terminal_outcome_even_after_http_200():
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    classify = harness["chat_response_state"]
    response = lambda body: SimpleNamespace(status_code=200, json=lambda: body)
    assert classify(response({
        "intent": "unavailable", "state": {"current_flow": "finn_v2_visible_failed", "run_id": "r1"},
        "response_trace": {"error": "provider_error"},
    }))[0] == "unavailable"
    assert classify(response({
        "intent": "processing", "state": {"current_flow": "finn_v2_visible_pending", "run_id": "r1"},
        "response_trace": {"run_id": "r1"},
    })) == ("pending", "r1")
    assert classify(response({
        "intent": "fact", "response": "Verified answer",
        "state": {"current_flow": "finn_v2_visible", "run_id": "r1"},
        "response_trace": {
            "run_id": "r1", "pipeline_version": "finn_v2",
            "response_source": "finn_v2_verified", "verifier_status": "passed",
            "delivery_envelope": {"status": "completed"},
        },
    })) == ("ok", "r1")
    assert classify(response({
        "intent": "fact", "response": "Unverified answer",
        "state": {"current_flow": "finn_v2_visible", "run_id": "r1"},
        "response_trace": {
            "run_id": "r2", "pipeline_version": "finn_v2",
            "response_source": "finn_v2_verified", "verifier_status": "passed",
            "delivery_envelope": {"status": "completed"},
        },
    }))[0] == "malformed"

    class Client:
        def __init__(self, terminal):
            self.terminal = terminal

        async def get(self, path, *, headers):
            assert path == "/api/assistant/v2/runs/r1"
            assert headers == {"Authorization": "Bearer private-token"}
            return response(self.terminal)

    pending = response({
        "intent": "processing", "state": {"current_flow": "finn_v2_visible_pending", "run_id": "r1"},
        "response_trace": {"run_id": "r1"},
    })
    completed = {"run_id": "r1", "status": "completed", "response": {
        "content": "Verified answer", "mode": "FACT", "verifier_status": "passed",
    }}
    assert asyncio.run(harness["chat_turn_outcome"](
        Client(completed), pending, "Bearer private-token", 0.01, asyncio.Event(),
    )) == "ok"
    assert asyncio.run(harness["chat_turn_outcome"](
        Client({"run_id": "r1", "status": "failed"}), pending,
        "Bearer private-token", 0.01, asyncio.Event(),
    )) == "terminal_unsuccessful"
    summary = harness["report"]("semantic", {
        "finn_chat": [(200, 10, None, "trace", 1, 2, "unavailable")],
    })
    assert summary["finn_chat"]["statuses"] == {"200": 1}
    assert summary["finn_chat"]["outcomes"] == {"unavailable": 1}
    assert harness["stage_has_blocking_errors"](summary)
    assert harness["chat_stage_quotas"](65, 3, production=True) == [20, 20, 25]
    with pytest.raises(ValueError, match="at least 20 requests per stage"):
        harness["chat_stage_quotas"](50, 3, production=True)


def test_chat_quota_is_reserved_for_steady_phase_after_ramp(monkeypatch):
    import time
    from collections import defaultdict
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))

    class ChooseChat:
        def choices(self, items, *, weights):
            return [items[-1]]

        def uniform(self, _minimum, _maximum):
            return 0.001

    monkeypatch.setattr(harness["virtual_user"].__globals__["random"], "Random", lambda _seed: ChooseChat())

    class Client:
        async def request(self, _method, path, *, headers, json):
            if path != "/api/assistant/chat":
                return SimpleNamespace(status_code=200, headers={})
            return SimpleNamespace(status_code=200, headers={}, json=lambda: {
                "intent": "fact", "response": "Verified answer",
                "state": {"current_flow": "finn_v2_visible", "run_id": "r1"},
                "response_trace": {
                    "run_id": "r1", "pipeline_version": "finn_v2",
                    "response_source": "finn_v2_verified", "verifier_status": "passed",
                    "delivery_envelope": {"status": "completed"},
                },
            })

    async def exercise():
        now = time.monotonic()
        all_results = defaultdict(list)
        steady_results = defaultdict(list)
        budget = {"remaining": 3}
        await harness["virtual_user"](
            Client(), {"user_id": 42, "access_token": "fixture"},
            now + 0.09, 0.001, budget, all_results, asyncio.Event(),
            steady_results=steady_results, steady_started=now + 0.03,
        )
        return all_results, steady_results, budget

    all_results, steady_results, budget = asyncio.run(exercise())
    assert len(all_results["workspace"]) > 0
    assert len(steady_results["finn_chat"]) == 3
    assert budget["remaining"] == 0


def test_capacity_generator_requires_fd_headroom_for_production(monkeypatch):
    import resource

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    monkeypatch.setattr(resource, "getrlimit", lambda _kind: (1024, 1048576))
    with pytest.raises(ValueError, match="at least 1128 open file descriptors"):
        harness["generator_fd_limits"](1000, production=True)
    assert harness["generator_fd_limits"](1000, production=False)["soft"] == 1024
    monkeypatch.setattr(resource, "getrlimit", lambda _kind: (4096, 1048576))
    assert harness["generator_fd_limits"](1000, production=True)["soft"] == 4096


def test_capacity_generator_diagnostics_summarize_local_pressure():
    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    summary = harness["generator_report"]([
        {"event_loop_lag_ms": 2, "process_cpu_pct": 10, "open_fds": 200},
        {"event_loop_lag_ms": 80, "process_cpu_pct": 120, "open_fds": 900},
    ])
    assert summary == {
        "samples": 2, "event_loop_lag_p95_ms": 80, "event_loop_lag_max_ms": 80,
        "process_cpu_p95_pct": 120, "open_fds_max": 900,
    }


def test_capacity_load_operator_gate_requires_explicit_continue(monkeypatch):
    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(RuntimeError, match="declined"):
        harness["require_operator_continue"]("500:120")
    monkeypatch.setattr("builtins.input", lambda prompt: "CONTINUE")
    harness["require_operator_continue"]("500:120")


def test_capacity_load_stops_active_stage_on_error_or_latency():
    import asyncio
    import time
    from collections import defaultdict
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))

    class FailingClient:
        async def request(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=503)

    async def check():
        stop = asyncio.Event()
        results = defaultdict(list)
        steady_results = defaultdict(list)
        await asyncio.wait_for(harness["virtual_user"](
            FailingClient(), {"user_id": 42, "access_token": "fixture"},
            time.monotonic() + 30, 10, None, results, stop,
            steady_results=steady_results, steady_started=time.monotonic() - 1,
        ), timeout=1)
        assert stop.is_set()
        assert sum(map(len, results.values())) == 1
        assert sum(map(len, steady_results.values())) == 1

        ramp_results = defaultdict(list)
        ramp_steady_results = defaultdict(list)
        ramp_stop = asyncio.Event()
        await harness["virtual_user"](
            FailingClient(), {"user_id": 44, "access_token": "fixture"},
            time.monotonic() + 30, 10, None, ramp_results, ramp_stop,
            steady_results=ramp_steady_results, steady_started=time.monotonic() + 30,
        )
        assert sum(map(len, ramp_results.values())) == 1
        assert not ramp_steady_results

        # A stopped stage must not start a delayed virtual user request.
        delayed_results = defaultdict(list)
        await harness["virtual_user"](
            FailingClient(), {"user_id": 43, "access_token": "fixture"},
            time.monotonic() + 30, 10, None, delayed_results, stop,
            initial_spread_seconds=10,
        )
        assert not delayed_results

        stop = asyncio.Event()
        results = {"workspace": [(200, 250)] * 20}
        latency_abort_routes = []
        await asyncio.wait_for(harness["monitor_stage"](
            results, {"workspace": 200}, time.monotonic() + 30, stop, latency_abort_routes,
        ), timeout=3)
        assert stop.is_set()
        assert latency_abort_routes == ["workspace"]
        results["workspace"].extend([(200, 100)] * 980)
        assert harness["stage_exceeds_latency_limit"](
            harness["report"]("recovered-final-p95", results), {"workspace": 200},
        ) == []
        with pytest.raises(RuntimeError, match="interim p95 breach"):
            harness["reject_aborted_stage"](latency_abort_routes)

    asyncio.run(check())


def test_capacity_load_reports_steady_samples_before_error_abort(monkeypatch, capsys):
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    scope = harness["run"].__globals__

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    async def identity(_client, _fixtures):
        pass

    async def fail(_client, _fixture, _deadline, _think, _chat, results, stop,
                   initial_spread_seconds=0, steady_results=None, steady_started=None):
        results["trade_reviews"].append((500, 25))
        steady_results["trade_reviews"].append((500, 25))
        stop.set()

    monkeypatch.setitem(scope, "verify_identity", identity)
    monkeypatch.setitem(scope, "virtual_user", fail)
    monkeypatch.setattr(scope["httpx"], "AsyncClient", lambda **_: Client())
    args = SimpleNamespace(
        max_users=1, base_url="http://127.0.0.1:8000", timeout=1,
        include_chat=False, stages="1:1", think_seconds=0.01,
        p95_limits={"trade_reviews": 1000}, between_stage_pause_seconds=0,
        allow_production=False,
    )
    with pytest.raises(RuntimeError, match="non-2xx"):
        asyncio.run(harness["run"](args, [{"user_id": 7, "access_token": "fixture"}]))
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(reports) == 3
    assert "generator" in reports[0]
    assert reports[1]["routes"]["trade_reviews"]["statuses"] == {"500": 1}
    assert reports[2]["routes"]["trade_reviews"]["statuses"] == {"500": 1}


def test_capacity_load_reports_partial_routes_on_operator_cancel(monkeypatch, capsys):
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    scope = harness["run"].__globals__
    started = asyncio.Event()

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    async def identity(_client, _fixtures):
        pass

    async def pending(_client, _fixture, _deadline, _think, _chat, results, _stop,
                      initial_spread_seconds=0, steady_results=None, steady_started=None):
        results["workspace"].append((200, 25))
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setitem(scope, "verify_identity", identity)
    monkeypatch.setitem(scope, "virtual_user", pending)
    monkeypatch.setattr(scope["httpx"], "AsyncClient", lambda **_: Client())
    args = SimpleNamespace(
        max_users=1, base_url="http://127.0.0.1:8000", timeout=1,
        include_chat=False, stages="1:120", think_seconds=0.01,
        p95_limits={"workspace": 2000}, between_stage_pause_seconds=0,
        allow_production=False,
    )

    async def cancel():
        task = asyncio.create_task(harness["run"](args, [{"user_id": 7, "access_token": "fixture"}]))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert reports[0]["routes"]["workspace"]["statuses"] == {"200": 1}
    assert reports[0]["stage"].endswith("interrupted ramp + steady")
    assert reports[1]["stage"].endswith("interrupted steady interval")
    assert reports[2]["stage_aborted"]["reason"] == "operator_interrupt"


def test_capacity_load_rejects_nonfinite_production_latency_gate(monkeypatch):
    import sys

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    monkeypatch.setattr(sys, "argv", [
        "active_users.py", "--base-url", "https://tradamind.com",
        "--fixtures", "/missing-private-file", "--stages", "100:1",
        "--allow-production", "--max-workspace-p95-ms", "nan",
        "--max-finn-p95-ms", "1000", "--max-reviews-p95-ms", "1000",
    ])
    with pytest.raises(SystemExit) as rejected:
        harness["main"]()
    assert rejected.value.code == 2
