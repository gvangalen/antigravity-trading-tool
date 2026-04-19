import logging
from celery import shared_task
from backend.utils.db import get_db_connection
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(name="backend.celery_task.daily_usage_reset.reset_daily_ai_quotas")
def reset_daily_ai_quotas():
    """
    Zet elke nacht om 00:00 de ai_requests_used_day teller op 0 voor alle users.
    Op de 1e van de maand wordt ook de ai_usage_current voor de administratie gereset.
    """
    conn = get_db_connection()
    if not conn: return
    
    try:
        now = datetime.now()
        is_first_of_month = (now.day == 1)
        
        with conn.cursor() as cur:
            # 1. Dagelijkse requests resetten
            logger.info("🕒 [Quota-Reset] Resetting daily AI request counts...")
            cur.execute("""
                UPDATE users 
                SET ai_requests_used_day = 0,
                    last_usage_reset = NOW()
            """)
            
            # 2. Maandelijkse euro-teller resetten (alleen op de 1e)
            if is_first_of_month:
                logger.info("📅 [Quota-Reset] First of month! Resetting monthly usage costs...")
                cur.execute("UPDATE users SET ai_usage_current = 0.00")
                
            conn.commit()
            logger.info("✅ [Quota-Reset] Quota reset voltooid.")
            
    except Exception:
        conn.rollback()
        logger.error("❌ [Quota-Reset] Fout bij quota reset", exc_info=True)
    finally:
        conn.close()
