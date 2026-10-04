import asyncio

from backend.services.finn_v2_tool_adapters.setup_inventory_tool_adapter import SetupInventoryToolAdapter


def test_saved_setup_inventory_exposes_weekday_name_alongside_stored_code():
    result = asyncio.run(SetupInventoryToolAdapter().execute(setups=[{
        "id": 41, "name": "ETH Vaste DCA", "symbol": "ETH", "setup_type": "dca",
        "dca_frequency": "weekly", "dca_day": "5",
    }]))

    row = result["data"].setups[0]
    assert row["dca_day"] == "5"
    assert row["dca_day_name"] == "friday"
