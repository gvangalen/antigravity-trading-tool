import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import auth_api


def test_registration_preserves_rate_limit_status(monkeypatch):
    def rate_limited(_request):
        raise HTTPException(status_code=429, detail="Te veel registratiepogingen.")

    monkeypatch.setattr(auth_api, "_apply_auth_register_rate_limit", rate_limited)

    with pytest.raises(HTTPException) as error:
        asyncio.run(auth_api.register_user(
            SimpleNamespace(email="test@example.com"),
            object(),
            SimpleNamespace(register_user=None),
        ))

    assert error.value.status_code == 429
