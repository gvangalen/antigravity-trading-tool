import hashlib
import asyncio
import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from backend.services.locale_config import (
    DEFAULT_LOCALE,
    LOCALE_TO_FINN_LANGUAGE,
    resolve_locale as resolve_supported_locale,
)
from backend.services.ai_usage_observability_service import ai_usage_context
from backend.utils.openai_client import ask_gpt_text_async


_translation_cache: Dict[str, str] = {}
_payload_translation_cache: Dict[str, Dict[str, Any]] = {}
_translation_inflight: Dict[str, "asyncio.Future[Any]"] = {}
_LOCAL_RULE_BASED_LOCALES = {"nl", "en", "de"}

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

_ENGLISH_TO_DUTCH_REPLACEMENTS = [
    ("Expansion Regime", "Expansieregime"),
    ("Recovery Phase", "Herstelfase"),
    ("Stagflation Risk", "Stagflatierisico"),
    ("Contraction Regime", "Contractieregime"),
    ("Aggressive Growth", "Agressieve groei"),
    ("Constructive Alignment", "Constructieve alignering"),
    ("Cautious Stance", "Voorzichtige houding"),
    ("Defensive Posture", "Defensieve houding"),
    ("Severe Contraction", "Zware contractie"),
    ("Bullish Structure", "Bullish structuur"),
    ("Neutral Structure", "Neutrale structuur"),
    ("Weak Structure", "Zwakke structuur"),
    ("Strong Upward Bias", "Sterke opwaartse bias"),
    ("Positive Divergence", "Positieve divergentie"),
    ("Neutral / Sideways", "Neutraal / zijwaarts"),
    ("Downward Pressure", "Neerwaartse druk"),
    ("Momentum Rising", "Momentum neemt toe"),
    ("Compression", "Compressie"),
    ("Rangebound", "Rangebound"),
    ("Expansion", "Expansie"),
    ("Premium Liquidity", "Premium liquiditeit"),
    ("Standard Volume", "Standaard volume"),
    ("Thin Orderbooks", "Dunne orderboeken"),
    ("Capital Flight", "Kapitaalvlucht"),
    ("Risk Elevated", "Risico verhoogd"),
    ("AI Confidence", "AI-vertrouwen"),
    ("Entry", "Instap"),
    ("Targets", "Doelen"),
    ("Stop Loss", "Stop-loss"),
    ("Risk Level", "Risiconiveau"),
    ("Medium", "Gemiddeld"),
    ("No specific signals", "Geen specifieke signalen"),
    ("Master snippet", "Master-snippet"),
    ("Live", "Live"),
]

_DUTCH_TO_GERMAN_REPLACEMENTS = [
    ("Voor de komende 24 tot 48 uur ligt de focus op", "In den naechsten 24 bis 48 Stunden liegt der Fokus auf"),
    ("Het dagrapport voor", "Der Tagesbericht fuer"),
    ("opent in", "eroeffnet in"),
    ("met een marktpostuur dat nu kwetsbaar aanvoelt bij een 24-uurs verandering van", "mit einer Marktstruktur, die bei einer 24-Stunden-Veraenderung von aktuell fragil wirkt"),
    ("Ten opzichte van gisteren verschoof de market score met", "Gegenueber gestern verschob sich der Markt-Score um"),
    ("Ten opzichte van gisteren verschoof de macro score met", "Gegenueber gestern verschob sich der Makro-Score um"),
    ("Ten opzichte van gisteren verschoof de technical score met", "Gegenueber gestern verschob sich der Technical-Score um"),
    ("Binnen de watchlist trekt", "Innerhalb der Watchlist zieht"),
    ("nu de meeste aandacht", "aktuell die meiste Aufmerksamkeit auf sich"),
    ("Er is geen harde regimebreuk zichtbaar", "Es ist kein harter Regimebruch sichtbar"),
    ("waardoor bevestiging belangrijker blijft dan anticiperen", "wodurch Bestaetigung wichtiger bleibt als Antizipation"),
    ("De best bruikbare setup is nu", "Das aktuell am besten nutzbare Setup ist"),
    ("Maar alleen zolang de interne bevestiging in de watchlist overeind blijft", "aber nur solange die interne Bestaetigung in der Watchlist intakt bleibt"),
    ("Macro blijft vandaag kwetsbaar en ondersteunt daarmee", "Makro bleibt heute fragil und unterstuetzt damit"),
    ("zonder al een nieuw risicoklimaat af te dwingen", "ohne bereits ein neues Risikoklima zu erzwingen"),
    ("Dat betekent dat", "Das bedeutet, dass"),
    ("Voor BTC: ik zou vandaag wachten;", "Fuer BTC: Ich wuerde heute warten;"),
    ("je setup is nog niet actief volgens je eigen ranges", "dein Setup ist gemaess deinen eigenen Bereichen noch nicht aktiv"),
    ("Veilige volgende stap:", "Sicherer naechster Schritt:"),
    ("Niet forceren: wacht tot de blocker-scores binnen je ranges vallen", "Nichts erzwingen: warte, bis die Blocker-Scores wieder innerhalb deiner Bereiche liegen"),
    ("Je kunt macro uitbreiden met", "Du kannst Makro erweitern mit"),
    ("Controleer of de hoge weging bewust is voor technical", "Pruefe, ob die hohe Gewichtung fuer Technical bewusst gesetzt ist"),
]

_GERMAN_TO_DUTCH_REPLACEMENTS = [
    ("Sicherer naechster Schritt:", "Veilige volgende stap:"),
    ("Nichts erzwingen: warte, bis die Blocker-Scores wieder innerhalb deiner Bereiche liegen", "Niet forceren: wacht tot de blocker-scores binnen je ranges vallen"),
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

_NON_TRANSLATABLE_PATTERN = re.compile(r"^[A-Z0-9_:/.\-\[\]%+ ]{2,}$")


def resolve_locale(preferences: Optional[dict] = None, context: Optional[dict] = None) -> str:
    locale = (
        (preferences or {}).get("locale")
        or (context or {}).get("locale")
        or DEFAULT_LOCALE
    )
    return resolve_supported_locale(locale)


def response_language_name(locale: str) -> str:
    normalized = _requested_locale_code(locale)
    if normalized in LOCALE_TO_FINN_LANGUAGE:
        return LOCALE_TO_FINN_LANGUAGE[normalized]
    locale_value = str(locale or "").strip()
    return locale_value or LOCALE_TO_FINN_LANGUAGE[DEFAULT_LOCALE]


def resolve_request_locale(
    header_locale: Optional[str] = None,
    preferences: Optional[dict] = None,
    context: Optional[dict] = None,
) -> str:
    locale = (
        header_locale
        or (preferences or {}).get("locale")
        or (context or {}).get("locale")
        or DEFAULT_LOCALE
    )
    return resolve_supported_locale(locale)


def _requested_locale_code(value: Optional[str]) -> str:
    raw = str(value or DEFAULT_LOCALE).strip().lower()
    base = raw.split("-", 1)[0].split("_", 1)[0]
    if base in _LOCAL_RULE_BASED_LOCALES:
        return base
    if raw:
        return base or raw
    return DEFAULT_LOCALE


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


def _rule_based_translate_to_dutch(text: str) -> str:
    translated = text
    for source, target in _ENGLISH_TO_DUTCH_REPLACEMENTS:
        translated = translated.replace(source, target)

    translated = re.sub(r"\bVery low range\b", "Zeer lage range", translated)
    translated = re.sub(r"\bThe daily report for\b", "Het dagrapport voor", translated)
    translated = re.sub(r"\bFor the next 24 to 48 hours, the focus is on\b", "Voor de komende 24 tot 48 uur ligt de focus op", translated)
    translated = re.sub(r"\bNo active strategy found for today\b", "Geen actieve strategie voor vandaag gevonden", translated)
    translated = re.sub(r"\bDo not force it: wait until the blocker scores move back inside your ranges\b", "Niet forceren: wacht tot de blocker-scores binnen je ranges vallen", translated)
    translated = re.sub(r"\bSafe next step:\b", "Veilige volgende stap:", translated)
    return translated


def _rule_based_translate_to_german(text: str) -> str:
    translated = text
    for source, target in _DUTCH_TO_GERMAN_REPLACEMENTS:
        translated = translated.replace(source, target)

    translated = re.sub(r"\bscore ([0-9.]+) valt buiten je range\b", r"Score \1 liegt ausserhalb deines Bereichs", translated)
    translated = re.sub(r"score ([0-9.]+) moet binnen (\[[^\]]+\]) vallen", r"Score \1 muss innerhalb von \2 liegen", translated)
    translated = re.sub(r"Gegenueber gestern verschob sich der ([A-Za-z-]+) score um ([+-]?[0-9.]+) point\b", r"Gegenueber gestern verschob sich der \1-Score um \2 Punkte", translated)
    translated = re.sub(r"Gegenueber gestern verschob sich der Markt-Score um ([+-]?[0-9.]+) point\b", r"Gegenueber gestern verschob sich der Markt-Score um \1 Punkte", translated)
    translated = re.sub(r"mit een setupscore van ([0-9.]+) en een technische score van ([0-9.]+)", r"mit einem Setup-Score von \1 und einem Technical-Score von \2", translated)
    translated = re.sub(r"\.\.", ".", translated)
    return translated


def _rule_based_translate(text: str, target_locale: str) -> str:
    if target_locale == "en":
        return _rule_based_translate_to_english(text)
    if target_locale == "de":
        return _rule_based_translate_to_german(text)
    if target_locale == "nl":
        intermediate = _rule_based_translate_to_dutch(text)
        for source, target in _GERMAN_TO_DUTCH_REPLACEMENTS:
            intermediate = intermediate.replace(source, target)
        return intermediate
    return text


def _translation_cache_key(text: str, target_locale: str) -> str:
    return hashlib.sha256(f"{target_locale}::{text}".encode("utf-8")).hexdigest()


def _payload_translation_cache_key(payload: Dict[str, Any], target_locale: str) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"payload::{target_locale}::{serialized}".encode("utf-8")).hexdigest()


async def _translate_payload_once_with_ai(payload: Dict[str, Any], target_locale: str) -> Dict[str, Any]:
    prompt = (
        f"Translate the following Tradamind/Finn JSON payload into natural {response_language_name(target_locale)}.\n"
        "Rules:\n"
        "- Preserve the exact JSON structure and keys.\n"
        "- Translate only user-facing string values.\n"
        "- Keep ids, tickers, numbers, percentages, and line breaks intact.\n"
        "- Return only valid JSON.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )
    with ai_usage_context(
        user_id=None,
        purpose="locale_translation_bundle",
        symbol="GLOBAL",
        request_source="system",
        run_kind="interactive",
        entry_point="locale_service:translate_payload_bundle",
        caller_tag="locale_service:translate_payload_bundle",
        completion_status="success",
        locale=target_locale,
    ):
        translated = await ask_gpt_text_async(
            prompt=prompt,
            system_role=(
                "You are a precise product copy translator for a trading app. "
                f"Translate JSON string values into concise natural {response_language_name(target_locale)}."
            ),
            max_tokens=2400,
            retries=1,
            client_max_retries=0,
        )
    if not isinstance(translated, str):
        return payload
    translated = translated.strip()
    if not translated or translated in {"AI quota bereikt", "Gebruiker niet gevonden."}:
        return payload
    try:
        parsed = json.loads(translated)
    except Exception:
        return payload
    return parsed if isinstance(parsed, dict) else payload


async def _translate_payload_once_with_ai_singleflight(payload: Dict[str, Any], target_locale: str) -> Dict[str, Any]:
    cache_key = _payload_translation_cache_key(payload, target_locale)
    cached = _payload_translation_cache.get(cache_key)
    if cached is not None:
        return deepcopy(cached)

    inflight = _translation_inflight.get(cache_key)
    if inflight is not None:
        result = await inflight
        return deepcopy(result)

    loop = asyncio.get_running_loop()
    future: "asyncio.Future[Any]" = loop.create_future()
    _translation_inflight[cache_key] = future
    try:
        translated = await _translate_payload_once_with_ai(payload, target_locale)
        _payload_translation_cache[cache_key] = deepcopy(translated)
        future.set_result(deepcopy(translated))
        return deepcopy(translated)
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        _translation_inflight.pop(cache_key, None)


async def translate_text_if_needed(text: Any, target_locale: str, *, allow_ai_translation: bool = True) -> Any:
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    normalized_locale = _requested_locale_code(target_locale)
    if not stripped:
        return text
    if _NON_TRANSLATABLE_PATTERN.match(stripped):
        return text

    cache_key = _translation_cache_key(stripped, normalized_locale)
    cached = _translation_cache.get(cache_key)
    if cached:
        return cached

    rule_based = _rule_based_translate(stripped, normalized_locale)
    if normalized_locale in _LOCAL_RULE_BASED_LOCALES:
        _translation_cache[cache_key] = rule_based
        return rule_based

    if normalized_locale == DEFAULT_LOCALE or not allow_ai_translation:
        return text

    prompt = (
        f"Translate the following Tradamind/Finn trading product text into natural {response_language_name(normalized_locale)}.\n"
        "Rules:\n"
        "- Keep the meaning exactly the same.\n"
        "- Keep bullet points, line breaks, numbers, ids, percentages, and asset tickers exactly intact.\n"
        "- Do not add explanation or commentary.\n"
        "- Return only the translated text.\n\n"
        f"{stripped}"
    )
    with ai_usage_context(
        user_id=None,
        purpose="locale_translation",
        symbol="GLOBAL",
        request_source="system",
        run_kind="interactive",
        entry_point="locale_service:translate_text_if_needed",
        caller_tag="locale_service:translate_text_if_needed",
        completion_status="success",
        locale=normalized_locale,
    ):
        translated = await ask_gpt_text_async(
            prompt=prompt,
            system_role=(
                "You are a precise product copy translator for a trading app. "
                f"Translate Dutch UI and coaching text into concise natural {response_language_name(normalized_locale)}."
            ),
            max_tokens=1200,
            retries=1,
            client_max_retries=0,
        )
    if not isinstance(translated, str):
        return text
    translated = translated.strip()
    if not translated or translated in {"AI quota bereikt", "Gebruiker niet gevonden."}:
        return rule_based if rule_based != stripped else text

    _translation_cache[cache_key] = translated
    return translated


async def localize_generic_payload(payload: Any, target_locale: str) -> Any:
    locale = _requested_locale_code(target_locale)

    if isinstance(payload, dict):
        localized = {}
        for key, value in payload.items():
            localized[key] = await localize_generic_payload(value, locale)
        return localized

    if isinstance(payload, list):
        return [await localize_generic_payload(value, locale) for value in payload]

    return await translate_text_if_needed(payload, locale, allow_ai_translation=locale not in _LOCAL_RULE_BASED_LOCALES)


async def _translate_string_list(values: Iterable[Any], target_locale: str, *, allow_ai_translation: bool = True) -> list[Any]:
    translated: list[Any] = []
    for value in values:
        translated.append(await translate_text_if_needed(value, target_locale, allow_ai_translation=allow_ai_translation))
    return translated


async def localize_finn_payload(
    payload: Dict[str, Any],
    target_locale: str,
    *,
    allow_ai_translation: bool = True,
) -> Dict[str, Any]:
    locale = _requested_locale_code(target_locale)
    if locale == DEFAULT_LOCALE:
        return payload

    if locale not in _LOCAL_RULE_BASED_LOCALES and allow_ai_translation:
        ai_payload = {
            key: payload.get(key)
            for key in _FINN_TEXT_KEYS
            if key in payload and isinstance(payload.get(key), str) and payload.get(key)
        }
        if isinstance(payload.get("suggested_actions"), list):
            ai_payload["suggested_actions"] = payload.get("suggested_actions") or []
        if ai_payload:
            translated_fields = await _translate_payload_once_with_ai_singleflight(ai_payload, locale)
            localized = deepcopy(payload)
            for key, value in translated_fields.items():
                localized[key] = value
            return localized

    localized = deepcopy(payload)
    for key in _FINN_TEXT_KEYS:
        if key in localized:
            localized[key] = await translate_text_if_needed(localized.get(key), locale, allow_ai_translation=False)

    if isinstance(localized.get("suggested_actions"), list):
        localized["suggested_actions"] = await _translate_string_list(
            localized["suggested_actions"],
            locale,
            allow_ai_translation=False,
        )

    return localized


async def localize_report_payload(
    payload: Dict[str, Any],
    target_locale: str,
    *,
    allow_ai_translation: bool = True,
) -> Dict[str, Any]:
    locale = _requested_locale_code(target_locale)
    if locale == DEFAULT_LOCALE:
        return payload

    if locale not in _LOCAL_RULE_BASED_LOCALES and allow_ai_translation:
        ai_payload = {
            key: payload.get(key)
            for key in _REPORT_TEXT_KEYS
            if key in payload and isinstance(payload.get(key), str) and payload.get(key)
        }
        meta_json = payload.get("meta_json")
        if isinstance(meta_json, str):
            ai_payload["meta_json"] = meta_json
        if ai_payload:
            translated_fields = await _translate_payload_once_with_ai_singleflight(ai_payload, locale)
            localized = deepcopy(payload)
            for key, value in translated_fields.items():
                localized[key] = value
            return localized

    localized = deepcopy(payload)
    for key in _REPORT_TEXT_KEYS:
        if key in localized:
            localized[key] = await translate_text_if_needed(localized.get(key), locale, allow_ai_translation=False)

    if isinstance(localized.get("report"), dict):
        localized["report"] = await localize_report_payload(
            localized["report"],
            locale,
            allow_ai_translation=False,
        )

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
