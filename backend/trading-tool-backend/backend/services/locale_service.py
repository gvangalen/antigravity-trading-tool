import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from backend.utils.openai_client import ask_gpt_text_async


_translation_cache: Dict[str, str] = {}

_FINN_TEXT_KEYS = {
    "response",
    "summary",
    "risk_summary",
    "next_best_action",
    "review_reason",
}

_REPORT_TEXT_KEYS = {
    "executive_summary",
    "market_analysis",
    "macro_context",
    "technical_analysis",
    "setup_validation",
    "strategy_implication",
    "bot_strategy",
    "outlook",
    "market_overview",
    "macro_trends",
    "technical_structure",
    "setup_performance",
    "bot_performance",
    "strategic_lessons",
    "summary",
    "recommended_action",
    "macro_summary",
    "technical_summary",
    "setup_summary",
    "bot_summary",
    "executive_summary_compact",
    "market_analysis_compact",
    "outlook_compact",
}


def resolve_locale(preferences: Optional[dict] = None, context: Optional[dict] = None) -> str:
    locale = (
        (preferences or {}).get("locale")
        or (context or {}).get("locale")
        or "nl"
    )
    locale = str(locale).strip().lower()
    return "en" if locale.startswith("en") else "nl"


def response_language_name(locale: str) -> str:
    return "English" if resolve_locale({"locale": locale}) == "en" else "Dutch"


async def translate_text_if_needed(text: Any, target_locale: str) -> Any:
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    if not stripped or resolve_locale({"locale": target_locale}) != "en":
        return text

    cache_key = hashlib.sha256(f"en::{stripped}".encode("utf-8")).hexdigest()
    cached = _translation_cache.get(cache_key)
    if cached:
        return cached

    prompt = (
        "Translate the following Tradamind/Finn trading product text from Dutch to natural English.\n"
        "Rules:\n"
        "- Keep the meaning exactly the same.\n"
        "- Keep bullet points, line breaks, numbers, ids, percentages, and asset tickers exactly intact.\n"
        "- Do not add explanation or commentary.\n"
        "- Return only the translated text.\n\n"
        f"{stripped}"
    )
    translated = await ask_gpt_text_async(
        prompt=prompt,
        system_role=(
            "You are a precise product copy translator for a trading app. "
            "Translate Dutch UI and coaching text into concise natural English."
        ),
        max_tokens=1200,
    )
    if not isinstance(translated, str):
        return text
    translated = translated.strip()
    if not translated or translated in {"AI quota bereikt", "Gebruiker niet gevonden."}:
        return text

    _translation_cache[cache_key] = translated
    return translated


async def _translate_string_list(values: Iterable[Any], target_locale: str) -> list[Any]:
    translated: list[Any] = []
    for value in values:
        translated.append(await translate_text_if_needed(value, target_locale))
    return translated


async def localize_finn_payload(payload: Dict[str, Any], target_locale: str) -> Dict[str, Any]:
    locale = resolve_locale({"locale": target_locale})
    if locale != "en":
        return payload

    localized = deepcopy(payload)
    for key in _FINN_TEXT_KEYS:
        if key in localized:
            localized[key] = await translate_text_if_needed(localized.get(key), locale)

    if isinstance(localized.get("suggested_actions"), list):
        localized["suggested_actions"] = await _translate_string_list(localized["suggested_actions"], locale)

    return localized


async def localize_report_payload(payload: Dict[str, Any], target_locale: str) -> Dict[str, Any]:
    locale = resolve_locale({"locale": target_locale})
    if locale != "en":
        return payload

    localized = deepcopy(payload)
    for key in _REPORT_TEXT_KEYS:
        if key in localized:
            localized[key] = await translate_text_if_needed(localized.get(key), locale)

    meta_json = localized.get("meta_json")
    if isinstance(meta_json, str):
        try:
            parsed = json.loads(meta_json)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            parsed = await localize_report_payload(parsed, locale)
            localized["meta_json"] = json.dumps(parsed, ensure_ascii=False)

    return localized
