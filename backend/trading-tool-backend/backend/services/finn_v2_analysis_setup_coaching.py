"""User-facing next step for a verified analysis card and saved setup inventory."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _score(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and 0 <= number <= 100 else None


def _display(value: Decimal, language: str) -> str:
    rendered = format(value.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")
    return rendered.replace(".", ",") if language in {"nl", "de"} else rendered


def render_analysis_setup_coaching(
    *, subject: str, matching: list[dict], scored: dict, language: str,
) -> str:
    """Never infer a score target where the user has not saved one."""
    language = language if language in {"en", "de"} else "nl"
    current = _score(scored.get("benchmark_score")) if scored.get("source_status") == "available" else None
    if not matching:
        context = {
            "nl": (f"De analyse voor {subject} is bruikbaar. De benchmark staat op {_display(current, language)}/100. "
                   if current is not None else f"Voor {subject} is er nu geen complete benchmarkscore. "),
            "en": (f"The analysis for {subject} is ready. The benchmark is {_display(current, language)}/100. "
                   if current is not None else f"A complete benchmark score for {subject} is not available now. "),
            "de": (f"Die Analyse für {subject} ist bereit. Der Benchmarkwert liegt bei {_display(current, language)}/100. "
                   if current is not None else f"Für {subject} ist derzeit kein vollständiger Benchmarkwert verfügbar. "),
        }[language]
        next_step = {
            "nl": "Je kunt nu een plan voorbereiden. Mijn startpunt is een swing-setup op de daggrafiek met een scorezone, instapvoorwaarde, risicogrens en exit. Een positie-setup voor langer aanhouden of een DCA-setup voor gespreid opbouwen kan ook. Wil je korter handelen, langer vasthouden of gespreid opbouwen? Dan werk ik die keuze uit als bewerkbaar voorstel. Er is nog niets opgeslagen.",
            "en": "You can prepare a plan now. I would start with a daily swing setup with a score range, entry condition, risk limit and exit. A longer-term position setup or a DCA setup for gradual buying are also possible. Do you want to trade over a shorter period, hold longer, or build gradually? I can prepare an editable proposal. Nothing has been saved.",
            "de": "Du kannst jetzt einen Plan vorbereiten. Mein Ausgangspunkt ist ein Swing-Setup im Tageschart mit Scorebereich, Einstiegsbedingung, Risikogrenze und Ausstieg. Ein längerfristiges Positions-Setup oder ein DCA-Setup zum schrittweisen Aufbau sind ebenfalls möglich. Möchtest du kürzer handeln, länger halten oder schrittweise aufbauen? Dann bereite ich einen bearbeitbaren Entwurf vor. Es wurde nichts gespeichert.",
        }[language]
        return context + next_step
    if len(matching) != 1:
        return {
            "nl": f"Voor {subject} zie ik {len(matching)} opgeslagen setups. Welke wil je met de huidige analyse vergelijken? Dan laat ik zien hoe ver de score van de gekozen scorezone af zit. Ik heb niets gewijzigd.",
            "en": f"I found {len(matching)} saved setups for {subject}. Which one should I compare with the current analysis? I can then show how far the score is from its saved range. I have changed nothing.",
            "de": f"Für {subject} gibt es {len(matching)} gespeicherte Setups. Welches soll ich mit der aktuellen Analyse vergleichen? Dann zeige ich den Abstand zum gespeicherten Scorebereich. Ich habe nichts geändert.",
        }[language]
    setup = matching[0]
    lower, upper = _score(setup.get("min_benchmark_score")), _score(setup.get("max_benchmark_score"))
    if (lower is None and setup.get("min_benchmark_score") is not None or
            upper is None and setup.get("max_benchmark_score") is not None or
            lower is not None and upper is not None and lower > upper):
        lower = upper = None
    if current is None or lower is None and upper is None:
        return {
            "nl": f"Voor {subject} is er een opgeslagen setup. Ik kan de afstand tot een scoregrens nu niet berekenen. Zal ik de setup en de gewenste scorezone met je doornemen? Ik heb niets gewijzigd.",
            "en": f"There is a saved setup for {subject}. I cannot calculate the distance to a score threshold right now. Shall I review the setup and your preferred score range with you? I have changed nothing.",
            "de": f"Für {subject} gibt es ein gespeichertes Setup. Den Abstand zu einer Scoregrenze kann ich derzeit nicht berechnen. Soll ich das Setup und deinen gewünschten Scorebereich mit dir durchgehen? Ich habe nichts geändert.",
        }[language]
    score_text = _display(current, language)
    if lower is not None and current < lower:
        boundary, distance, relation = lower, lower - current, "below"
    elif upper is not None and current > upper:
        boundary, distance, relation = upper, current - upper, "above"
    else:
        boundary = distance = None
        relation = "inside"
    if relation == "inside":
        progress = {
            "nl": f"De benchmark voor {subject} staat op {score_text}/100, binnen de opgeslagen scorezone van je setup.",
            "en": f"The benchmark for {subject} is {score_text}/100, within your setup's saved score range.",
            "de": f"Der Benchmarkwert für {subject} liegt bei {score_text}/100, innerhalb des gespeicherten Scorebereichs deines Setups.",
        }[language]
    else:
        difference = _display(distance, language)
        limit = _display(boundary, language)
        progress = {
            "nl": f"De benchmark voor {subject} staat op {score_text}/100: {difference} punten {'onder de ondergrens' if relation == 'below' else 'boven de bovengrens'} van {limit} in je opgeslagen setup.",
            "en": f"The benchmark for {subject} is {score_text}/100: {difference} points {'below the lower threshold' if relation == 'below' else 'above the upper threshold'} of {limit} in your saved setup.",
            "de": f"Der Benchmarkwert für {subject} liegt bei {score_text}/100: {difference} Punkte {'unter der Untergrenze' if relation == 'below' else 'über der Obergrenze'} von {limit} in deinem gespeicherten Setup.",
        }[language]
    action = {
        "nl": " Zodra de score binnen je gekozen zone valt, kunnen we de opgeslagen instapvoorwaarde, risicogrens en exit controleren. Zal ik die voorwaarden nu alvast met je doornemen? Ik heb niets gewijzigd.",
        "en": " When the score enters your chosen range, we can check the saved entry condition, risk limit and exit. Shall I review those conditions with you now? I have changed nothing.",
        "de": " Sobald der Wert deinen gewählten Bereich erreicht, können wir die gespeicherte Einstiegsbedingung, Risikogrenze und den Ausstieg prüfen. Soll ich diese Bedingungen jetzt mit dir durchgehen? Ich habe nichts geändert.",
    }[language]
    return progress + action
