"""Canonical, presentation-safe setup input normalization for FINN V2."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


class FinnV2SetupInputCatalog:
    """Normalize typed setup slots without changing the user's display values."""

    _TYPE_ALIASES = {
        "dca": ("dca", "dollar cost averaging", "periodiek bijkopen", "sparplan"),
        "position": ("position", "positie", "positioneel", "positionssetup", "position setup"),
        "trade": ("trade", "trading", "swing", "swingtrade", "swing trading", "scalp", "breakout", "momentum", "intraday"),
    }
    _TIMEFRAME_ALIASES = {
        "1D": ("dagbasis", "daily", "daily basis", "day basis", "tagesbasis", "taglich", "taeglich"),
        "1H": ("uurbasis", "hourly", "hour basis", "stundenbasis", "stundlich", "stuendlich"),
        "4H": ("4 uur", "vier uur", "four hours", "4 hours", "vier stunden", "4 stunden"),
        "12H": ("12 uur", "twaalf uur", "twelve hours", "12 hours", "zwolf stunden", "12 stunden"),
        "1W": ("weekbasis", "weekly", "week basis", "wochenbasis", "wochentlich", "woechentlich"),
    }
    _CODE_TIMEFRAME = re.compile(r"\b([1-9]\d*(?:m|h|d|w))\b", re.IGNORECASE)
    _COMPOUND_SETUP_SUFFIXES = (
        "opzet", "setup", "set-up", "strategie", "strategy", "einrichtung",
    )

    @classmethod
    def setup_type_from_text(cls, text: str) -> Optional[str]:
        lowered = cls._comparison_text(text)
        for canonical, aliases in cls._TYPE_ALIASES.items():
            if any(cls._has_setup_type_phrase(lowered, alias) for alias in aliases):
                return canonical
        return None

    @classmethod
    def canonical_setup_type(cls, value: object) -> Optional[str]:
        normalized = cls._comparison_text(value)
        for canonical, aliases in cls._TYPE_ALIASES.items():
            if normalized in aliases:
                return canonical
        # Selector telemetry can contain a descriptive phrase rather than a
        # bare enum. Use the same unambiguous catalog as user-supplied slots
        # so the response projection and collected inputs stay aligned.
        return cls.setup_type_from_text(str(value or ""))

    @classmethod
    def timeframe_from_text(cls, text: str) -> Optional[str]:
        match = cls._CODE_TIMEFRAME.search(str(text or ""))
        if match:
            return match.group(1).upper()
        lowered = cls._comparison_text(text)
        matches: set[str] = set()
        for canonical, aliases in cls._TIMEFRAME_ALIASES.items():
            if any(cls._has_phrase(lowered, alias) for alias in aliases):
                matches.add(canonical)
        matches.update(cls._compound_timeframes(lowered))
        return next(iter(matches)) if len(matches) == 1 else None

    @classmethod
    def canonical_timeframe(cls, value: object) -> Optional[str]:
        match = cls._CODE_TIMEFRAME.fullmatch(str(value or "").strip())
        if match:
            return match.group(1).upper()
        normalized = cls._comparison_text(value)
        for canonical, aliases in cls._TIMEFRAME_ALIASES.items():
            if normalized in aliases:
                return canonical
        return cls.timeframe_from_text(str(value or ""))

    @classmethod
    def canonical_input(cls, field: str, value: object) -> object:
        if field == "setup_type":
            return cls.canonical_setup_type(value) or value
        if field == "timeframe":
            return cls.canonical_timeframe(value) or value
        if field == "name":
            return cls.display_name(value) or value
        return value

    @staticmethod
    def display_name(value: object) -> Optional[str]:
        """Trim delimiters only; presentation casing and spacing stay intact."""
        if not isinstance(value, str):
            return None
        name = value.strip().strip("\"'").strip()
        return name or None

    @staticmethod
    def _comparison_text(value: object) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        return re.sub(r"\s+", " ", text.casefold()).strip()

    @classmethod
    def _compound_timeframes(cls, text: str) -> set[str]:
        patterns = {
            "1H": r"(?:(?:1|een|one)[\s-]?(?:uur|hour|stund(?:e|en))(?:s)?|(?:uur|hour|stund(?:e|en))(?:s)?[\s-]?(?:grafiek|chart))",
            "4H": r"(?:4|vier|four)[\s-]?(?:uur|hour|stund(?:e|en))(?:s)?(?:[\s-]?(?:grafiek|chart))?",
            "12H": r"(?:12|twaalf|twelve|zwolf)[\s-]?(?:uur|hour|stund(?:e|en))(?:s)?(?:[\s-]?(?:grafiek|chart))?",
            "1D": r"(?:(?:1|een|one)[\s-]?)?(?:dag|day|tag)(?:en)?(?:[\s-]?(?:grafiek|chart))?",
            "1W": r"(?:(?:1|een|one)[\s-]?)?(?:week|woche)(?:n)?(?:[\s-]?(?:grafiek|chart))?",
        }
        return {
            canonical for canonical, pattern in patterns.items()
            if re.search(r"(?<![\w-])" + pattern + r"(?!\w)", text)
        }

    @staticmethod
    def _has_phrase(text: str, phrase: str) -> bool:
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None

    @classmethod
    def _has_setup_type_phrase(cls, text: str, phrase: str) -> bool:
        if cls._has_phrase(text, phrase):
            return True
        suffixes = "|".join(re.escape(suffix) for suffix in cls._COMPOUND_SETUP_SUFFIXES)
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?:-|\s)?(?:" + suffixes + r")(?!\w)"
        return re.search(pattern, text) is not None
