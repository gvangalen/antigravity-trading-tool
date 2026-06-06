from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_public_report_logging_uses_token_fingerprint_and_generic_denials():
    source = _read(BACKEND_ROOT / "api" / "report_public_api.py")

    assert "def _token_fingerprint" in source
    assert 'token_fingerprint=%s' in source
    assert "token[:12]" not in source
    assert 'detail="Access denied"' in source
    assert 'detail=str(e)' not in source


def test_sidebar_routes_require_authenticated_user_and_hide_internal_errors():
    source = _read(BACKEND_ROOT / "api" / "sidebar_api.py")

    assert "from backend.utils.auth_utils import get_current_user" in source
    assert 'current_user: dict = Depends(get_current_user)' in source
    assert 'detail="Actieve trades konden niet worden opgehaald."' in source
    assert 'detail="Botstatus kon niet worden opgehaald."' in source
    assert "detail=str(e)" not in source


def test_supporting_api_routes_no_longer_echo_raw_internal_exceptions():
    files = {
        "market_data_api.py": [
            "Fout bij ophalen market-indicatornamen.",
            "Fout bij ophalen market-indicatorregels.",
        ],
        "macro_data_api.py": [
            "Fout bij ophalen macro-indicatornamen.",
            "Fout bij ophalen macro-indicatorregels.",
        ],
        "bot_api.py": [
            "Preview van order mislukt.",
        ],
        "onboarding_api.py": [
            "Ongeldige onboarding stap.",
        ],
        "indicator_config_api.py": [
            "Ongeldige indicator-configuratie.",
            "Ongeldige indicator-instellingen.",
            "Ongeldige indicatorregels.",
            "Ongeldige reset-aanvraag.",
        ],
    }

    for filename, messages in files.items():
        source = _read(BACKEND_ROOT / "api" / filename)
        assert "detail=str(e)" not in source
        for message in messages:
            assert message in source
