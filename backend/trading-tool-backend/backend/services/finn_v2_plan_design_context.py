"""Keep an exploratory new-plan discussion distinct from saved-plan reads."""

from __future__ import annotations

import re
from typing import Any

from backend.services.finn_v2_factual_source_answer import is_report_technical_comparison_request


_NEW_SETUP = re.compile(
    r"\b(?:nieuwe?|new|neu(?:e|en|er|es)?|separate|aparte|losse|"
    r"independent)\b(?:\s+[\w-]+){0,2}\s+\b(?:setup|plan|opzet)\b|"
    r"\b(?:setup|plan|opzet)\b(?:\s+[\w-]+){0,2}\s+\b(?:nieuwe?|new|"
    r"neu(?:e|en|er|es)?|separate|aparte|independent)\b",
    re.I,
)
_NEW_DESIGN = re.compile(
    r"\b(?:nieuwe?|new|neu(?:e|en|er|es)?)\b[\s,]+"
    r"(?:(?:aparte|separate|losse|independent|eigen)\b[\s,]+)?"
    r"(?:(?:[A-Z0-9]+(?:/[A-Z0-9]+)?|trade|trading|smart)\b[\s-]+){0,3}"
    r"(?:dca[\s-]+)?(?:setup|plan|opzet|idea|idee|concept)\b",
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
    r"\b(?:kan|kunnen|mogelijk|uitvoer\w*|automatiseer\w*|automatisch|"
    r"instel\w*|can|could|possible|execut\w*|support\w*|automat\w*|"
    r"configur\w*|kann|können|möglich|ausführ\w*|automatisier\w*|"
    r"einricht\w*)\b",
    re.I,
)
_DESIGN_SUBJECT = re.compile(
    r"\b(?:setup|plan|strategie|strategy|dca|regel\w*|rule\w*|"
    r"indicator\w*|score\w*|benchmark\w*|sma\d*|ma\d+|"
    r"kruising\w*|cross(?:over)?\w*|trendlijn\w*|trendline\w*|"
    r"koop\w*|kopen|aankoop\w*|"
    r"buy|sell|verkoop\w*|trade\w*|bedrag\w*|amount\w*|"
    r"kauf\w*|verkauf\w*|betrag\w*|linie\w*)\b",
    re.I,
)
_READ_ONLY_QUESTION = re.compile(
    r"\b(?:toelichten|uitleggen|teruglezen|voorlezen|summarize|explain|read back|"
    r"zusammenfassen|erklären|vorlesen|"
    r"(?:herhaal|repeat|wiederhole)\b.{0,50}\b(?:les|lesson|lektion))\b",
    re.I,
)
_CURRENT_EVIDENCE = re.compile(
    r"\b(?:actuele|huidige|nieuwste|laatste|current|latest|aktuelle[nr]?|letzte[nr]?)\b"
    r".{0,100}\b(?:score\w*|bronmoment\w*|indicator\w*|koers\w*|prijs\w*|"
    r"botbeslissing\w*|botbesluit\w*|portfolio|portefeuille|kas|cash|positie\w*|"
    r"source\w*|quote\w*|price\w*|decision\w*|quelle\w*|kurs\w*|"
    r"entscheidung\w*|position\w*)\b",
    re.I | re.S,
)
_EVIDENCE_READ_VERB = re.compile(
    r"\b(?:lees|lezen|ophalen|control\w*|check\w*|vergelijk\w*|beoordeel\w*|"
    r"read|fetch|check|compare|assess|verify|lese\w*|abruf\w*|prüf\w*|"
    r"vergleich\w*|bewert\w*)\b",
    re.I,
)
_DIRECT_ACTION_REQUEST = re.compile(
    r"\b(?:kan je|can you|kannst du)\b.{0,70}\b"
    r"(?:maken|aanmaken|wijzigen|aanpassen|hernoemen|opslaan|bevestigen|"
    r"create|change|update|rename|save|confirm|erstellen|ändern|umbenennen|speichern)\b",
    re.I,
)
_IMPERATIVE_ACTION_REQUEST = re.compile(
    r"^\s*(?:maak|creëer|bereid|wijzig|pas|hernoem|sla|verwijder|"
    r"create|prepare|change|update|rename|save|delete|"
    r"erstelle|bereite|ändere|benenne|speichere|lösche)\b",
    re.I,
)


def is_new_separate_setup_request(message: str) -> bool:
    text = str(message or "")
    return bool(_NEW_SETUP.search(text) or _NEW_DESIGN.search(text))


def supersedes_guided_setup(message: str, guided: dict[str, Any] | None) -> bool:
    """A mention of the *current* new concept is not another new concept.

    Guided setup slots survive read-only questions and requests to show the
    current proposal. An explicit asset change or a fresh differently named
    setup is a new parent and must still retire the old draft.
    """
    if not is_new_separate_setup_request(message):
        return False
    collected = dict((guided or {}).get("collected_inputs") or {})
    if not collected or (guided or {}).get("operation_id") != "create_setup":
        return True
    text = str(message or "")
    if re.search(r"\b(?:in plaats van|niet langer|instead of|rather than|statt|anstelle)\b", text, re.I):
        return True
    current_symbol = str(collected.get("symbol") or "").upper()
    from backend.services.asset_catalog_service import mentioned_catalog_symbols
    if any(symbol != current_symbol for symbol in mentioned_catalog_symbols(text)):
        return True
    current_name = str(collected.get("name") or "").casefold().strip()
    if current_name and re.search(r"\b(?:andere|tweede|another|second|andere|zweite)\s+(?:setup|plan|concept)\b", text, re.I):
        return True
    return False


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


def asks_read_only_impulse_plan_coaching(message: str) -> bool:
    """A buy impulse review needs saved owner facts, not plan-rule capability copy."""
    text = str(message or "")
    return bool(
        re.search(r"\b(?:FOMO|impulsief)\b", text, re.I)
        and re.search(r"\b(?:plan|setup)\b", text, re.I)
        and re.search(r"\b(?:bijkopen|kopen|aankoop|instapsignaal)\b", text, re.I)
        and re.search(
            r"\b(?:alleen coachen|niets voorstellen|niets.{0,20}uitvoeren|"
            r"zonder koopvoorstel|zonder uitvoering|leg uit zonder)\b",
            text, re.I,
        )
    )


def requests_execution_capability_question(message: str, context: dict[str, Any] | None = None) -> bool:
    """Route explicit feasibility questions through the executable contracts."""
    text = str(message or "")
    if asks_read_only_impulse_plan_coaching(text):
        return False
    if (
        re.search(r"\b(?:elk|ieder|per|each|every)\b", text, re.I)
        and re.search(r"\b(?:opgeslagen|bestaande|saved|existing)\b", text, re.I)
        and re.search(r"\b(?:plan\w*|setup\w*|opzet\w*)\b", text, re.I)
        and re.search(r"\b(?:controle\w*|check\w*|controleren|verify)\b", text, re.I)
        and re.search(r"\b(?:geen|zonder|no|without)\s+(?:wijziging|aanpassing|order|change|execution)\b", text, re.I)
    ):
        # Read-only checks for each saved plan need owner-scoped evidence.
        # The word "kan" in "kan ik mijn voorbereiding verbeteren?" is not
        # a question about whether a plan rule can execute automatically.
        return False
    if (re.search(r"\b(?:hoeveel|wat is|betekent)\b", text, re.I)
            and re.search(r"\bbotbudget\b", text, re.I)
            and re.search(r"\b(?:positie|posities|position|positions)\b", text, re.I)
            and re.search(r"\b(?:kas|kassaldo|cash|saldo)\b", text, re.I)):
        # "Can I buy more?" with position, cash and budget asks about
        # account capacity. It needs an owner-scoped portfolio read, not the
        # plan-rule capability explainer that runs before the Responses door.
        return False
    if is_report_technical_comparison_request(text):
        # "Wat kan Analyse lezen?" asks for owner-scoped measurements, not
        # whether a plan rule is executable. Let the factual read run first.
        return False
    if _CURRENT_EVIDENCE.search(text) and _EVIDENCE_READ_VERB.search(text):
        # "Can you check my current score and last bot decision?" asks for
        # owner-scoped facts. The words can/execute in a later no-action
        # sentence do not make it a question about executable plan rules.
        return False
    # A guided plan answer can contain words such as "uitvoering" and an
    # active design focus. Those words do not turn supplied fields into a
    # capability question, even when the answer spans several sentences.
    if "?" not in text and not re.match(
        r"^\s*(?:kan|kunnen|kann|können|can|could|is\s+het\s+mogelijk)\b",
        text, re.I,
    ):
        return False
    focus = (context or {}).get("plan_design_focus")
    active_design = isinstance(focus, dict) and focus.get("kind") in {
        "new_separate_setup", "unsaved_capability_design",
    }
    return bool(_CAPABILITY_QUESTION.search(text) and not _READ_ONLY_QUESTION.search(text)
    and not _DIRECT_ACTION_REQUEST.search(text) and not _IMPERATIVE_ACTION_REQUEST.search(text) and (
        _DESIGN_SUBJECT.search(text) or active_design
    ))


def asks_why_guided_signal_needs_entry(message: str, context: dict[str, Any] | None = None) -> bool:
    """Recognize a direct objection to the next required slot in a signal draft."""
    guided = (context or {}).get("active_guided_operation") or {}
    if not isinstance(guided, dict) or guided.get("operation_id") != "create_setup":
        return False
    inputs = guided.get("collected_inputs") or {}
    if not isinstance(inputs, dict) or not inputs.get("entry_signal"):
        return False
    # The user can ask about the entry requirement before reaching that slot.
    # Keep the active draft available instead of treating the question as a
    # failed answer to whichever field FINN happened to request first.
    text = str(message or "")
    return bool(
        re.search(r"\b(?:geen|zonder|no|without|kein\w*|ohne)\b", text, re.I)
        and re.search(r"\b(?:vaste?\s+)?(?:instapkoers|instapprijs|entry\s*price|einstiegskurs)\b", text, re.I)
        and re.search(r"\b(?:waarom|leg\s+uit|why|explain|warum|erkl[aä]r)\b", text, re.I)
    )
