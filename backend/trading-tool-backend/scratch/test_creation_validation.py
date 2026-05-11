import sys
import os
from fastapi import HTTPException

# Add project root to python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.services.setup_service import SetupService
from backend.services.bot_service import BotService

# ==========================================================
# MOCKING INFRASTRUCTURE FOR DATABASE SESSION (SELF-CONTAINED)
# ==========================================================
class MockResult:
    def __init__(self, row=None):
        self._row = row
    def fetchone(self):
        return self._row

class MockSession:
    def __init__(self):
        self.commits = 0
    async def execute(self, query, params=None):
        query_str = str(query).lower()
        if "bot_configs" in query_str:
            name = params.get("name", "").lower()
            if name == "duplicaat-bot":
                return MockResult((99,)) # Simulate duplicate bot ID 99
            return MockResult(None)
        elif "strategies" in query_str:
            strategy_id = params.get("strategy_id")
            if strategy_id == 888:
                return MockResult(None) # Simulate non-existing strategy
            return MockResult((strategy_id,))
        return MockResult(None)
    async def commit(self):
        self.commits += 1


# ==========================================================
# TEST SETUPS VALIDATION
# ==========================================================
def test_setups_validation():
    print("📋 Testing SetupService validate_setup_payload...")
    service = SetupService(db_session=None)

    # 1. Test a valid setup payload
    valid_payload = {
        "name": "Super DCA Setup",
        "symbol": "btc",
        "setup_type": "dca",
        "dca_frequency": "daily",
        "min_macro_score": -50,
        "max_macro_score": 80,
        "min_investment": 10.0
    }
    # Should pass without throwing any exception
    service.validate_setup_payload(valid_payload, is_update=False)

    # 2. Test missing or empty name
    try:
        service.validate_setup_payload({**valid_payload, "name": ""}, is_update=False)
        assert False, "Expected HTTPException for empty name"
    except HTTPException as e:
        assert e.status_code == 400
        assert "Naam is verplicht" in e.detail

    # 3. Test name too long
    try:
        service.validate_setup_payload({**valid_payload, "name": "A" * 81}, is_update=False)
        assert False, "Expected HTTPException for name > 80 chars"
    except HTTPException as e:
        assert e.status_code == 400
        assert "maximaal 80 karakters" in e.detail

    # 4. Test missing/empty symbol
    try:
        service.validate_setup_payload({**valid_payload, "symbol": "   "}, is_update=False)
        assert False, "Expected HTTPException for empty symbol"
    except HTTPException as e:
        assert e.status_code == 400
        assert "Symbool is verplicht" in e.detail

    # 5. Test invalid symbol length
    try:
        service.validate_setup_payload({**valid_payload, "symbol": "B" * 11}, is_update=False)
        assert False, "Expected HTTPException for long symbol"
    except HTTPException as e:
        assert e.status_code == 400
        assert "tussen 2 en 10 karakters" in e.detail

    # 6. Test invalid setup_type
    try:
        service.validate_setup_payload({**valid_payload, "setup_type": "invalid"}, is_update=False)
        assert False, "Expected HTTPException for invalid setup_type"
    except HTTPException as e:
        assert e.status_code == 400
        assert "Moet 'dca' of 'trade' zijn" in e.detail

    # 7. Test DCA frequency missing
    try:
        payload = valid_payload.copy()
        payload.pop("dca_frequency")
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for missing dca_frequency"
    except HTTPException as e:
        assert e.status_code == 400
        assert "dca_frequency is verplicht" in e.detail

    # 8. Test invalid weekly day
    try:
        payload = {**valid_payload, "dca_frequency": "weekly", "dca_day": 8}
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for invalid weekly day"
    except HTTPException as e:
        assert e.status_code == 400
        assert "dca_day moet een getal tussen 1" in e.detail

    # 9. Test invalid monthly day
    try:
        payload = {**valid_payload, "dca_frequency": "monthly", "dca_month_day": 32}
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for invalid monthly day"
    except HTTPException as e:
        assert e.status_code == 400
        assert "dca_month_day moet een getal tussen 1" in e.detail

    # 10. Test invalid score limits
    try:
        payload = {**valid_payload, "min_macro_score": -101}
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for min score < -100"
    except HTTPException as e:
        assert e.status_code == 400
        assert "min_macro_score moet een getal tussen -100" in e.detail

    try:
        payload = {**valid_payload, "max_macro_score": 105}
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for max score > 100"
    except HTTPException as e:
        assert e.status_code == 400
        assert "max_macro_score moet een getal tussen -100" in e.detail

    # 11. Test min score > max score
    try:
        payload = {**valid_payload, "min_macro_score": 50, "max_macro_score": 40}
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for min_score > max_score"
    except HTTPException as e:
        assert e.status_code == 400
        assert "mag niet hoger zijn dan max_" in e.detail

    # 12. Test negative investment
    try:
        payload = {**valid_payload, "min_investment": -1.5}
        service.validate_setup_payload(payload, is_update=False)
        assert False, "Expected HTTPException for negative min_investment"
    except HTTPException as e:
        assert e.status_code == 400
        assert "min_investment mag niet negatief zijn" in e.detail

    print("✅ SetupService validate_setup_payload passed all validation tests!")


# ==========================================================
# TEST BOTS VALIDATION
# ==========================================================
async def test_bots_validation():
    print("\n📋 Testing BotService validate_bot_payload...")
    mock_db = MockSession()
    service = BotService(db_session=mock_db)

    # 1. Test a valid bot config payload
    valid_payload = {
        "name": "Super Finn Bot",
        "strategy_id": 10,
        "mode": "manual",
        "risk_profile": "balanced",
        "cadence": "daily",
        "budget_total_eur": 500.0,
        "budget_daily_limit_eur": 50.0,
        "budget_min_order_eur": 10.0,
        "budget_max_order_eur": 40.0,
        "max_asset_exposure_pct": 50.0
    }
    # Should pass without throwing any exception
    await service.validate_bot_payload(valid_payload, user_id=1, is_update=False)

    # 2. Test duplicate name conflict (idempotency/flaky check)
    try:
        await service.validate_bot_payload({**valid_payload, "name": "Duplicaat-Bot"}, user_id=1, is_update=False)
        assert False, "Expected HTTPException (409) for duplicate bot name"
    except HTTPException as e:
        assert e.status_code == 409
        assert "Een botconfiguratie met de naam" in e.detail

    # 3. Test non-existing or unauthorized strategy_id
    try:
        await service.validate_bot_payload({**valid_payload, "strategy_id": 888}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for invalid strategy ownership"
    except HTTPException as e:
        assert e.status_code == 400
        assert "strategy_id" in e.detail and "bestaat niet" in e.detail

    # 4. Test negative budgets
    try:
        await service.validate_bot_payload({**valid_payload, "budget_total_eur": -10}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for negative budget total"
    except HTTPException as e:
        assert e.status_code == 400
        assert "budget_total_eur moet een positief getal" in e.detail

    # 5. Test logical budget violations: daily limit > total budget
    try:
        await service.validate_bot_payload({**valid_payload, "budget_total_eur": 100, "budget_daily_limit_eur": 150}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for daily limit > total budget"
    except HTTPException as e:
        assert e.status_code == 400
        assert "Daglimiet" in e.detail and "mag niet groter zijn" in e.detail

    # 6. Test logical budget violations: min order > max order
    try:
        await service.validate_bot_payload({**valid_payload, "budget_min_order_eur": 25, "budget_max_order_eur": 20}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for min order > max order"
    except HTTPException as e:
        assert e.status_code == 400
        assert "budget_min_order_eur mag niet groter zijn" in e.detail

    # 7. Test logical budget violations: max order > total budget
    try:
        await service.validate_bot_payload({**valid_payload, "budget_total_eur": 100, "budget_max_order_eur": 110}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for max order > total budget"
    except HTTPException as e:
        assert e.status_code == 400
        assert "budget_max_order_eur mag niet groter zijn" in e.detail

    # 8. Test exposure out of range
    try:
        await service.validate_bot_payload({**valid_payload, "max_asset_exposure_pct": 101.5}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for exposure > 100"
    except HTTPException as e:
        assert e.status_code == 400
        assert "max_asset_exposure_pct moet een getal tussen" in e.detail

    # 9. Test invalid cadence enum
    try:
        await service.validate_bot_payload({**valid_payload, "cadence": "every-minute"}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for invalid cadence"
    except HTTPException as e:
        assert e.status_code == 400
        assert "cadence moet één van" in e.detail

    # 10. Test invalid mode enum
    try:
        await service.validate_bot_payload({**valid_payload, "mode": "unmanned"}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for invalid mode"
    except HTTPException as e:
        assert e.status_code == 400
        assert "mode moet één van" in e.detail

    # 11. Test invalid risk enum
    try:
        await service.validate_bot_payload({**valid_payload, "risk_profile": "kamikaze"}, user_id=1, is_update=False)
        assert False, "Expected HTTPException for invalid risk profile"
    except HTTPException as e:
        assert e.status_code == 400
        assert "risk_profile moet één van" in e.detail

    print("✅ BotService validate_bot_payload passed all validation & conflict tests!")


if __name__ == "__main__":
    print("🚀 Starting Setup & Bot Creation Endpoints Validation verification suite...")
    import asyncio
    try:
        test_setups_validation()
        asyncio.run(test_bots_validation())
        print("\n🎉 All Verification Tests Completed with 100% SUCCESS!")
    except Exception as e:
        print(f"\n❌ Verification failed with error: {e}")
        sys.exit(1)
