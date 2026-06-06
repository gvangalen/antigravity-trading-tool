import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def test_frontend_security_dependency_tranche_removes_legacy_pwa_stack():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    next_config = (FRONTEND_ROOT / "next.config.js").read_text(encoding="utf-8")

    deps = package_json.get("dependencies", {})
    overrides = package_json.get("overrides", {})

    assert deps.get("next") != "13.4.12"
    assert deps.get("next", "").startswith("^15.5.")
    assert deps.get("postcss", "").startswith("^8.5.")
    assert "next-pwa" not in deps
    assert "next-transpile-modules" not in deps
    assert overrides.get("postcss", "").startswith("^8.5.")
    assert "const withPWA = require('next-pwa')" not in next_config
    assert "module.exports = nextConfig;" in next_config
    assert "appDir: true" not in next_config
