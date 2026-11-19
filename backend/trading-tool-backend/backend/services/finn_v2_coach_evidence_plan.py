"""Source and answer coverage for a named, read-only coach question.

The plan identifies requested source domains; it never chooses an action or
substitutes user-stated values for owner-scoped reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CoachEvidencePlan:
    topics: tuple[str, ...]
    read_tools: tuple[str, ...]
    decision_required: bool = False
    next_step_required: bool = False


_TOPICS = (
    ("setup", r"\b(?:setup|plan|strategie|strategy|weging|voorwaarden|scoreband)\b",
     ("read_active_setup", "read_linked_strategy")),
    ("score", r"\b(?:score\w*|benchmark\w*|indicator\w*)\b",
     ("read_asset_scores",)),
    ("bot", r"\b(?:bot\w*|automatisering|automation)\b",
     ("read_bot_status", "read_review_history")),
    ("report", r"\b(?:dagrapport|ochtendrapport|rapport|report)\b",
     ("read_latest_report",)),
    ("quote", r"\b(?:koers\w*|prijs\w*|quote)\b",
     ("read_market_snapshot",)),
    ("portfolio", r"\b(?:positie\w*|portefeuille|portfolio|kas|cash|saldo)\b",
     ("read_portfolio",)),
)

_ANSWER_CUES = {
    "setup": r"\b(?:setup|plan|strategie|band|weging|voorwaard\w*)\b",
    "score": r"\b(?:\w*score\w*|benchmark\w*|indicator\w*)\b",
    "bot": r"\b(?:bot\w*|automatisering|voorstel|besluit|beslissing)\b",
    "report": r"\b(?:rapport|momentopname)\b",
    "quote": r"\b(?:koers\w*|prijs\w*|quote)\b",
    "portfolio": r"\b(?:positie\w*|portefeuille|portfolio|kas|cash|saldo)\b",
}


def coach_evidence_plan(message: str, *, named_asset_count: int, read_only: bool) -> CoachEvidencePlan | None:
    """Require a source bundle only for one explicitly named personal asset."""
    if not read_only or named_asset_count != 1 or not re.search(
        r"\b(?:mijn|mij|ik|me|my|our|ons|onze)\b", message, re.I,
    ):
        return None
    if len(set(re.findall(r"\b[A-Z]{2,10}/(?:EUR|USDT)\b", message, re.I))) > 1:
        return None
    chosen = [(name, tools) for name, pattern, tools in _TOPICS
              if re.search(pattern, message, re.I)]
    if len(chosen) < 2:
        return None
    topics = tuple(name for name, _ in chosen)
    reads = tuple(dict.fromkeys(tool for _, tools in chosen for tool in tools))
    return CoachEvidencePlan(
        topics=topics, read_tools=reads,
        decision_required="bot" in topics and bool(re.search(
            r"\b(?:besliss\w*|beoordel\w*|check\w*|blokkeer\w*|(?:bot)?reden\w*|waarom)\b",
            message, re.I,
        )),
        next_step_required=bool(re.search(
            r"\b(?:wat\s+(?:doe|moet|kan)\s+ik|vervolgstap|bij\s+(?:de\s+)?beursopening|"
            r"wat\s+nu|should\s+i\s+do|next\s+step)\b", message, re.I,
        )),
    )


def coach_answer_gap(plan: CoachEvidencePlan, answer: str) -> str | None:
    """Detect an omitted requested domain, including an explicit unavailable one."""
    for topic in plan.topics:
        if not re.search(_ANSWER_CUES[topic], answer, re.I):
            return f"coach_topic_missing:{topic}"
    if plan.decision_required and re.search(
        r"\b(?:reden|omdat|wegens|vanwege|door|geblokkeer\w*|blokkeer\w*)\b", answer, re.I,
    ) is None:
        return "coach_bot_decision_missing"
    if plan.next_step_required and re.search(
        r"\b(?:controleer|wacht|bekijk|herbeoordeel|verander|pas\s+aan|"
        r"doe|volgende\s+stap|bij\s+(?:de\s+)?beursopening|"
        r"check|wait|review|next\s+step)\b", answer, re.I,
    ) is None:
        return "coach_next_step_missing"
    return None
