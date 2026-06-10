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
QUOTA_COOLDOWN_SECONDS = int(os.getenv("OPENAI_QUOTA_COOLDOWN_SECONDS", "3600"))

_openai_runtime_state: Dict[str, Any] = {
    "quota_exhausted_until": 0.0,
    "quota_failures": 0,
    "blocked_calls": 0,
    "text_calls": 0,
    "json_calls": 0,
    "last_error": None,
    "last_error_at": None,
}


def _quota_breaker_active() -> bool:
    return float(_openai_runtime_state.get("quota_exhausted_until") or 0.0) > time.time()


def _mark_runtime_error(message: str) -> None:
    _openai_runtime_state["last_error"] = str(message)
    _openai_runtime_state["last_error_at"] = int(time.time())


def _mark_quota_exhausted() -> None:
    _openai_runtime_state["quota_failures"] = int(_openai_runtime_state.get("quota_failures") or 0) + 1
    _openai_runtime_state["quota_exhausted_until"] = time.time() + max(60, QUOTA_COOLDOWN_SECONDS)
    _mark_runtime_error("insufficient_quota")


def get_openai_runtime_status() -> Dict[str, Any]:
    exhausted_until = float(_openai_runtime_state.get("quota_exhausted_until") or 0.0)
    breaker_active = exhausted_until > time.time()
    remaining = int(max(0, exhausted_until - time.time())) if breaker_active else 0
    return {
        "configured": bool(api_key),
        "model": model,
        "quota_breaker_active": breaker_active,
        "quota_exhausted_until_epoch": int(exhausted_until) if exhausted_until else None,
        "quota_cooldown_remaining_seconds": remaining,
        "quota_failures": int(_openai_runtime_state.get("quota_failures") or 0),
        "blocked_calls": int(_openai_runtime_state.get("blocked_calls") or 0),
        "text_calls": int(_openai_runtime_state.get("text_calls") or 0),
        "json_calls": int(_openai_runtime_state.get("json_calls") or 0),
        "last_error": _openai_runtime_state.get("last_error"),
        "last_error_at_epoch": _openai_runtime_state.get("last_error_at"),
    }

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
    if _quota_breaker_active():
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        logger.warning("⛔ GPT JSON Call overgeslagen: quota breaker actief")
        return {"error": "quota"}

    _openai_runtime_state["json_calls"] = int(_openai_runtime_state.get("json_calls") or 0) + 1

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
            _mark_runtime_error(str(e))

            # 🔥 STOP bij quota errors
            if "insufficient_quota" in str(e):
                logger.error("❌ QUOTA bereikt → stop retries")
                _mark_quota_exhausted()
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
    if _quota_breaker_active():
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        logger.warning("⛔ GPT Text Call overgeslagen: quota breaker actief")
        return "AI quota bereikt"

    _openai_runtime_state["text_calls"] = int(_openai_runtime_state.get("text_calls") or 0) + 1

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
            _mark_runtime_error(str(e))

            # 🔥 STOP bij quota errors
            if "insufficient_quota" in str(e):
                logger.error("❌ QUOTA bereikt → stop retries")
                _mark_quota_exhausted()
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


def stream_gpt_json(
    *,
    prompt: str,
    system_role: str,
    max_tokens: Optional[int] = None
):
    """
    Initiates a streaming chat completion in JSON mode, yielding the raw OpenAI stream.
    """
    if not client:
        logger.error("❌ GPT Stream Call gefaald: Geen OpenAI Client")
        raise ValueError("AI is offline")

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt + "\n\nRETURN ONLY VALID JSON."}
    ]

    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=JSON_TEMP,
        max_tokens=max_tokens or MAX_TOKENS,
        response_format={"type": "json_object"},
        stream=True
    )
