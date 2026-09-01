from backend.services import ai_availability_service
from backend.utils import embedding_client


def test_environment_switch_forces_deterministic_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    status = ai_availability_service.get_ai_availability()

    assert status["available"] is False
    assert status["reason"] == "ai_unavailable_budget"
    assert status["mode"] == "deterministic_only"
    assert status["source"] == "environment"


def test_shared_breaker_survives_local_state_reset(monkeypatch):
    store = {}

    class _Redis:
        def setex(self, key, ttl, value):
            store[key] = value

        def get(self, key):
            return store.get(key)

    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: _Redis())
    ai_availability_service.reset_ai_availability_for_tests()

    ai_availability_service.mark_ai_unavailable("ai_unavailable_budget", 600)
    ai_availability_service.reset_ai_availability_for_tests()
    status = ai_availability_service.get_ai_availability()

    assert status["available"] is False
    assert status["source"] == "redis"
    assert status["retry_after_seconds"] > 0


def test_clear_ai_unavailable_clears_shared_breaker(monkeypatch):
    store = {}

    class _Redis:
        def setex(self, key, ttl, value):
            store[key] = value

        def get(self, key):
            return store.get(key)

        def delete(self, key):
            store.pop(key, None)

    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: _Redis())
    ai_availability_service.reset_ai_availability_for_tests()

    ai_availability_service.mark_ai_unavailable("ai_unavailable_budget", 600)
    assert ai_availability_service.get_ai_availability()["available"] is False

    ai_availability_service.clear_ai_unavailable()

    status = ai_availability_service.get_ai_availability()
    assert status["available"] is True
    assert status["reason"] is None


def test_scheduled_call_slots_are_limited_per_scope(monkeypatch):
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    monkeypatch.delenv("OPENAI_MAX_CALLS_PER_SCOPE_WINDOW", raising=False)
    ai_availability_service.reset_ai_availability_for_tests()

    assert ai_availability_service.acquire_ai_call_slot("setup:7:BTC", scheduled=True) is True
    assert ai_availability_service.acquire_ai_call_slot("setup:7:BTC", scheduled=True) is False
    assert ai_availability_service.acquire_ai_call_slot("setup:7:ETH", scheduled=True) is True


def test_call_slot_honors_a_typed_boundary_override(monkeypatch):
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    ai_availability_service.reset_ai_availability_for_tests()

    assert ai_availability_service.acquire_ai_call_slot("selector:7:GLOBAL", limit_override=2) is True
    assert ai_availability_service.acquire_ai_call_slot("selector:7:GLOBAL", limit_override=2) is True
    assert ai_availability_service.acquire_ai_call_slot("selector:7:GLOBAL", limit_override=2) is False


def test_embeddings_are_disabled_in_no_budget_mode(monkeypatch):
    class _Embeddings:
        def create(self, **kwargs):
            raise AssertionError("Embedding API mag niet worden aangeroepen")

    class _Client:
        embeddings = _Embeddings()

    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "false")
    monkeypatch.setattr(embedding_client, "client", _Client())

    assert embedding_client.get_embedding("BTC") == []
    assert embedding_client.get_embeddings_batch(["BTC", "ETH"]) == []
