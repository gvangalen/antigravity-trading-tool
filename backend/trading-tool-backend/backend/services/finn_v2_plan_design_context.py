"""Keep an exploratory new-plan discussion distinct from saved-plan reads."""

from __future__ import annotations

import re
from typing import Any


_NEW_SETUP = re.compile(
    r"\b(?:nieuwe?|new|neu(?:e|en|er|es)?|separate|aparte|losse|"
    r"independent)\b(?:\s+[\w-]+){0,2}\s+\b(?:setup|plan|opzet)\b|"
    r"\b(?:setup|plan|opzet)\b(?:\s+[\w-]+){0,2}\s+\b(?:nieuwe?|new|"
    r"neu(?:e|en|er|es)?|separate|aparte|independent)\b",
    re.I,
)
_SAVED_TOPIC = re.compile(
    r"\b(?:mijn|my|mein(?:e|en|er|es)?)\s+(?:opgeslagen|bestaande|saved|existing|"
    r"gespeicherte[nrms]?|bestehende[nrms]?)\s+(?:[\w-]+\s+){0,3}"
    r"(?:[\w]+-)?(?:setup|plan|strategie|strategy)\b",
    re.I,
)


def is_new_separate_setup_request(message: str) -> bool:
    return bool(_NEW_SETUP.search(str(message or "")))


def advance_plan_design_focus(context: dict[str, Any], message: str) -> bool:
    """Return whether the context changed; expire the focus after a short discussion."""
    before = context.get("plan_design_focus")
    if is_new_separate_setup_request(message):
        context["plan_design_focus"] = {"kind": "new_separate_setup", "turns_left": 8}
    elif _SAVED_TOPIC.search(message):
        context.pop("plan_design_focus", None)
    elif isinstance(before, dict):
        remaining = int(before.get("turns_left") or 0) - 1
        if remaining > 0:
            context["plan_design_focus"] = {"kind": before.get("kind"), "turns_left": remaining}
        else:
            context.pop("plan_design_focus", None)
    return context.get("plan_design_focus") != before


def remember_unsupported_ma_design(context: dict[str, Any]) -> bool:
    """A conceptual rule stays unsaved until the user chooses its parent scope."""
    before = context.get("plan_design_focus")
    if not isinstance(before, dict) or before.get("kind") != "new_separate_setup":
        context["plan_design_focus"] = {"kind": "unsaved_ma_dca_design", "turns_left": 8}
    return context.get("plan_design_focus") != before


def requests_unsupported_ma_dca_amount(message: str) -> bool:
    """Route the MA-distance amount design to capability facts, never an action card."""
    text = str(message or "")
    return bool(
        re.search(r"\b(?:ma\s*200|200\s*ma|200[-\s]*(?:daags(?:e)?|day|tage)[-\s]*(?:ma|average|gemiddelde))\b", text, re.I)
        and re.search(r"\b(?:dca|koop\w*|kopen|aankoop\w*|buy|purchase\w*)\b", text, re.I)
        and re.search(r"\b(?:afstand|distance|percentage\w*|procent\w*|bedrag\w*|amount\w*|meer|minder|more|less|lineair|linear)\b", text, re.I)
    )
