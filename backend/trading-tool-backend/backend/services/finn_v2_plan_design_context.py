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
_SAVED_READ = re.compile(
    r"\b(?:wat|welk\w*|hoe|lees|toon|vertel|beschrijf|what|which|read|show|"
    r"was|wie|zeig|lies)\b.*\b(?:opgeslagen|bestaande|oude|eerdere|saved|"
    r"existing|old|previous|gespeichert\w*|bestehend\w*)\b.*\b"
    r"(?:setup|plan|strategie|strategy|ritme|bedrag|cadence|amount)\b",
    re.I | re.S,
)
_CAPABILITY_QUESTION = re.compile(
    r"\b(?:kan dat|kan dit|kan\b(?=[^?]{0,100}\b(?:met|via|op basis|"
    r"afhankelijk|automatisch|uitvoeren|activeren|volgens|onder|boven)\b)|"
    r"kunnen we|is dat mogelijk|is dit mogelijk|"
    r"werkt dat|werkt dit|uitvoerbaar|automatiseren|automatisch|"
    r"can (?:we|you|it|this)|is (?:that|this|it) possible|supported|"
    r"does (?:it|this) work|kann (?:man|ich|das)|geht das|automatisieren)\b",
    re.I,
)
_DESIGN_SUBJECT = re.compile(
    r"\b(?:setup|plan|strategie|strategy|dca|regel\w*|rule\w*|"
    r"indicator\w*|score\w*|benchmark\w*|koop\w*|kopen|aankoop\w*|"
    r"buy|sell|verkoop\w*|trade\w*|bedrag\w*|amount\w*)\b",
    re.I,
)


def is_new_separate_setup_request(message: str) -> bool:
    return bool(_NEW_SETUP.search(str(message or "")))


def advance_plan_design_focus(context: dict[str, Any], message: str) -> bool:
    """Return whether the context changed; expire the focus after a short discussion."""
    before = context.get("plan_design_focus")
    if is_new_separate_setup_request(message):
        context["plan_design_focus"] = {"kind": "new_separate_setup", "turns_left": 8}
    elif is_explicit_saved_plan_read(message):
        context.pop("plan_design_focus", None)
    elif isinstance(before, dict):
        remaining = int(before.get("turns_left") or 0) - 1
        if remaining > 0:
            context["plan_design_focus"] = {"kind": before.get("kind"), "turns_left": remaining}
        else:
            context.pop("plan_design_focus", None)
    return context.get("plan_design_focus") != before


def is_explicit_saved_plan_read(message: str) -> bool:
    return bool(_SAVED_TOPIC.search(str(message or "")) or _SAVED_READ.search(str(message or "")))


def remember_unsaved_design(context: dict[str, Any]) -> bool:
    """An exploratory rule stays unsaved until the user chooses its parent scope."""
    before = context.get("plan_design_focus")
    if not isinstance(before, dict) or before.get("kind") != "new_separate_setup":
        context["plan_design_focus"] = {"kind": "unsaved_capability_design", "turns_left": 8}
    return context.get("plan_design_focus") != before


def requests_execution_capability_question(message: str, context: dict[str, Any] | None = None) -> bool:
    """Route explicit feasibility questions through the executable contracts."""
    text = str(message or "")
    focus = (context or {}).get("plan_design_focus")
    active_design = isinstance(focus, dict) and focus.get("kind") in {
        "new_separate_setup", "unsaved_capability_design",
    }
    return bool(_CAPABILITY_QUESTION.search(text) and (
        _DESIGN_SUBJECT.search(text) or active_design
    ) and not re.search(r"\b(?:kan je|can you|kannst du)\b.{0,30}\b(?:maken|aanmaken|create|erstellen)\b", text, re.I))
