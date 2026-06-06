import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def test_frontend_security_dependency_tranche_removes_legacy_pwa_stack():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    next_config = (FRONTEND_ROOT / "next.config.js").read_text(encoding="utf-8")

    deps = package_json.get("dependencies", {})

    assert deps.get("next") != "13.4.12"
    assert "next-pwa" not in deps
    assert "next-transpile-modules" not in deps
    assert "const withPWA = require('next-pwa')" not in next_config
    assert "module.exports = nextConfig;" in next_config
    assert "appDir: true" not in next_config
