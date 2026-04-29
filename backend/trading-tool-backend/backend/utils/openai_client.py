import os
import json
import logging
import time
import re
import asyncio
from typing import Any, Dict, Optional
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ============================================================
# ⚙️ Setup
# ============================================================
# Probeer .env te vinden in CWD of in /backend map
env_path = Path(".") / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent.parent / ".env"

load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not api_key:
    logger.warning("⚠️ OPENAI_API_KEY ontbreekt in de omgeving. AI functionaliteit is beperkt.")

client = None
if api_key:
    try:
        client = OpenAI(api_key=api_key)
        logger.info(f"🤖 OpenAI Client geïnitialiseerd (Model: {model})")
    except Exception as e:
        logger.error(f"❌ Fout bij initialiseren OpenAI Client: {e}")

# ============================================================
# 🔥 AI DEFAULTS
# ============================================================
TEXT_TEMP = float(os.getenv("OPENAI_TEXT_TEMP", "0.4"))
JSON_TEMP = float(os.getenv("OPENAI_JSON_TEMP", "0.2"))
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "500"))

# ============================================================
# 🧰 JSON parsing helper
# ============================================================
def _strip_fences(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"^\s*```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()

def sanitize_json_output(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {}
    text = _strip_fences(raw_text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                candidate = m.group(0).replace("True", "true").replace("False", "false")
                return json.loads(candidate)
            except:
                pass
    return {}

# ============================================================
# ✅ GPT JSON CALL
# ============================================================
def ask_gpt_json(
    *,
    prompt: str,
    system_role: str,
    schema: Optional[Dict[str, Any]] = None,
    retries: int = 2,
    max_tokens: Optional[int] = None
) -> Dict[str, Any]:
    """Genereert een gestructureerde JSON response."""
    
    if not client:
        logger.error("❌ GPT JSON Call gefaald: Geen OpenAI Client (Missing API Key)")
        return {"error": "AI is offline"}

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt + "\n\nRETURN ONLY VALID JSON."}
    ]

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🧠 GPT JSON Call (Attempt {attempt})")
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=JSON_TEMP,
                max_tokens=max_tokens or MAX_TOKENS,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            parsed = sanitize_json_output(content)

            if parsed:
                return parsed
            
        except Exception as e:
            logger.error(f"❌ OpenAI JSON API Error (Attempt {attempt}): {e}")

            # 🔥 STOP bij quota errors
            if "insufficient_quota" in str(e):
                logger.error("❌ QUOTA bereikt → stop retries")
                return {"error": "quota"}

            if attempt == retries:
                return {"error": str(e)}

            time.sleep(1)

    return {"error": "Failed to generate valid JSON"}

# ============================================================
# 🧠 GPT TEXT CALL
# ============================================================
def ask_gpt_text(
    *,
    prompt: str,
    system_role: str,
    retries: int = 2,
    max_tokens: Optional[int] = None
) -> str:
    """Genereert een platte tekst response."""
    
    if not client:
        logger.error("❌ GPT Text Call gefaald: Geen OpenAI Client (Missing API Key)")
        return "De AI assistent is momenteel offline omdat de OpenAI API sleutel ontbreekt. Controleer je .env bestand."

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt}
    ]

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🧠 GPT Text Call (Attempt {attempt})")
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=TEXT_TEMP,
                max_tokens=max_tokens or MAX_TOKENS
            )

            content = response.choices[0].message.content
            if content:
                return content.strip()

        except Exception as e:
            logger.error(f"❌ OpenAI Text API Error (Attempt {attempt}): {e}")

            # 🔥 STOP bij quota errors
            if "insufficient_quota" in str(e):
                logger.error("❌ QUOTA bereikt → stop retries")
                return "AI quota bereikt"

            if attempt == retries:
                return f"⚠️ Er is een fout opgetreden bij de AI aanvraag: {str(e)}"

            time.sleep(1)

    return "Fout bij het genereren van de analyse."
# ============================================================
# 🌏 ASYNC WRAPPERS (To prevent blocking the event loop)
# ============================================================
async def ask_gpt_json_async(*args, **kwargs):
    return await asyncio.to_thread(ask_gpt_json, *args, **kwargs)

async def ask_gpt_text_async(*args, **kwargs):
    return await asyncio.to_thread(ask_gpt_text, *args, **kwargs)
