#!/usr/bin/env python3
"""Sync supported technical indicators for one user and a set of symbols."""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.infrastructure.database import async_session_factory
from backend.services.technical_data_service import TechnicalDataService


DEFAULT_INDICATORS = ["rsi", "ma_50", "ma_200", "ema_20_gap_pct", "ema_50_gap_pct", "macd_hist_pct", "atr_pct", "adx"]
DEFAULT_SYMBOLS = ["SPY", "MSTR"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync technical indicators for one user.")
    parser.add_argument("--user-id", type=int, required=True, help="Target user id.")
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Symbols to sync.")
    parser.add_argument(
        "--indicators",
        nargs="*",
        default=DEFAULT_INDICATORS,
        help="Indicator names to sync.",
    )
    return parser.parse_args()


async def _run(user_id: int, symbols: list[str], indicators: list[str]) -> dict:
    results: dict[str, dict] = {}
    async with async_session_factory() as session:
        service = TechnicalDataService(session)
        for symbol in symbols:
            if indicators:
                results[symbol] = await service.sync_effective_indicators(
                    user_id,
                    symbol,
                    explicit_indicators=indicators,
                )
            else:
                results[symbol] = await service.sync_effective_indicators(user_id, symbol)
            await session.commit()
    return results


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args.user_id, args.symbols, args.indicators))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
