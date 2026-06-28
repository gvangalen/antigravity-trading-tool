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


def response_language_name(value: Optional[str]) -> str:
    return LOCALE_TO_FINN_LANGUAGE[resolve_locale(value)]
