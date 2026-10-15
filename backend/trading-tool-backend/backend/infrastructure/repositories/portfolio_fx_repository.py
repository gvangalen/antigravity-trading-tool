"""Persist provider-observed conversion rates with monotonic source times."""

from __future__ import annotations

from backend.utils.db import get_db_connection


def store_portfolio_fx_rates(rows: list[tuple]) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute("""
                    INSERT INTO portfolio_fx_rates
                        (quote_currency, eur_per_unit, provider, provider_pair, source_price, observed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (quote_currency) DO UPDATE SET
                        eur_per_unit = EXCLUDED.eur_per_unit,
                        provider = EXCLUDED.provider,
                        provider_pair = EXCLUDED.provider_pair,
                        source_price = EXCLUDED.source_price,
                        observed_at = EXCLUDED.observed_at,
                        fetched_at = NOW()
                    WHERE portfolio_fx_rates.observed_at < EXCLUDED.observed_at
                """, row)
