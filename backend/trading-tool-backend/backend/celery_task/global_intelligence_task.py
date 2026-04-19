import logging
from celery import shared_task

from backend.ai_agents.macro_ai_agent import run_macro_agent
from backend.ai_agents.market_ai_agent import run_market_agent
from backend.ai_agents.technical_ai_agent import run_technical_agent

logger = logging.getLogger(__name__)

@shared_task(name="backend.celery_task.global_intelligence_task.run_global_intelligence")
def run_global_intelligence():
    """
    Orchestrator voor de Global Intelligence Layer.
    Draait de 3 grote agenten sequentieel op basis van GLOBALE data.
    """
    logger.info("🤖 [Global-Intelligence] Start platform-brede AI analyse")

    try:
        # 1. Macro Analyse
        logger.info("🌍 [Global-Intelligence] Stap 1: Macro AI")
        run_macro_agent()

        # 2. Market Analyse
        logger.info("🌍 [Global-Intelligence] Stap 2: Market AI")
        run_market_agent()

        # 3. Technical Analyse
        logger.info("🌍 [Global-Intelligence] Stap 3: Technical AI")
        run_technical_agent()

        logger.info("✅ [Global-Intelligence] Volledige markt-analyse afgerond")
    except Exception:
        logger.error("❌ [Global-Intelligence] Kritieke fout in orchestrator", exc_info=True)
