#!/usr/bin/env python3
"""Sync normalized latest market snapshots into market_data."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from backend.infrastructure.database import async_session_factory
from backend.services.market_data_ingestion_service import MarketDataIngestionService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync latest market snapshots into market_data.")
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Symbols to sync, for example BTC SOL MSTR SPY. Defaults to the FINN V1 core set.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first provider or persistence error.",
    )
    return parser.parse_args()


async def _run(symbols: Sequence[str] | None, fail_fast: bool) -> dict:
    async with async_session_factory() as session:
        service = MarketDataIngestionService(session)
        if symbols:
            return await service.ingest_latest_snapshots(
                symbols,
                commit=True,
                continue_on_error=not fail_fast,
            )
        return await service.ingest_default_v1_snapshots(
            commit=True,
            continue_on_error=not fail_fast,
        )


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args.symbols, args.fail_fast))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
