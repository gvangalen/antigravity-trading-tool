"""Protect the token and arbitrary response content from QA artifacts."""

import sys
from types import SimpleNamespace

import pytest

from backend.scripts.qa_protected_readback import read_json


@pytest.mark.parametrize("path", ["/asset", "//evil.example/api/x", "https://evil.example/api/x"])
def test_readback_rejects_out_of_scope_paths_before_request(path):
    with pytest.raises(RuntimeError, match="^qa_readback_scope_invalid$"):
        read_json(owner_id=7, path=path)


def test_readback_sanitizes_transport_and_response_failures(monkeypatch):
    from backend.utils import auth_utils

    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "secret-token")
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "https://tradamind.com"
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def get(self, path, *, headers):
            assert path == "/api/workspace/exact-market?symbol=BTC&quote_currency=USDT"
            assert headers["authorization"] == "Bearer secret-token"
            raise OSError("secret-token private fixture 123")
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=Client))
    with pytest.raises(RuntimeError, match="^qa_readback_transport_failed$") as error:
        read_json(owner_id=7, path="/api/workspace/exact-market?symbol=BTC&quote_currency=USDT")
    assert "secret-token" not in str(error.value)
