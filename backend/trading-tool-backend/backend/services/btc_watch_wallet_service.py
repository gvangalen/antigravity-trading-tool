"""Read-only Bitcoin account observation. No private keys or signing paths."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy import text

from backend.utils.encryption_utils import EncryptionUtils


_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_WRAPPERS = {
    "legacy": "pkh({})",
    "nested_segwit": "sh(wpkh({}))",
    "native_segwit": "wpkh({})",
    "taproot": "tr({})",
}
_PROVIDER_ORIGIN = "https://bitcoin-mainnet.g.alchemy.com"
_MAX_SATS = 21_000_000 * 100_000_000

# httpx logs complete request URLs at INFO, including the provider key and xpub.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def provider_configured() -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,128}", os.getenv("ALCHEMY_BITCOIN_API_KEY", "").strip()))


def validate_account_xpub(value: str) -> str:
    """Accept only a mainnet, account-depth, public BIP32 xpub."""
    key = str(value or "").strip()
    if not re.fullmatch(r"xpub[1-9A-HJ-NP-Za-km-z]{100,120}", key):
        raise ValueError("btc_xpub_invalid")
    number = 0
    for character in key:
        number = number * 58 + _BASE58.index(character)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    raw = b"\x00" * (len(key) - len(key.lstrip("1"))) + raw
    if len(raw) != 82 or hashlib.sha256(hashlib.sha256(raw[:78]).digest()).digest()[:4] != raw[78:]:
        raise ValueError("btc_xpub_invalid")
    if raw[:4] != bytes.fromhex("0488b21e") or raw[4] != 3 or raw[45] not in (2, 3):
        raise ValueError("btc_xpub_invalid")
    return key


def _sats(value: object, *, signed: bool = False) -> int:
    if type(value) not in (str, int) or not re.fullmatch(r"-?\d{1,16}", str(value)):
        raise ValueError("btc_provider_balance_invalid")
    amount = int(value)
    if abs(amount) > _MAX_SATS or (amount < 0 and not signed):
        raise ValueError("btc_provider_balance_invalid")
    return amount


async def fetch_xpub_balance(xpub: str, script_type: str) -> tuple[int, int]:
    """Use a fixed HTTPS Blockbook endpoint; never accept a user-supplied URL."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not provider_configured():
        raise HTTPException(503, "BTC-walletprovider is nog niet geconfigureerd.")
    api_key = os.getenv("ALCHEMY_BITCOIN_API_KEY", "").strip()
    if script_type not in _WRAPPERS:
        raise ValueError("btc_script_type_invalid")
    descriptor = _WRAPPERS[script_type].format(validate_account_xpub(xpub))
    url = f"{_PROVIDER_ORIGIN}/v2/{api_key}/api/v2/xpub/{quote(descriptor, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=False) as client:
            response = await asyncio.wait_for(
                client.get(url, params={"details": "basic", "tokens": "nonzero"}),
                timeout=6.0,
            )
        if response.status_code != 200 or len(response.content) > 512_000:
            raise ValueError("btc_provider_unavailable")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("btc_provider_balance_invalid")
        return _sats(payload.get("balance")), _sats(payload.get("unconfirmedBalance", "0"), signed=True)
    except (httpx.HTTPError, ValueError, asyncio.TimeoutError):
        # Never include the provider URL, key, descriptor, or raw response in logs/errors.
        raise HTTPException(503, "BTC-walletsaldo kon niet worden vernieuwd.") from None


class BtcWatchWalletService:
    def __init__(self, session):
        self.session = session

    async def list(self, user_id: int) -> list[dict]:
        rows = await self.session.execute(text("""
            SELECT id, label, script_type, confirmed_sats, unconfirmed_sats,
                   sync_status, provider, fetched_at, last_attempt_at
            FROM btc_watch_wallets WHERE user_id=:user_id ORDER BY id
        """), {"user_id": user_id})
        return [self._public(dict(row._mapping)) for row in rows.fetchall()]

    @staticmethod
    def _public(row: dict) -> dict:
        sats = row.get("confirmed_sats")
        return {
            "id": int(row["id"]), "label": row["label"], "asset": "BTC",
            "source": "self_custody_xpub", "script_type": row["script_type"],
            "quantity_btc": str(Decimal(int(sats)) / Decimal(100_000_000)) if sats is not None else None,
            "confirmed_sats": int(sats) if sats is not None else None,
            "unconfirmed_sats": int(row["unconfirmed_sats"]) if row.get("unconfirmed_sats") is not None else None,
            "sync_status": row["sync_status"], "provider": row.get("provider"),
            "fetched_at": row.get("fetched_at"), "last_attempt_at": row.get("last_attempt_at"),
            "watch_only": True,
        }

    async def create(self, user_id: int, *, label: str, xpub: str, script_type: str) -> dict:
        if not provider_configured():
            raise HTTPException(503, "BTC-walletprovider is nog niet geconfigureerd.")
        try:
            key = validate_account_xpub(xpub)
        except ValueError:
            raise HTTPException(422, "Gebruik een publieke BTC-account-xpub uit Ledger Wallet.") from None
        if script_type not in _WRAPPERS or not 1 <= len(label.strip()) <= 80:
            raise HTTPException(422, "BTC-accountgegevens zijn ongeldig.")
        count = await self.session.execute(text(
            "SELECT COUNT(*) FROM btc_watch_wallets WHERE user_id=:user_id"
        ), {"user_id": user_id})
        if int(count.scalar_one()) >= 10:
            raise HTTPException(409, "Maximaal tien BTC-accounts per gebruiker.")
        digest = hashlib.sha256(key.encode()).hexdigest()
        duplicate = await self.session.execute(text("""
            SELECT 1 FROM btc_watch_wallets WHERE user_id=:user_id AND xpub_fingerprint=:digest
        """), {"user_id": user_id, "digest": digest})
        if duplicate.first():
            raise HTTPException(409, "Dit BTC-account is al gekoppeld.")
        row = await self.session.execute(text("""
            INSERT INTO btc_watch_wallets
                (user_id, label, xpub_encrypted, xpub_fingerprint, script_type)
            VALUES (:user_id, :label, :encrypted, :digest, :script_type)
            RETURNING id, label, script_type, confirmed_sats, unconfirmed_sats,
                      sync_status, provider, fetched_at, last_attempt_at
        """), {"user_id": user_id, "label": label.strip(),
               "encrypted": EncryptionUtils.encrypt(key), "digest": digest,
               "script_type": script_type})
        result = self._public(dict(row.first()._mapping))
        await self.session.commit()
        return result

    async def remove(self, user_id: int, wallet_id: int) -> None:
        result = await self.session.execute(text("""
            DELETE FROM btc_watch_wallets WHERE id=:wallet_id AND user_id=:user_id
            RETURNING id
        """), {"user_id": user_id, "wallet_id": wallet_id})
        if result.first() is None:
            raise HTTPException(404, "BTC-account niet gevonden.")
        await self.session.commit()

    async def refresh(self, user_id: int, wallet_id: int) -> dict:
        row = await self.session.execute(text("""
            SELECT xpub_encrypted, script_type FROM btc_watch_wallets
            WHERE id=:wallet_id AND user_id=:user_id
        """), {"user_id": user_id, "wallet_id": wallet_id})
        entry = row.first()
        if entry is None:
            raise HTTPException(404, "BTC-account niet gevonden.")
        xpub = EncryptionUtils.decrypt(entry[0])
        if not xpub:
            raise HTTPException(503, "BTC-accountgegevens konden niet worden gelezen.")
        requested_at = datetime.now(timezone.utc)
        try:
            confirmed, unconfirmed = await fetch_xpub_balance(xpub, entry[1])
        except HTTPException:
            await self.session.execute(text("""
                UPDATE btc_watch_wallets SET sync_status='unavailable',
                    last_attempt_at=:attempt, updated_at=NOW()
                WHERE id=:wallet_id AND user_id=:user_id
                  AND (last_attempt_at IS NULL OR last_attempt_at <= :attempt)
            """), {"user_id": user_id, "wallet_id": wallet_id, "attempt": requested_at})
            await self.session.commit()
            raise
        fetched_at = datetime.now(timezone.utc)
        updated = await self.session.execute(text("""
            UPDATE btc_watch_wallets SET confirmed_sats=:confirmed,
                unconfirmed_sats=:unconfirmed, sync_status='available',
                provider='alchemy_blockbook', fetched_at=:fetched,
                last_attempt_at=:attempt, updated_at=NOW()
            WHERE id=:wallet_id AND user_id=:user_id
              AND (last_attempt_at IS NULL OR last_attempt_at <= :attempt)
            RETURNING id, label, script_type, confirmed_sats, unconfirmed_sats,
                      sync_status, provider, fetched_at, last_attempt_at
        """), {"user_id": user_id, "wallet_id": wallet_id,
               "confirmed": confirmed, "unconfirmed": unconfirmed,
               "attempt": requested_at, "fetched": fetched_at})
        row = updated.first()
        if row is None:
            await self.session.rollback()
            raise HTTPException(409, "BTC-account is intussen verwijderd of vernieuwd.")
        await self.session.commit()
        return self._public(dict(row._mapping))
