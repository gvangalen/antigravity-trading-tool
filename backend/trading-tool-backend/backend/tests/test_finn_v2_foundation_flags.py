from backend.services.finn_v2_flag_service import FinnV2FlagService


def test_finn_v2_flags_default_to_v2_only_runtime(monkeypatch):
    for name in (
        "FINN_V2_ENABLED",
        "FINN_V2_SHADOW_ENABLED",
        "FINN_V2_VISIBLE_ENABLED",
        "FINN_V2_WRITE_BLOCKED",
        "FINN_V2_CANARY_USER_IDS",
        "FINN_V2_ALLOWED_TRANSPORTS",
        "FINN_V2_MAX_EXECUTES_PER_MINUTE",
    ):
        monkeypatch.delenv(name, raising=False)

    service = FinnV2FlagService()

    assert service.is_enabled_globally() is True
    assert service.is_shadow_enabled() is False
    assert service.is_write_blocked() is True
    assert service.resolve_mode(7) == "visible_runtime"


def test_finn_v2_runtime_requires_safe_v2_config(monkeypatch):
    monkeypatch.setenv("FINN_V2_ENABLED", "true")
    monkeypatch.setenv("FINN_V2_WRITE_BLOCKED", "true")
    monkeypatch.setenv("FINN_V2_MAX_EXECUTES_PER_MINUTE", "0")
    monkeypatch.setenv("FINN_V2_ALLOWED_TRANSPORTS", "chat,stream")

    service = FinnV2FlagService()

    assert service.resolve_mode(11) == "visible_runtime"
    assert service.allows_transport("chat") is True
    assert service.allows_transport("stream") is True


def test_finn_v2_visible_mode_is_global_for_authenticated_runtime(monkeypatch):
    monkeypatch.setenv("FINN_V2_ENABLED", "true")
    monkeypatch.setenv("FINN_V2_VISIBLE_ENABLED", "true")
    monkeypatch.setenv("FINN_V2_WRITE_BLOCKED", "true")
    monkeypatch.setenv("FINN_V2_MAX_EXECUTES_PER_MINUTE", "0")
    monkeypatch.setenv("FINN_V2_CANARY_USER_IDS", "5, 8,13")

    service = FinnV2FlagService()

    assert service.is_canary_user(8) is True
    assert service.is_canary_user(9) is False
    assert service.is_visible_for_user(8) is True
    assert service.is_visible_for_user(9) is True
    assert service.resolve_mode(8) == "visible_runtime"
    assert service.resolve_mode(9) == "visible_runtime"


def test_unsafe_v2_config_is_disabled_without_affecting_startup(monkeypatch):
    monkeypatch.setenv("FINN_V2_ENABLED", "true")
    monkeypatch.setenv("FINN_V2_SHADOW_ENABLED", "true")
    monkeypatch.setenv("FINN_V2_WRITE_BLOCKED", "false")
    monkeypatch.setenv("FINN_V2_MAX_EXECUTES_PER_MINUTE", "2")

    service = FinnV2FlagService()

    assert service.resolve_mode(7) == "disabled"
