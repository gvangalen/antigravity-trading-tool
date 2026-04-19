import logging
from celery import shared_task
from backend.utils.db import get_db_connection
from backend.utils.scoring_utils import normalize_indicator_name
from backend.utils.scoring_engine import score_indicator

logger = logging.getLogger(__name__)

@shared_task(name="backend.celery_task.user_scoring_sync_task.sync_all_users_scores")
def sync_all_users_scores():
    """
    Dispatcher dat voor alle actieve users hun persoonlijke scores 
    opnieuw berekent op basis van de laatste GLOBAL DATA.
    """
    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE is_active = TRUE")
            user_ids = [r[0] for r in cur.fetchall()]
        
        logger.info(f"🔄 [Score-Sync] Start berekening voor {len(user_ids)} users")
        
        for user_id in user_ids:
            # We kunnen dit parallel doen (via .delay), 
            # maar omdat het pure SQL/Math is, is het vaak sneller 
            # om het in batches te doen of gewoon sequentieel per user.
            sync_scores_for_user(user_id)
            
        logger.info("✅ [Score-Sync] Alle users bijgewerkt")
    finally:
        conn.close()

def sync_scores_for_user(user_id: int):
    """
    Berekent Macro, Market en Technical scores voor 1 user 
    op basis van de globale bron.
    """
    conn = get_db_connection()
    if not conn: return
    
    try:
        # 1. Sync Macro
        sync_category_for_user(conn, user_id, "macro", "global_macro_data", "macro_data")
        
        # 2. Sync Market
        sync_category_for_user(conn, user_id, "market", "global_market_indicators", "market_data_indicators")
        
        # 3. Sync Technical
        sync_category_for_user(conn, user_id, "technical", "global_technical_indicators", "technical_indicators")
        
        conn.commit()
    except Exception:
        conn.rollback()
        logger.error(f"❌ [Score-Sync] Fout bij user {user_id}", exc_info=True)
    finally:
        conn.close()

def sync_category_for_user(conn, user_id, category, global_table, user_table):
    """
    Helper om 1 categorie (macro/market/technical) te syncen.
    """
    # Kolomnaam in de global_table
    name_col = "indicator" if category == "technical" else "name"
    
    # 1. Haal de laatste global readings op
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT ON ({name_col}) {name_col}, value 
            FROM {global_table} 
            ORDER BY {name_col}, timestamp DESC
        """)
        readings = cur.fetchall()
        
    for name, value in readings:
        if value is None: continue
        
        # 2. Pas de gebruikers-regels toe (Standard/Contrarian/Custom)
        # score_indicator handelt dit intern af via de 'Rules' tabellen.
        scored = score_indicator(
            conn=conn,
            category=category,
            indicator=normalize_indicator_name(name),
            value=value,
            user_id=user_id
        )
        
        # 3. Opslaan in de user-tabel (zijn persoonlijke 'lens')
        # We gebruiken UPSERT op de meest recente record voor vandaag (of per indicator)
        if category == "technical":
            cur.execute("""
                INSERT INTO technical_indicators (indicator, value, score, advies, uitleg, user_id, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id, indicator, score_date) 
                DO UPDATE SET 
                    value = EXCLUDED.value,
                    score = EXCLUDED.score,
                    advies = EXCLUDED.advies,
                    uitleg = EXCLUDED.uitleg,
                    timestamp = NOW()
            """, (name, value, scored['score'], scored['action'], scored['interpretation'], user_id))
        else:
            cur.execute(f"""
                INSERT INTO {user_table} (user_id, name, value, trend, interpretation, action, score, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id, name, score_date)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    score = EXCLUDED.score,
                    trend = EXCLUDED.trend,
                    interpretation = EXCLUDED.interpretation,
                    action = EXCLUDED.action,
                    timestamp = NOW()
            """, (user_id, name, value, scored['trend'], scored['interpretation'], scored['action'], scored['score']))
