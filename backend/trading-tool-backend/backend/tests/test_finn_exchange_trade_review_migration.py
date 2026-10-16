"""Schema guards prevent an attested exchange review from impersonating ledger facts."""

import runpy
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.finn_exchange_trade_review_schema import ExchangeTradeReviewCreate


def test_attestation_schema_requires_strict_fill_ids_and_closure():
    from uuid import uuid4

    payload = {"fill_ids": [1, 2], "closure_confirmed": True,
               "idempotency_key": uuid4()}
    assert ExchangeTradeReviewCreate(**payload).same_account_confirmed is False
    for ids in ([True, 2], ["1", 2], [1, 1.5]):
        with pytest.raises(ValidationError):
            ExchangeTradeReviewCreate(**{**payload, "fill_ids": ids})
    with pytest.raises(ValidationError):
        ExchangeTradeReviewCreate(**{**payload, "closure_confirmed": None})


def test_migration_has_owner_composite_fks_and_origin_separation():
    path = Path(__file__).parents[1] / "scripts/migrations/2026_10_19_finn_exchange_attested_reviews.py"
    sql = runpy.run_path(str(path))["SQL"]
    assert "origin='exchange_user_attested'" in sql
    assert "bot_id IS NULL AND opening_ledger_id IS NULL AND closing_ledger_id IS NULL" in sql
    assert "pnl_status='not_comparable'" in sql
    assert "PRIMARY KEY (user_id, exchange_fill_id)" in sql
    assert "FOREIGN KEY (user_id, exchange_fill_id)" in sql
    assert "FOREIGN KEY (user_id, review_id)" in sql
