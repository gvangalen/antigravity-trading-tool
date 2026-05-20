from backend.schemas.technical_data_schema import TechnicalIndicatorRuleResponse


def test_technical_indicator_rule_response_allows_null_rule_metadata():
    response = TechnicalIndicatorRuleResponse(
        id=1,
        indicator="rsi",
        range_min=0,
        range_max=20,
        score=10,
        trend=None,
        interpretation=None,
        action=None,
    )

    assert response.indicator == "rsi"
    assert response.trend is None
    assert response.interpretation is None
    assert response.action is None
