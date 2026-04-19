import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from celery import shared_task
from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)

TIMEOUT = 15
HEADERS = {"Content-Type": "application/json"}

@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=5, max=15), reraise=True)
def safe_request(url, params=None):
    resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
    if resp.status_code == 429: raise requests.exceptions.HTTPError("429_RATE_LIMIT")
    resp.raise_for_status()
    return resp.json()

# =====================================================
# 🌐 Global Ingestion Logic
# =====================================================

@shared_task(name="backend.celery_task.global_ingestion_task.run_global_ingestion")
def run_global_ingestion():
    """
    Haalt ALLE markt-data 1x op voor het hele platform.
    """
    logger.info("🌍 [Global-Ingestion] Start globale data-verzameling")
    
    # 1. Macro Data Ingestie
    fetch_global_macro_data()
    
    # 2. Market Indicator Ingestie (BTC Dom, etc.)
    fetch_global_market_indicators()
    
    # 3. Technical Data Ingestie (OHLCV-based)
    # Technicals kunnen we vaak lokaal uit 'market_data' berekenen, 
    # maar we kunnen hier ook externe bronnen toevoegen.
    
    logger.info("✅ [Global-Ingestion] Volledig afgerond")

# =====================================================
# 📡 Macro Ingestion
# =====================================================
def fetch_global_macro_data():
    conn = get_db_connection()
    if not conn: return
    
    try:
        # Haal actieve macro indicators op
        with conn.cursor() as cur:
            cur.execute("SELECT name, source, link FROM indicators WHERE category = 'macro' AND active = TRUE")
            indicators = cur.fetchall()

        for name, source, link in indicators:
            try:
                value = fetch_value_from_link(name, source, link)
                if value is not None:
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO global_macro_data (name, value) VALUES (%s, %s)", (name, value))
                    logger.debug(f"💾 Global Macro: {name} = {value}")
            except Exception:
                logger.error(f"❌ Fout bij global macro {name}", exc_info=True)
        
        conn.commit()
    finally:
        conn.close()

# =====================================================
# 📡 Market Ingestion
# =====================================================
def fetch_global_market_indicators():
    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, source, link FROM indicators WHERE category = 'market' AND active = TRUE")
            indicators = cur.fetchall()

        for name, source, link in indicators:
            try:
                value = fetch_value_from_link(name, source, link)
                if value is not None:
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO global_market_indicators (name, value) VALUES (%s, %s)", (name, value))
            except Exception:
                logger.error(f"❌ Fout bij global market indicator {name}", exc_info=True)
        
        conn.commit()
    finally:
        conn.close()

# De parser logica (gekopieerd uit macro_task.py voor nu)
def fetch_value_from_link(name, source, link):
    if not link: return None
    try:
        data = safe_request(link)
        source = source.lower() if source else ""
        
        if "fear" in link or "alternative" in source:
            return float(data["data"][0]["value"])
        if "coingecko" in source:
            return float(data["data"]["market_cap_percentage"]["btc"])
        if "fred" in source:
            val = data["observations"][-1]["value"]
            return float(val) if val not in (None, ".") else None
        if "yahoo" in source or "dxy" in name.lower():
            return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
            
        return None
    except Exception:
        return None
