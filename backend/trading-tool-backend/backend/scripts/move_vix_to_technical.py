import asyncio
import logging
from sqlalchemy import text, delete, insert
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import Indicator, MacroIndicatorRule, TechnicalIndicatorRule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("move_vix")

async def migrate():
    async with async_session_factory() as s:
        # 1. Update Indicator Category
        logger.info("Changing VIX category to 'technical'...")
        vix = await s.get(Indicator, "vix")
        if vix:
            vix.category = "technical"
            logger.info("✅ Indicator updated.")
        else:
            logger.warning("⚠️ VIX indicator not found.")

        # 2. Transfer Rules
        logger.info("Transferring rules from macro to technical...")
        
        # Get macro rules for vix
        macro_rules = await s.execute(
            text("SELECT range_min, range_max, score, trend, interpretation, action, score_mode, weight, is_active, user_id FROM macro_indicator_rules WHERE indicator = 'vix'")
        )
        rows = macro_rules.fetchall()
        
        if rows:
            # Delete existing technical rules for vix to avoid duplicates
            await s.execute(
                text("DELETE FROM technical_indicator_rules WHERE indicator = 'vix'")
            )
            
            for r in rows:
                new_rule = TechnicalIndicatorRule(
                    indicator="vix",
                    range_min=r.range_min,
                    range_max=r.range_max,
                    score=r.score,
                    trend=r.trend,
                    interpretation=r.interpretation,
                    action=r.action,
                    score_mode=r.score_mode,
                    weight=r.weight,
                    is_active=r.is_active,
                    user_id=r.user_id
                )
                s.add(new_rule)
            
            # Clean up macro rules
            await s.execute(
                text("DELETE FROM macro_indicator_rules WHERE indicator = 'vix'")
            )
            logger.info(f"✅ Transferred {len(rows)} rules.")
        else:
            logger.warning("⚠️ No macro rules found for VIX.")

        await s.commit()
        print("🚀 VIX successfully migrated to Technicals!")

if __name__ == "__main__":
    asyncio.run(migrate())
