import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from backend.services.locale_config import (
    DEFAULT_LOCALE,
    LOCALE_TO_FINN_LANGUAGE,
    resolve_locale as resolve_supported_locale,
)
from backend.utils.openai_client import ask_gpt_text_async


_translation_cache: Dict[str, str] = {}

_DUTCH_TO_ENGLISH_REPLACEMENTS = [
    ("Voor de komende 24 tot 48 uur ligt de focus op", "For the next 24 to 48 hours, the focus is on"),
    ("Het dagrapport voor", "The daily report for"),
    ("opent in", "opens in"),
    ("met een marktpostuur dat nu kwetsbaar aanvoelt bij een 24-uurs verandering van", "with a market posture that currently feels fragile on a 24-hour move of"),
    ("Ten opzichte van gisteren verschoof de market score met", "Versus yesterday, the market score shifted by"),
    ("Ten opzichte van gisteren verschoof de macro score met", "Versus yesterday, the macro score shifted by"),
    ("Ten opzichte van gisteren verschoof de technical score met", "Versus yesterday, the technical score shifted by"),
    ("Binnen de watchlist trekt", "Within the watchlist,"),
    ("nu de meeste aandacht", "currently draws the most attention"),
    ("Er is geen harde regimebreuk zichtbaar", "There is no hard regime break visible"),
    ("waardoor bevestiging belangrijker blijft dan anticiperen", "so confirmation remains more important than anticipation"),
    ("De best bruikbare setup is nu", "The most usable setup right now is"),
    ("maar alleen zolang de interne bevestiging in de watchlist overeind blijft", "but only as long as the internal confirmation in the watchlist holds up"),
    ("Macro blijft vandaag kwetsbaar en ondersteunt daarmee", "Macro remains fragile today and therefore supports"),
    ("zonder al een nieuw risicoklimaat af te dwingen", "without already forcing a new risk climate"),
    ("Binnen de macro-laag springt", "Within the macro layer,"),
    ("eruit", "stands out"),
    ("Dat betekent dat", "That means"),
    ("de speelruimte voor agressie nog steeds afhangt van bevestiging op markt- en technieklaag, niet alleen van een macro-meewind", "the room for aggression still depends on confirmation from the market and technical layers, not only on macro tailwind"),
    ("Zolang macro niet duidelijk versnelt of verslechtert", "As long as macro does not clearly accelerate or deteriorate"),
    ("is de juiste lezing dat de markt vooral moet bewijzen dat de recente beweging meer is dan tijdelijke opluchting", "the correct read is that the market still has to prove the recent move is more than temporary relief"),
    ("met een setupscore van", "with a setup score of"),
    ("en een technische score van", "and a technical score of"),
    ("Zeer lage range", "Very low range"),
    ("Sentiment/conditie extreem zwak.", "Sentiment/condition extremely weak."),
    ("Sentiment/conditie extreem zwak..", "Sentiment/condition extremely weak."),
    ("Voor BTC: ik zou vandaag wachten;", "For BTC: I would wait today;"),
    ("je setup is nog niet actief volgens je eigen ranges", "your setup is not active yet according to your own ranges"),
    ("Setup:", "Setup:"),
    ("match", "match"),
    ("Blokkeert nu:", "Blocked now:"),
    ("Strategie vandaag:", "Strategy today:"),
    ("geen actieve DCA-strategie gevonden", "no active DCA strategy found"),
    ("Bot vandaag:", "Bot today:"),
    ("beslissing(en)", "decision(s)"),
    ("Data/indicator aandacht:", "Data/indicator focus:"),
    ("zwakke indicatoren", "weak indicators"),
    ("Agent-verdicts:", "Agent verdicts:"),
    ("Macro blokkeert: score", "Macro blocks: score"),
    ("Technical blokkeert: score", "Technical blocks: score"),
    ("Market blokkeert: score", "Market blocks: score"),
    ("buiten range", "outside range"),
    ("Setup blokkeert volgens je eigen ranges", "The setup is blocked by your own ranges"),
    ("Geen actieve strategie voor vandaag gevonden", "No active strategy found for today"),
    ("bot-decision(s) staan klaar", "bot decision(s) are ready"),
    ("eerst Risk Agent volgen", "follow the Risk Agent first"),
    ("Veilige volgende stap:", "Safe next step:"),
    ("Niet forceren: wacht tot de blocker-scores binnen je ranges vallen", "Do not force it: wait until the blocker scores move back inside your ranges"),
    ("Je kunt macro uitbreiden met", "You can expand macro with"),
    ("Controleer of de hoge weging bewust is voor technical", "Check whether the high weighting is intentional for technical"),
    ("Ik voer niets automatisch uit vanuit deze check; dit is advies-only.", "I am not executing anything automatically from this check; this is advice only."),
    ("punt", "point"),
]

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
        or DEFAULT_LOCALE
    )
    return resolve_supported_locale(locale)


def response_language_name(locale: str) -> str:
    return LOCALE_TO_FINN_LANGUAGE[resolve_locale({"locale": locale})]


def _rule_based_translate_to_english(text: str) -> str:
    translated = text
    for source, target in _DUTCH_TO_ENGLISH_REPLACEMENTS:
        translated = translated.replace(source, target)

    translated = re.sub(r"\bscore ([0-9.]+) valt buiten je range\b", r"score \1 falls outside your range", translated)
    translated = re.sub(r"score ([0-9.]+) moet binnen (\[[^\]]+\]) vallen", r"score \1 must be within \2", translated)
    translated = re.sub(r"Versus yesterday, the ([a-z]+) score shifted by ([+-]?[0-9.]+) point\b", r"Versus yesterday, the \1 score shifted by \2 points", translated)
    translated = re.sub(r"Versus yesterday, the market score shifted by ([+-]?[0-9.]+) point\b", r"Versus yesterday, the market score shifted by \1 points", translated)
    translated = re.sub(r"met een setupscore van ([0-9.]+) en een technische score van ([0-9.]+)", r"with a setup score of \1 and a technical score of \2", translated)
    translated = re.sub(r"Very low range \(([^)]+)\)\.", r"Very low range (\1).", translated)
    translated = re.sub(r"\.\.", ".", translated)
    translated = re.sub(r"\bGeen actieve strategie\b", "No active strategy", translated)
    translated = re.sub(r"\bgeen actieve\b", "no active", translated)
    translated = re.sub(r"\bgeen actieve .*? gevonden\b", lambda m: m.group(0).replace("geen actieve", "no active").replace("gevonden", "found"), translated)
    translated = translated.replace(" falls outside your range [", " falls outside your range [")
    translated = translated.replace("must be within [", "must be within [")
    return translated


async def translate_text_if_needed(text: Any, target_locale: str) -> Any:
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    normalized_locale = resolve_locale({"locale": target_locale})
    if not stripped or normalized_locale == DEFAULT_LOCALE:
        return text

    cache_key = hashlib.sha256(f"{normalized_locale}::{stripped}".encode("utf-8")).hexdigest()
    cached = _translation_cache.get(cache_key)
    if cached:
        return cached

    rule_based = _rule_based_translate_to_english(stripped) if normalized_locale == "en" else stripped
    if normalized_locale == "en" and rule_based != stripped and any(token in rule_based for token in ("The ", "For ", "Blocked", "Strategy", "Macro", "Safe next step", "Within the")):
        _translation_cache[cache_key] = rule_based
        return rule_based

    prompt = (
        f"Translate the following Tradamind/Finn trading product text from Dutch to natural {response_language_name(normalized_locale)}.\n"
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
            f"Translate Dutch UI and coaching text into concise natural {response_language_name(normalized_locale)}."
        ),
        max_tokens=1200,
    )
    if not isinstance(translated, str):
        return text
    translated = translated.strip()
    if not translated or translated in {"AI quota bereikt", "Gebruiker niet gevonden."}:
        return rule_based if rule_based != stripped else text

    _translation_cache[cache_key] = translated
    return translated


async def _translate_string_list(values: Iterable[Any], target_locale: str) -> list[Any]:
    translated: list[Any] = []
    for value in values:
        translated.append(await translate_text_if_needed(value, target_locale))
    return translated


async def localize_finn_payload(payload: Dict[str, Any], target_locale: str) -> Dict[str, Any]:
    locale = resolve_locale({"locale": target_locale})
    if locale == DEFAULT_LOCALE:
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
    if locale == DEFAULT_LOCALE:
        return payload

    localized = deepcopy(payload)
    for key in _REPORT_TEXT_KEYS:
        if key in localized:
            localized[key] = await translate_text_if_needed(localized.get(key), locale)

    if isinstance(localized.get("report"), dict):
        localized["report"] = await localize_report_payload(localized["report"], locale)

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
