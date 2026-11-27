"""Security and source-contract checks for the watch-only BTC connector."""

import asyncio
import logging

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.bot_api import BtcWatchWalletCreateRequest
from backend.services.btc_watch_wallet_service import (
    BtcWatchWalletService,
    _verified_preview,
    fetch_xpub_balance,
    validate_account_xpub,
    wallet_link_enabled,
)
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService


# Account-depth public key derived from the public BIP39 test mnemonic.
XPUB = "xpub6CatWdiZiodmUeTDp8LT5or8nmbKNcuyvz7WyksVFkKB4RHwCD3XyuvPEbvqAQY3rAPshWcMLoP2fMFMKHPJ4ZeZXYVUhLv1VMrjPC7PW6V"


def test_accepts_only_checksummed_mainnet_account_public_key():
    assert validate_account_xpub(XPUB) == XPUB
    with pytest.raises(ValueError):
        validate_account_xpub(XPUB[:-1] + ("1" if XPUB[-1] != "1" else "2"))
    with pytest.raises(ValueError):
        validate_account_xpub("xprv" + XPUB[4:])
    with pytest.raises(ValueError):
        validate_account_xpub("abandon " * 11 + "about")


def test_provider_requires_server_key_and_does_not_echo_xpub(monkeypatch):
    monkeypatch.delenv("ALCHEMY_BITCOIN_API_KEY", raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(fetch_xpub_balance(XPUB, "native_segwit"))
    assert error.value.status_code == 503
    assert XPUB not in str(error.value.detail)


def test_account_link_requires_explicit_provider_sharing_confirmation():
    with pytest.raises(ValidationError):
        BtcWatchWalletCreateRequest(
            label="Ledger", xpub=XPUB, script_type="native_segwit",
            provider_sharing_confirmed=False,
        )


def test_wallet_rollout_defaults_off_and_can_target_one_owner(monkeypatch):
    monkeypatch.delenv("BTC_WATCH_WALLET_ENABLED", raising=False)
    monkeypatch.setenv("BTC_WATCH_PILOT_USER_IDS", "7, invalid, 12")
    assert wallet_link_enabled(7) is True
    assert wallet_link_enabled(12) is True
    assert wallet_link_enabled(8) is False


def test_preview_is_owner_bound_and_required_before_saving(monkeypatch):
    monkeypatch.setenv("BTC_WATCH_PILOT_USER_IDS", "7")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-preview-signing-key")

    async def balance(_xpub, _script_type):
        return 123456789, 0

    monkeypatch.setattr("backend.services.btc_watch_wallet_service.fetch_xpub_balance", balance)
    preview = asyncio.run(BtcWatchWalletService(None).preview(7, xpub=XPUB, script_type="native_segwit"))
    assert preview["quantity_btc"] == "1.23456789"
    assert XPUB not in str(preview)
    token = preview["preview_token"]
    assert _verified_preview(token, user_id=7, xpub=XPUB, script_type="native_segwit")["c"] == 123456789
    for owner, kind, candidate in ((8, "native_segwit", token), (7, "taproot", token),
                                    (7, "native_segwit", token[:-1] + "0")):
        with pytest.raises(HTTPException) as error:
            _verified_preview(candidate, user_id=owner, xpub=XPUB, script_type=kind)
        assert error.value.status_code == 409
    with pytest.raises(ValidationError):
        BtcWatchWalletCreateRequest(
            label="Ledger", xpub=XPUB, script_type="native_segwit",
            provider_sharing_confirmed=True, balance_confirmed=True,
        )


def test_http_client_does_not_log_xpub_or_provider_key_at_info():
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_provider_parses_satoshis_and_uses_fixed_origin(monkeypatch):
    monkeypatch.setenv("ALCHEMY_BITCOIN_API_KEY", "test-key-12345678")
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, params):
            calls.append((url, params))
            return httpx.Response(200, json={"balance": "123456789", "unconfirmedBalance": "-1000"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert asyncio.run(fetch_xpub_balance(XPUB, "native_segwit")) == (123456789, -1000)
    assert calls[0][0].startswith("https://bitcoin-mainnet.g.alchemy.com/v2/test-key-12345678/api/v2/xpub/")
    assert "wpkh%28" in calls[0][0]
    assert calls[0][1] == {"details": "basic", "tokens": "nonzero"}


def test_bad_provider_balance_fails_closed_without_leaking_request(monkeypatch):
    monkeypatch.setenv("ALCHEMY_BITCOIN_API_KEY", "test-key-12345678")

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, *_args, **_kwargs):
            return httpx.Response(200, json={"balance": "-1"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as error:
        asyncio.run(fetch_xpub_balance(XPUB, "native_segwit"))
    assert error.value.status_code == 503
    assert XPUB not in str(error.value.detail)


def test_public_wallet_projection_never_returns_xpub():
    result = BtcWatchWalletService._public({
        "id": 4, "label": "Ledger BTC", "script_type": "native_segwit",
        "confirmed_sats": 123456789, "unconfirmed_sats": 0,
        "sync_status": "available", "provider": "alchemy_blockbook",
        "fetched_at": None, "last_attempt_at": None,
        "xpub_encrypted": "secret", "xpub_fingerprint": "also-secret",
    })
    assert result["quantity_btc"] == "1.23456789"
    assert "xpub_encrypted" not in result
    assert "xpub_fingerprint" not in result


def test_finn_portfolio_reasoning_keeps_wallet_provenance_without_xpub():
    service = FinnV2ReasoningContextService.__new__(FinnV2ReasoningContextService)
    facts = service._sanitize_facts({
        "global": {"total_equity": 100.0}, "bots": [],
        "watch_wallets": [{"id": 4, "label": "Ledger", "asset": "BTC",
                           "source": "self_custody_xpub", "quantity_btc": "1.23456789",
                           "sync_status": "available", "fetched_at": "2026-11-27T17:00:00Z",
                           "stale": False, "valuation_available": True,
                           "position_value_eur": 60000.0, "watch_only": True,
                           "xpub_encrypted": "must-not-appear"}],
    }, "read_portfolio")
    assert facts["watch_wallets"][0]["quantity_btc"] == "1.23456789"
    assert facts["watch_wallets_separate_from_global_equity"] is True
    assert "xpub_encrypted" not in str(facts)
