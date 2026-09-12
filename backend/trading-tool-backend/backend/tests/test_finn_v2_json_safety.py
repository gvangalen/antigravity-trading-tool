from backend.services.finn_v2_json_safety import to_json_safe


def test_json_safety_removes_postgres_incompatible_nul_from_nested_provider_payload():
    payload = {"content": "first\x00second", "nested": ["safe", {"detail": "x\x00y"}]}

    assert to_json_safe(payload) == {
        "content": "firstsecond",
        "nested": ["safe", {"detail": "xy"}],
    }
