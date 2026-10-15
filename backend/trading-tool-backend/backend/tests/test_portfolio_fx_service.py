from datetime import datetime, timedelta, timezone

from backend.services.portfolio_fx_service import inverted_eur_quote, price_in_eur


def test_usd_and_usdt_require_a_recent_dated_conversion():
    now = datetime.now(timezone.utc)
    for quote in ("USD", "USDT"):
        assert price_in_eur(price=100, price_at=now, quote_currency=quote, fx=None, now=now)[0] is None
        assert price_in_eur(price=100, price_at=now, quote_currency=quote,
                            fx={"eur_per_unit": 0.8, "observed_at": now-timedelta(hours=25)}, now=now)[0] is None
        converted = price_in_eur(price=100, price_at=now, quote_currency=quote,
                                 fx={"eur_per_unit": 0.8, "observed_at": now}, now=now)
        assert converted == (80.0, now, 0.8, now)


def test_missing_future_and_stale_prices_fail_closed():
    now = datetime.now(timezone.utc)
    for when in (None, now+timedelta(minutes=1), now-timedelta(hours=25)):
        assert price_in_eur(price=100, price_at=when, quote_currency="EUR", fx=None, now=now)[0] is None
    assert price_in_eur(price=100, price_at=now, quote_currency="EUR", fx=None, now=now)[0] == 100
    assert price_in_eur(price=100, price_at=now, quote_currency="GBP", fx=None, now=now)[0] is None


def test_inverted_quote_never_assumes_parity():
    now = datetime.now(timezone.utc)
    assert inverted_eur_quote(1.25, now, now=now) == 0.8
    assert inverted_eur_quote(1.25, None, now=now) is None
    assert inverted_eur_quote(1e-320, now, now=now) is None
    assert price_in_eur(price=1e308, price_at=now, quote_currency="USD",
                        fx={"eur_per_unit": 1e308, "observed_at": now}, now=now)[0] is None
