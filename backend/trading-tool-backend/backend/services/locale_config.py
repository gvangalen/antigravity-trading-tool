import re
from typing import Optional

SUPPORTED_LOCALES = ("nl", "en", "de")
DEFAULT_LOCALE = "nl"
LOCALE_LABELS = {
    "nl": "Nederlands",
    "en": "English",
    "de": "Deutsch",
}
LOCALE_TO_FINN_LANGUAGE = {
    "nl": "Dutch",
    "en": "English",
    "de": "German",
}


def normalize_locale(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = str(value).strip().lower()
    direct_match = lowered.split("-", 1)[0].split("_", 1)[0]
    if lowered in SUPPORTED_LOCALES:
        return lowered
    if direct_match in SUPPORTED_LOCALES:
        return direct_match
    return None


def resolve_locale(value: Optional[str]) -> str:
    return normalize_locale(value) or DEFAULT_LOCALE


def resolve_chat_locale(
    preferred: Optional[str], message: str, *, conversation_locale: Optional[str] = None,
) -> str:
    """Use a conversation switch, then the saved preference, unless this turn switches."""
    base = normalize_locale(conversation_locale) or resolve_locale(preferred)
    lowered = message.casefold()
    requested = {
        "nl": r"(?:in|auf)\s+(?:het\s+)?(?:nederlands|dutch)",
        "en": r"(?:in|auf)\s+(?:het\s+)?(?:engels|english|englisch)",
        "de": r"(?:in|auf)\s+(?:het\s+)?(?:duits|german|deutsch)",
    }
    for locale, pattern in requested.items():
        if re.search(rf"\b{pattern}\b", lowered):
            return locale
    return base


def response_language_name(value: Optional[str]) -> str:
    return LOCALE_TO_FINN_LANGUAGE[resolve_locale(value)]
