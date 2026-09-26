from backend.domain.strategy_level_geometry import strategy_level_geometry


def test_long_strategy_multiple_targets_have_static_ratios():
    result = strategy_level_geometry("80000", "76000", ["88000", "92000"])
    assert result["status"] == "completed"
    assert result["direction"] == "long"
    assert result["risk_per_unit"] == "4000"
    assert result["entry_stop_distance_percent"] == "5.00"
    assert [target["reward_to_risk"] for target in result["targets"]] == ["2.00", "3.00"]


def test_short_strategy_and_invalid_targets():
    result = strategy_level_geometry(100, 110, [80, 70])
    assert result["status"] == "completed"
    assert result["direction"] == "short"
    assert [target["reward_to_risk"] for target in result["targets"]] == ["2.00", "3.00"]
    assert strategy_level_geometry(100, 90, [80])["reason"] == "target_wrong_side_of_entry"
    assert strategy_level_geometry(100, 100, [120])["reason"] == "risk_not_positive"
