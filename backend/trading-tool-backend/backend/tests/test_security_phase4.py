from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_main_has_standard_security_headers_and_no_env_value_prints():
    source = _read(BACKEND_ROOT / "main.py")

    assert "async def security_headers_middleware" in source
    assert 'response.headers["X-Frame-Options"] = "DENY"' in source
    assert 'response.headers["X-Content-Type-Options"] = "nosniff"' in source
    assert 'response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"' in source
    assert 'response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"' in source
    assert 'response.headers["Content-Security-Policy"]' in source
    assert 'response.headers["Strict-Transport-Security"]' in source
    assert 'print("ENV FRONTEND_URL' not in source
    assert 'print("ENV DB_HOST' not in source


def test_auth_api_returns_generic_client_messages():
    source = _read(BACKEND_ROOT / "api" / "auth_api.py")

    assert "Registratie mislukt." in source
    assert "Ongeldige inloggegevens." in source
    assert "Ongeldige refresh token." in source
    assert "Interne authenticatiefout." in source
    assert "detail=f\"Internal Server Error: {str(e)}\"" not in source


def test_report_api_no_longer_returns_raw_internal_errors():
    source = _read(BACKEND_ROOT / "api" / "report_api.py")

    assert "def _report_value_error" in source
    assert "Rapport niet gevonden." in source
    assert "Ongeldige rapportaanvraag." in source
    assert "Rapportverwerking mislukt." in source
    assert "detail=str(e)" not in source


def test_exchange_api_hides_provider_error_details():
    source = _read(BACKEND_ROOT / "api" / "exchange_api.py")

    assert 'detail="Exchange-verbinding mislukt."' in source
    assert 'detail=f"❌ Verbinding mislukt: {str(e)}"' not in source
