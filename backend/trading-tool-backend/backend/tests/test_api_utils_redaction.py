from backend.utils.api_utils import redact_url_query


def test_redact_url_query_hides_known_secret_query_parameters():
    redacted = redact_url_query(
        "https://api.twelvedata.com/time_series?symbol=BTC%2FUSD&apikey=leaked&token=also-leaked"
    )

    assert "leaked" not in redacted
    assert "also-leaked" not in redacted
    assert "symbol=BTC%2FUSD" in redacted
    assert "apikey=%5Bredacted%5D" in redacted
