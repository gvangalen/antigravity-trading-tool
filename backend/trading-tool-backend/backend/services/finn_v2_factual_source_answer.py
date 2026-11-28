"""Answer narrow source-fact questions from typed owner-scoped reads."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.domain.indicator_display import indicator_display_name
from backend.domain.technical_indicator_catalog import get_active_technical_indicator_definitions
from backend.services.finn_v2_tool_adapters.display_source_moment import amsterdam_source_moment
from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG


def _read(results: dict[str, Any], scope: str) -> tuple[dict[str, Any] | None, str | None]:
    matching = [row for row in results.get("results") or []
                if isinstance(row, dict) and row.get("scope") == scope]
    if len(matching) != 1:
        return None, "bron niet gelezen"
    row = matching[0]
    if row.get("status") != "completed" or not isinstance(row.get("data"), dict):
        reason = str(row.get("reason") or "")
        if reason in {"tool_timeout", "read_timeout", "source_timeout"}:
            return None, "de bron reageerde niet op tijd"
        if reason in {"source_unavailable", "no_data", "report_not_found"}:
            return None, "er is geen bronmeting beschikbaar"
        return None, "de bron is tijdelijk niet beschikbaar"
    return row["data"], None


def _moment(value: Any) -> str | None:
    return amsterdam_source_moment(value)


def _moment_in_zone(value: Any, user_time_zone: str | None) -> tuple[str | None, str]:
    zone_name = user_time_zone or "Europe/Amsterdam"
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone_name = "Europe/Amsterdam"
        zone = ZoneInfo(zone_name)
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if instant.tzinfo is None:
            return None, zone_name
        return instant.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z"), zone_name
    except (TypeError, ValueError):
        return None, zone_name


def _utc_instant(value: Any) -> datetime | None:
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        return instant.astimezone(timezone.utc) if instant.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


_UNBOUND_WEEK_SAVED_CLAIM = re.compile(
    r"(?P<label>(?:\*{1,2})?\b(?:opgeslagen\s+)?weekreflectie\s+"
    r"(?:voor\s+\d{1,2}\s*[–—-]\s*\d{1,2}\s+[a-z]+(?:\s+\d{4})?\s*:\s*)?"
    r"(?:gegenereerd|opgeslagen)(?:\*{1,2})?\s*:?(?:\*{1,2})?\s*)"
    r"(?P<moment>(?:(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[a-z]+(?:\s+\d{4})?)"
    r"\s*,?\s*)?\d{1,2}:\d{2}(?::\d{2})?\s+"
    r"(?:[A-Za-z_]+/[A-Za-z_]+|[A-Z]{2,5}\b)"
    r"(?:\s*\((?:[A-Za-z_]+/[A-Za-z_]+|UTC|GMT|CET|CEST|EST|EDT|PST|PDT|Amsterdamse\s+tijd)\))?)",
    re.I,
)


def _suppress_unbound_week_saved_claims(answer: str) -> str:
    """Remove draft storage clocks whose week cannot be proven from their text."""
    return _UNBOUND_WEEK_SAVED_CLAIM.sub(
        "Opslagmoment van deze weekreflectie niet geverifieerd", answer,
    )


_UNBOUND_FX_MOMENT_CLAIM = re.compile(
    r"(?P<label>(?:\*{1,2})?(?:Geverifieerd\s+)?\b(?:FX(?:[- ]?(?:bron(?:moment)?|koers))?|"
    r"(?:exit|uitvoerings)?wisselkoers(?:bron(?:moment)?)?)\b"
    r"(?:(?![.;]\s|\n|(?:,|\ben\b)\s*(?:de\s+)?"
    r"(?:bot\w*|(?:uitstap|exit)[- ]?besliss\w*|bevestigde\s+les|"
    r"geregistreerde\s+sluiting)\b).){0,80}?)"
    r"(?P<moment>(?:(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[a-z]+(?:\s+\d{4})?)"
    r"\s*,?\s*)?\d{1,2}:\d{2}(?::\d{2})?\s+"
    r"(?:[A-Za-z_]+/[A-Za-z_]+|UTC|GMT|CET|CEST)\b)"
    r"(?P<alternative>\s*(?:\(\s*(?:(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[a-z]+"
    r"(?:\s+\d{4})?)\s*,?\s*)?\d{1,2}:\d{2}(?::\d{2})?\s+"
    r"(?:[A-Za-z_]+/[A-Za-z_]+|UTC|GMT|CET|CEST)\s*\)|"
    r"(?:,|\ben\b)\s*(?:(?:op|om)\s+)?"
    r"(?:(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[a-z]+"
    r"(?:\s+\d{4})?)\s*,?\s*)?\d{1,2}:\d{2}(?::\d{2})?\s+"
    r"(?:[A-Za-z_]+/[A-Za-z_]+|UTC|GMT|CET|CEST)\b))?"
    r"(?P<markdown_close>\*\*)?",
    re.I,
)

_HISTORICAL_EXIT_DECISION_CLAIM = re.compile(
    r"(?P<label>\b(?:uitstap|exit)[- ]?besliss\w*\b\s*"
    r"(?:(?:op|om)\s*|:\s*)?)"
    r"(?P<moment>(?:(?:20\d{2}-\d{2}-\d{2}|\d{1,2}\s+[a-z]+(?:\s+20\d{2})?)"
    r"\s*,?\s*)?(?:om\s+)?\d{1,2}:\d{2}(?::\d{2})?\s+(?:UTC|CET|CEST)\b)",
    re.I,
)

_MIXED_EXIT_DECISION_PRICE_CLAIM = re.compile(
    r"(?P<label>\b(?:uitstap|exit)[- ]?besliss\w*\s+en\s+(?:de\s+)?"
    r"(?:(?P<currency>EUR|USD|USDT)[- ]?koers\s+van\s+"
    r"(?P<price>\d+(?:[.,]\d+)?)|(?P<execution>uitvoeringskoers))\s*:\s*)"
    r"(?P<moment>(?:\d{1,2}\s+[a-z]+\s+20\d{2}|20\d{2}-\d{2}-\d{2})"
    r"\s*,?\s*\d{1,2}:\d{2}(?::\d{2})?\s+(?:UTC|CET|CEST)\b)",
    re.I,
)


def _suppress_unbound_fx_moment_claims(
    answer: str, verified_at: datetime | None, canonical_line: str | None,
) -> str:
    """Keep only model FX clocks that denote the typed Paper-exit instant."""
    months = {name: month for month, name in enumerate((
        "januari", "februari", "maart", "april", "mei", "juni", "juli",
        "augustus", "september", "oktober", "november", "december",
    ), 1)}

    def verified(moment: str) -> bool:
        if verified_at is None:
            return False
        match = re.fullmatch(
            r"(?:(?P<iso>\d{4}-\d{2}-\d{2})|(?P<day>\d{1,2})\s+"
            r"(?P<month>[a-z]+)(?:\s+(?P<year>\d{4}))?)\s*,?\s*"
            r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s+"
            r"(?P<zone>[A-Za-z_]+/[A-Za-z_]+|UTC|GMT|CET|CEST)",
            moment, re.I,
        )
        if not match:
            return False
        try:
            if match.group("iso"):
                day = datetime.fromisoformat(match.group("iso")).date()
            else:
                month = months[match.group("month").lower()]
                day = datetime(int(match.group("year") or verified_at.year),
                               month, int(match.group("day"))).date()
            label = match.group("zone")
            zone = (timezone.utc if label.upper() in {"UTC", "GMT"}
                    else ZoneInfo("Europe/Amsterdam") if label.upper() in {"CET", "CEST"}
                    else ZoneInfo(label))
            claimed = datetime(
                day.year, day.month, day.day, int(match.group("hour")),
                int(match.group("minute")), int(match.group("second") or 0),
                tzinfo=zone,
            )
            if label.upper() in {"CET", "CEST"} and claimed.tzname() != label.upper():
                return False
            actual = verified_at.astimezone(timezone.utc)
            stated = claimed.astimezone(timezone.utc)
            return (stated == actual if match.group("second") is not None
                    else stated.replace(second=0) == actual.replace(second=0))
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            return False

    def scrub(fragment: str) -> str:
        replacement = (
            "FX-brontijd: zie de afzonderlijk geverifieerde bronregel"
            if canonical_line else
            "FX-brontijd: niet verifieerbaar uit opgeslagen bewijs"
        )
        def replace(match: re.Match[str]) -> str:
            if not match.group("alternative") and verified(match.group("moment")):
                return match.group(0)
            # The match includes both outer and inner emphasis markers, so
            # rejected draft clocks cannot leave a dangling `**` behind.
            return replacement

        return _UNBOUND_FX_MOMENT_CLAIM.sub(replace, fragment)

    # Only the exact line assembled from typed evidence is exempt. A model may
    # write the word "Geverifieerd" in front of an incorrect clock.
    return (canonical_line.join(scrub(fragment) for fragment in answer.split(canonical_line))
            if canonical_line else scrub(answer))


def complete_historical_week_exit_moments(
    answer: str, evidence: tuple[dict[str, Any], ...], *, question: str,
    user_time_zone: str | None,
) -> str:
    """Show the two verified source moments in the user's zone for a weekly exit review."""
    if not user_time_zone or not re.search(r"\b(?:weekreflectie|wekelijkse reflectie)\b", question, re.I) \
            or not re.search(r"\bAAPL\b", question, re.I) \
            or not re.search(r"\bPaper\b", question, re.I) \
            or not re.search(r"\b(?:exitreden|exit|uitstap|verkoop|afgesloten)\b", question, re.I):
        return answer
    try:
        ZoneInfo(user_time_zone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return answer
    rows = [item["data"] for item in evidence
            if item.get("scope") == "read_review_history"
            and item.get("status") == "completed" and isinstance(item.get("data"), dict)]
    weeks = [row["weekly_reflection"] for row in rows
             if isinstance(row.get("weekly_reflection"), dict)]
    if not weeks:
        return answer
    week = weeks[0]
    # The model can read the same owner-scoped history twice in one turn. A
    # duplicate read is safe; conflicting saved weeks are not.
    week_key = tuple(week.get(key) for key in
                     ("week_start", "week_end", "generated_at", "time_zone"))
    if any(tuple(candidate.get(key) for key in
                 ("week_start", "week_end", "generated_at", "time_zone")) != week_key
           for candidate in weeks[1:]):
        return answer
    try:
        start = datetime.fromisoformat(str(week["week_start"])).date()
        end = datetime.fromisoformat(str(week["week_end"])).date()
    except (KeyError, TypeError, ValueError):
        return answer
    try:
        period_zone = ZoneInfo(str(week.get("time_zone") or user_time_zone))
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return answer
    all_trades = [trade for row in rows for trade in row.get("closed_trades") or []
                  if isinstance(trade, dict)]
    # Check a dossier's identity and registered exit across every read before
    # filtering by week. Otherwise an inconsistent out-of-week duplicate can
    # disappear and make the remaining timestamp look verified.
    dossiers: dict[int, tuple[str, str, datetime | None, datetime | None]] = {}
    for trade in all_trades:
        review_id = trade.get("review_id")
        if type(review_id) is not int:
            continue
        identity = (str(trade.get("symbol") or ""),
                    str(trade.get("environment") or "").lower(),
                    _utc_instant(trade.get("exit_at")),
                    _utc_instant(trade.get("paper_exit_decision_at")))
        if review_id in dossiers and dossiers[review_id] != identity:
            return answer
        dossiers[review_id] = identity
    matching_trades = [trade for trade in all_trades
                       if trade.get("symbol") == "AAPL"
                       and str(trade.get("environment") or "").lower() == "paper"
                       and (instant := _utc_instant(trade.get("exit_at"))) is not None
                       and start <= instant.astimezone(period_zone).date() <= end]
    unique_trades = {(trade.get("review_id"), str(trade["exit_at"])): trade
                     for trade in matching_trades}
    trades = list(unique_trades.values())
    if len(trades) != 1:
        return answer
    requested_ids = {int(match.group(1)) for match in re.finditer(
        r"\b(?:dossier|trade(?:[- ]?(?:reflectie|review))?|review)\s*#\s*(\d+)\b",
        question, re.I,
    )}
    if requested_ids and requested_ids != {trades[0].get("review_id")}:
        return answer
    # A separately named exit date can refer to another trade than the week.
    # Remove the week range before interpreting dates as trade references.
    without_week = re.sub(
        r"\b\d{1,2}\s*[–—-]\s*\d{1,2}\s+"
        r"(?:jan(?:uari)?|feb(?:ruari)?|mrt|maart|apr(?:il)?|mei|jun(?:i)?|"
        r"jul(?:i)?|aug(?:ustus)?|sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        "", question, flags=re.I,
    )
    without_week = re.sub(
        rf"\b{re.escape(start.isoformat())}\s*(?:tot|t/m|[–—-])\s*"
        rf"{re.escape(end.isoformat())}\b", "", without_week, flags=re.I,
    )
    exit_date = _utc_instant(trades[0]["exit_at"]).astimezone(period_zone).date()
    for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", without_week):
        try:
            if datetime.fromisoformat(match.group()).date() != exit_date:
                return answer
        except ValueError:
            return answer
    without_week = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", without_week)
    # Numeric locale dates are ambiguous (day/month versus month/day). Do not
    # guess which exit they identify; the week range itself was removed above.
    if re.search(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b", without_week):
        return answer
    month_numbers = {name: number for number, names in enumerate((
        ("januari", "jan"), ("februari", "feb"), ("maart", "mrt"),
        ("april", "apr"), ("mei",), ("juni", "jun"), ("juli", "jul"),
        ("augustus", "aug"), ("september", "sep"), ("oktober", "okt"),
        ("november", "nov"), ("december", "dec"),
    ), 1) for name in names}
    for match in re.finditer(
        r"\b(\d{1,2})\s+(januari|jan|februari|feb|maart|mrt|april|apr|mei|"
        r"juni|jun|juli|jul|augustus|aug|september|sep|oktober|okt|"
        r"november|nov|december|dec)(?:\s+(\d{4}))?\b", without_week, re.I,
    ):
        if (int(match.group(1)), month_numbers[match.group(2).lower()]) != (
            exit_date.day, exit_date.month,
        ) or (match.group(3) and int(match.group(3)) != exit_date.year):
            return answer
    exit_at, zone_name = _moment_in_zone(trades[0]["exit_at"], user_time_zone)
    saved_at, _ = _moment_in_zone(week.get("generated_at"), user_time_zone)
    if not exit_at or not saved_at:
        return answer
    decision_instants = {_utc_instant(trade.get("paper_exit_decision_at"))
                         for trade in matching_trades}
    decision_at_in_zone = None
    verified_decision_at = None
    if (len(decision_instants) == 1 and None not in decision_instants
            and all(isinstance(trade.get("paper_exit_evidence"), dict)
                    and trade["paper_exit_evidence"].get("trigger") in {"first_target", "stop_loss"}
                    for trade in matching_trades)):
        verified_decision_at = next(iter(decision_instants))
        decision_at_in_zone, _ = _moment_in_zone(verified_decision_at, user_time_zone)
    # A price source observation is not the bot decision. Rewrite the narrow
    # mixed draft only when every owner-bound copy agrees on the typed quote.
    quote_facts = [trade.get("paper_exit_evidence") for trade in matching_trades]
    if all(isinstance(facts, dict) for facts in quote_facts):
        def distinct_price_source(match: re.Match[str]) -> str:
            clause_start = max(answer.rfind(".", 0, match.start()),
                               answer.rfind("\n", 0, match.start())) + 1
            next_stops = [stop for stop in (answer.find(".", match.end()),
                                             answer.find("\n", match.end())) if stop >= 0]
            clause_end = min(next_stops, default=len(answer))
            clause = answer[clause_start:clause_end]
            stated_ids = {int(ref.group(1)) for ref in re.finditer(
                r"\b(?:dossier|trade(?:[- ]?(?:reflectie|review))?|review)\s*#?\s*(\d+)\b",
                clause, re.I,
            )}
            stated_bot_ids = {int(ref.group(1)) for ref in re.finditer(
                r"\bbot\s*#?\s*(\d+)\b", clause, re.I,
            )}
            if (verified_decision_at is None
                    or (stated_ids and stated_ids != {trades[0].get("review_id")})
                    or (stated_bot_ids and stated_bot_ids != {trades[0].get("bot_id")})):
                return match.group(0)
            if ((re.search(r"\b(?:eerdere|vorige|voorgaande|andere|oudere)\b", clause, re.I)
                    and re.search(r"\b(?:trade|dossier|review)\b", clause, re.I))
                    or re.search(r"\b(?:ochtend|middag|avond)[- ]?trade\b", clause, re.I)):
                return match.group(0)
            execution = bool(match.group("execution"))
            moment_key = "execution_source_price_at" if execution else "source_price_at"
            price_key = "execution_source_price" if execution else "source_price"
            quote_moments = {_utc_instant(facts.get(moment_key)) for facts in quote_facts}
            currency_key = ("execution_source_price_currency" if execution
                            else "source_price_currency")
            quote_prices = {(str(facts.get(currency_key) or "").upper(),
                             str(facts.get(price_key) or "")) for facts in quote_facts}
            if (len(quote_moments) != 1 or None in quote_moments
                    or len(quote_prices) != 1):
                return match.group(0)
            quote_at = next(iter(quote_moments))
            currency, raw_price = next(iter(quote_prices))
            try:
                verified_price = Decimal(raw_price)
                claimed_price = (Decimal(match.group("price").replace(",", "."))
                                 if not execution else verified_price)
            except (InvalidOperation, TypeError, ValueError):
                return match.group(0)
            claim = _claimed_moment(match.group("moment"))
            registered_close = _utc_instant(trades[0]["exit_at"])
            if (claim and (any(_same_moment(claim, instant) for instant in
                               (quote_at, verified_decision_at, registered_close) if instant)
                           if execution else _same_moment(claim, quote_at))
                    and currency in {"EUR", "USD", "USDT"}
                    and (execution or match.group("currency").upper() == currency)
                    and verified_price.is_finite() and verified_price > 0
                    and claimed_price == verified_price):
                if execution:
                    zone_quote, _ = _moment_in_zone(quote_at, user_time_zone)
                    displayed_price = f"{verified_price:.2f}".replace(".", ",")
                    return (f"Koersbron bij AAPL Paper-uitvoering: "
                            f"{displayed_price} {currency} op {zone_quote} "
                            f"({quote_at.strftime('%Y-%m-%d %H:%M:%S UTC')}; {user_time_zone})")
                return (f"Koersbron bij AAPL Paper-exitbeoordeling: "
                        f"{match.group('price')} {currency} op {match.group('moment')}")
            return match.group(0)

        from backend.services.finn_v2_source_moment_claims import _claimed_moment, _same_moment
        answer = _MIXED_EXIT_DECISION_PRICE_CLAIM.sub(distinct_price_source, answer)
    if decision_at_in_zone and re.search(r"\bbronmoment(?:en)?\b", question, re.I):
        # A model may call the registered close an exit decision. Replace
        # only that historical decision clock, using the owner-read closing
        # ledger's linked decision; leave unrelated clocks and prose intact.
        from backend.services.finn_v2_source_moment_claims import _claimed_moment, _same_moment

        def corrected_decision(match: re.Match[str]) -> str:
            clause_start = max(answer.rfind(".", 0, match.start()),
                               answer.rfind("\n", 0, match.start())) + 1
            next_stops = [stop for stop in (answer.find(".", match.end()),
                                             answer.find("\n", match.end())) if stop >= 0]
            clause_end = min(next_stops, default=len(answer))
            clause = answer[clause_start:clause_end]
            if ((re.search(r"\b(?:eerdere|vorige|voorgaande|andere|oudere)\b", clause, re.I)
                    and re.search(r"\b(?:trade|dossier|review)\b", clause, re.I))
                    or re.search(r"\b(?:ochtend|middag|avond)[- ]?trade\b", clause, re.I)):
                return match.group(0)
            moment = match.group("moment")
            if not re.search(r"\b20\d{2}\b", moment):
                moment = re.sub(
                    r"^(\d{1,2}\s+[a-z]+)",
                    lambda date: f"{date.group(1)} {verified_decision_at.year}",
                    moment, count=1, flags=re.I,
                )
            claim = _claimed_moment(moment)
            if claim is None or claim[0].astimezone(ZoneInfo(user_time_zone)).date() != (
                verified_decision_at.astimezone(ZoneInfo(user_time_zone)).date()
            ):
                return match.group(0)
            if _same_moment(claim, verified_decision_at):
                return match.group(0)
            # Correct only the proven confusion between this dossier's
            # closing registration and its linked decision. Another time on
            # the same day could belong to another trade.
            registered_close = _utc_instant(trades[0]["exit_at"])
            if not claim[1] or registered_close is None or not _same_moment(claim, registered_close):
                return match.group(0)
            return match.group("label") + decision_at_in_zone

        answer = _HISTORICAL_EXIT_DECISION_CLAIM.sub(
            corrected_decision, answer,
        )
    fx_instants: set[datetime] = set()
    for trade in matching_trades:
        paper_exit = trade.get("paper_exit_evidence")
        if not isinstance(paper_exit, dict):
            continue
        try:
            factor = Decimal(str(paper_exit.get("execution_fx_eur_per_unit")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        fx_at = _utc_instant(paper_exit.get("execution_fx_observed_at"))
        if factor.is_finite() and factor > 0 and fx_at is not None:
            fx_instants.add(fx_at)
    fx_at_in_zone = None
    verified_fx_at = None
    if len(fx_instants) == 1:
        verified_fx_at = next(iter(fx_instants))
        fx_at_in_zone, _ = _moment_in_zone(verified_fx_at, user_time_zone)
    answer = _suppress_unbound_week_saved_claims(answer)
    fx_line = (
        f"Geverifieerd FX-bronmoment bij AAPL Paper-uitvoering: "
        f"{fx_at_in_zone} ({zone_name})."
    ) if fx_at_in_zone else None
    if re.search(r"\bbronmoment(?:en)?\b", question, re.I):
        answer = _suppress_unbound_fx_moment_claims(answer, verified_fx_at, fx_line)
    additions = []
    if exit_at not in answer:
        additions.append(f"AAPL Paper-trade als gesloten geregistreerd: {exit_at} ({zone_name}).")
    if saved_at not in answer:
        additions.append(
            f"Geverifieerd opslagmoment week {start.isoformat()} t/m {end.isoformat()}: "
            f"{saved_at} ({zone_name})."
        )
    if fx_at_in_zone and re.search(r"\bbronmoment(?:en)?\b", question, re.I):
        if fx_line not in answer:
            additions.append(fx_line)
    if decision_at_in_zone and re.search(r"\bbronmoment(?:en)?\b", question, re.I):
        utc_clock = verified_decision_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        decision_line = (
            f"Geverifieerde AAPL Paper-exitbeslissing: {decision_at_in_zone} "
            f"({utc_clock}; {zone_name})."
        )
        if decision_line not in answer:
            additions.append(decision_line)
    return answer.rstrip() + ("\n" + "\n".join(additions) if additions else "")


def _number(value: Any) -> str | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return format(amount.normalize(), "f") if amount.is_finite() else None


_REPORT_BLOCK_REASON_NL = {
    # These are the labels shown by the Dutch report for stored block codes.
    # Keep the raw decision reason separate: it can differ from the report UI.
    "market_price_stale": "Geen recente marktprijs beschikbaar voor deze beoordeling.",
}


def _report_reason(decision: dict[str, Any]) -> tuple[str, str]:
    raw = str(decision.get("reason") or "").strip()
    display = _REPORT_BLOCK_REASON_NL.get(str(decision.get("block_code") or ""), raw)
    return display, raw


def render_closed_paper_exit_facts(message: str, tool_trace: Any) -> str | None:
    """Read an explicitly named Paper exit from its owner-scoped review row.

    The Responses model still performs the read. For this narrow question the
    exact stored currency, target and FX factor are rendered from typed facts,
    so the final answer cannot silently omit one of them.
    """
    match = re.search(r"\b(?:trade[- ]?reflectie|reflectie)\s*#\s*(\d{1,12})\b", message, re.I)
    if (not match or not re.search(r"Paper[- ]?exitreden", message, re.I)
            or not re.search(r"oorspronkelijke koersvaluta", message, re.I)
            or not re.search(r"eerste doel", message, re.I)
            or not re.search(r"wisselkoers bij uitvoering", message, re.I)):
        return None
    review_id = int(match.group(1))
    rows = [row for call in (tool_trace or ()) if isinstance(call, dict)
            for row in ((call.get("result") or {}).get("results") or ())
            if isinstance(row, dict) and row.get("scope") == "read_review_history"
            and row.get("status") == "completed" and isinstance(row.get("data"), dict)]
    if len(rows) != 1:
        return None
    reviews = [row for row in rows[0]["data"].get("closed_trades") or ()
               if isinstance(row, dict) and row.get("review_id") == review_id
               and str(row.get("environment") or "").lower() == "paper"]
    if len(reviews) != 1:
        return None
    facts = reviews[0].get("paper_exit_evidence")
    if not isinstance(facts, dict):
        return None
    trigger = facts.get("trigger")
    currency = str(facts.get("source_price_currency") or "").upper()
    if trigger not in {"stop_loss", "first_target"} or currency not in {"EUR", "USD", "USDT"}:
        return None

    def positive_number(key: str) -> str | None:
        try:
            value = Decimal(str(facts.get(key)))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not value.is_finite() or value <= 0:
            return None
        return format(value.normalize(), "f")

    target = positive_number("saved_first_target")
    fx = positive_number("execution_fx_eur_per_unit")
    if not target or not fx:
        return None
    reason = "stop-loss" if trigger == "stop_loss" else "eerste koersdoel"
    return (f"Bij trade-reflectie #{review_id} was de vastgelegde Paper-exitreden {reason}. "
            f"De oorspronkelijke koersvaluta was {currency}. Het opgeslagen eerste doel "
            f"was {target} {currency}. De wisselkoers bij uitvoering was {fx} EUR per {currency}. "
            "Dit zijn de opgeslagen virtuele uitvoeringsgegevens, geen actuele koers of nieuw handelssignaal.")


def render_bot_decision(
    result: dict[str, Any], *, symbol: str, paper: bool | None,
    pair: str | None = None, bot_id: int | None = None,
    referenced_minute: bool = False, user_time_zone: str | None = None,
) -> str:
    data, reason = _read(result, "read_review_history")
    if data is None:
        return f"Ik kan de opgeslagen botbesluiten voor {symbol} nu niet lezen ({reason})."
    source = "referenced_bot_decisions" if referenced_minute else "latest_bot_decisions"
    decisions = [row for row in data.get(source) or []
                 if isinstance(row, dict)
                 and str(row.get("symbol") or "").upper().split("/", 1)[0] == symbol
                 and (bot_id is None or row.get("bot_id") == bot_id)
                 and (pair is None or str(row.get("pair") or row.get("symbol") or "").upper() == pair)
                 and (paper is None or bool(row.get("is_live")) is paper)]
    if not decisions:
        label = f"bot {bot_id} ({symbol})" if bot_id is not None else f"{symbol}-bot"
        return f"Ik vind geen opgeslagen besluit voor {label} in dit account."
    if len(decisions) != 1:
        names = ", ".join(str(row.get("bot_name") or "onbekend") for row in decisions[:5])
        return f"Ik vind meerdere {symbol}-bots ({names}). Welke bot bedoel je?"
    row = decisions[0]
    at, zone_name = _moment_in_zone(row.get("decision_at"), user_time_zone)
    action = str(row.get("action") or "").lower()
    if not at or action not in {"hold", "buy", "sell"}:
        return f"Het opgeslagen {symbol}-botbesluit mist een controleerbare actie of tijd."
    mode = "Paper" if not row.get("is_live") else "Live"
    action_text = {"hold": "geen order (hold)", "buy": "koopbesluit (buy)",
                   "sell": "verkoopbesluit (sell)"}[action]
    safety_state = str(row.get("safety_state") or "").lower()
    saved_reason = str(row.get("safety_reason") or "").strip()
    safety_text = (f" Opgeslagen botreden: {saved_reason}." if saved_reason else
                   " De opgeslagen beslissing vermeldt geen concrete reden.")
    if safety_state in {"blocked", "error"}:
        action_text = "trade geblokkeerd / geen order"
        safety_text = f" Opgeslagen blokkadereden: {saved_reason}." if saved_reason else (
            " De opgeslagen veiligheidscontrole vermeldt geen controleerbare reden."
        )
    status = {"planned": "besluit opgeslagen", "completed": "besluit afgerond",
              "skipped": "besluit zonder order afgerond", "executed": "besluit uitgevoerd",
              "failed": "besluit mislukt"}.get(str(row.get("persistence_status") or ""),
                                          "opslagstatus onbekend")
    try:
        instant = datetime.fromisoformat(str(row["decision_at"]).replace("Z", "+00:00"))
        historical = instant.astimezone(timezone.utc) < datetime.now(timezone.utc)
    except (TypeError, ValueError):
        historical = True
    kind = "historische opgeslagen beoordeling" if historical else "opgeslagen beoordeling"
    label = f"bot {bot_id} ({pair or symbol})" if bot_id is not None else pair or symbol
    prefix = "Het opgeslagen besluit" if referenced_minute else "Het laatst opgeslagen besluit"
    return (f"{prefix} van je {label} {mode}-bot is {action_text}, "
            f"op {at} ({zone_name}). Dit is een {kind}, geen actuele "
            f"marktbeoordeling. Opslagstatus: {status}.{safety_text}")


def latest_paper_hold_decision(
    result: dict[str, Any], *, symbol: str, bot_id: int | None = None,
    requested_pair: str | None = None,
) -> dict[str, Any] | None:
    data, _ = _read(result, "read_review_history")
    if data is None:
        return None
    rows = [row for row in data.get("latest_bot_decisions") or []
            if isinstance(row, dict) and row.get("is_live") is False
            and str(row.get("symbol") or "").upper().split("/", 1)[0] == symbol
            and (bot_id is None or row.get("bot_id") == bot_id)
            and (requested_pair is None
                 or str(row.get("pair") or row.get("symbol") or "").upper() == requested_pair)]
    if len(rows) != 1:
        return None
    if (str(rows[0].get("action") or "").lower() != "hold"
            or str(rows[0].get("persistence_status") or "").lower()
            not in {"planned", "skipped", "completed"}):
        return None
    return rows[0]


def latest_paper_bot_pair(
    result: dict[str, Any], *, symbol: str, bot_id: int | None = None,
    requested_pair: str | None = None,
) -> str | None:
    row = latest_paper_hold_decision(
        result, symbol=symbol, bot_id=bot_id, requested_pair=requested_pair,
    )
    pair = str((row or {}).get("pair") or "").upper()
    return pair if re.fullmatch(rf"{re.escape(symbol)}/(?:EUR|USDT)", pair) else None


def asset_wide_paper_hold(
    result: dict[str, Any], *, symbol: str, bot_id: int | None = None,
    requested_pair: str | None = None,
) -> bool:
    row = latest_paper_hold_decision(
        result, symbol=symbol, bot_id=bot_id, requested_pair=requested_pair,
    )
    return bool(row and requested_pair is None
                and not str(row.get("pair") or "").strip()
                and str(row.get("symbol") or "").upper() == symbol)


def _asset_wide_quote_context(
    result: dict[str, Any] | None, *, symbol: str, quote: str,
    user_time_zone: str,
) -> str:
    label = f"{symbol}/{quote}"
    unavailable = f"Voor {label} kan ik geen gedateerde koersbron verifiëren."
    market, _ = _read(result or {"results": []}, "read_market_snapshot")
    if not isinstance(market, dict):
        return unavailable
    source_ref = market.get("source_ref")
    market_id = market.get("market_id")
    price = _number(market.get("price"))
    source_at = market.get("source_observed_at_utc")
    ref_at = source_ref.get("source_observed_at_utc") if isinstance(source_ref, dict) else None
    at, zone_name = _moment_in_zone(source_at, user_time_zone)
    source_utc = _utc_instant(source_at)
    ref_utc = _utc_instant(ref_at)
    if (market.get("symbol") != symbol or market.get("pair") != label
            or market.get("quote_currency") != quote
            or type(market_id) is not int or market_id <= 0
            or not isinstance(source_ref, dict)
            or source_ref.get("market_id") != market_id
            or type(source_ref.get("measurement_id")) is not int
            or source_ref["measurement_id"] <= 0
            or source_utc is None or source_utc != ref_utc
            or not at or not price or Decimal(price) <= 0):
        return unavailable
    provider = str(market.get("price_provider") or "onbekend")
    return (f"De laatst beschikbare {label}-koers als algemene marktcontext is "
            f"{price} {quote} van {provider}, bronmoment {at} ({zone_name}).")


def render_bot_hold_quote_coach(
    decision_result: dict[str, Any], quote_result: dict[str, Any] | None,
    *, symbol: str, bot_id: int | None = None, requested_pair: str | None = None,
    user_time_zone: str | None = None,
    asset_quote_results: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Keep the saved Paper hold, latest pair quote and saved risk separate."""
    try:
        ZoneInfo(user_time_zone or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        user_time_zone = "UTC"
    else:
        user_time_zone = user_time_zone or "UTC"
    decision = latest_paper_hold_decision(
        decision_result, symbol=symbol, bot_id=bot_id, requested_pair=requested_pair,
    )
    pair = latest_paper_bot_pair(
        decision_result, symbol=symbol, bot_id=bot_id, requested_pair=requested_pair,
    )
    decision_text = render_bot_decision(
        decision_result, symbol=symbol, paper=False, bot_id=bot_id,
        pair=requested_pair, user_time_zone=user_time_zone,
    )
    if decision is None:
        return (f"{decision_text} Ik kan uit deze lezing geen eenduidig opgeslagen "
                "Paper-Hold zonder order en met exact handelspaar vaststellen. "
                "Daarom vergelijk ik geen koersbron en geef ik geen blokkadeadvies. "
                "Controleer eerst het laatste botbesluit in de botdetails; ik wijzig niets.")
    if pair is None and (str(decision.get("pair") or "").strip()
                         or str(decision.get("symbol") or "").upper() != symbol):
        return (f"{decision_text} Het opgeslagen handelspaar kan ik niet als ondersteund "
                "paar verifiëren. Daarom vergelijk ik geen koersbron en geef ik geen "
                "blokkadeadvies. Controleer het handelspaar in de botdetails; ik wijzig niets.")
    quote = pair.split("/", 1)[1] if pair else None
    quote_text = (render_latest_quote(
        quote_result or {"results": []}, symbol=symbol, quote_currency=quote,
        user_time_zone=user_time_zone,
    ) if quote else (f"Deze Paper-bot is voor {symbol} zonder vast handelspaar opgeslagen. "
                     "Ik kan daarom geen exacte koersbron aan dit botbesluit koppelen. "
                     + (" ".join(_asset_wide_quote_context(
                         asset_quote_results.get(unit), symbol=symbol, quote=unit,
                         user_time_zone=user_time_zone,
                     ) for unit in ("EUR", "USDT"))
                        + " Deze marktmetingen zijn geen bewezen bron van het botbesluit of uitvoeringskoers."
                        if asset_quote_results is not None else "")))
    profile, _ = _read(decision_result, "read_profile")
    stored = profile.get("trader_profile") if isinstance(profile, dict) else None
    risks = stored.get("risk_profiles") if isinstance(stored, dict) else None
    if profile and profile.get("has_profile") is True and isinstance(risks, list):
        risk_text = ("Je opgeslagen risicoprofiel is normaal. " if risks == ["balanced"] else
                     "Je opgeslagen profiel bevestigt geen eenduidig normaal risicoprofiel. ")
    else:
        risk_text = "Ik kan je opgeslagen risicoprofiel nu niet verifiëren. "
    reason_code = str(decision.get("safety_reason_code") or "")
    if reason_code == "strategy_price_currency_unconfirmed":
        step = "Controleer de valuta van de opgeslagen koersniveaus in de gekoppelde strategie vóór een nieuwe Paper-beoordeling."
    elif reason_code == "strategy_price_conversion_unavailable":
        step = "Controleer de omrekening van de opgeslagen koersniveaus vóór een nieuwe Paper-beoordeling."
    else:
        step = "Controleer de opgeslagen blokkade in de botdetails vóór een nieuwe Paper-beoordeling."
    market, _ = _read(quote_result or {"results": []}, "read_market_snapshot")
    verified_quote = bool(
        quote and isinstance(market, dict)
        and str(market.get("symbol") or "").upper() == symbol
        and str(market.get("quote_currency") or "").upper() == quote
        and _number(market.get("price"))
        and _moment_in_zone(
            market.get("source_observed_at_utc") or market.get("source_observed_at"),
            user_time_zone,
        )[0]
    )
    separation = (f" Het beslismoment en het koersbronmoment zijn verschillende bronnen; "
                  f"de laatst beschikbare {pair}-koers is geen geverifieerde uitvoeringskoers."
                  if verified_quote else "")
    return (f"{decision_text} {quote_text}{separation} "
            f"{risk_text}Veilige vervolgstap: {step} "
            "Ik wijzig geen bot of order.")


def render_report_bot_check_comparison(
    result: dict[str, Any], *, symbol: str, message: str = "",
) -> str:
    """Compare one requested historical check with the saved report, by bot ID."""
    history, history_error = _read(result, "read_review_history")
    report, report_error = _read(result, "read_latest_report")
    if history is None or report is None:
        missing = []
        if history is None:
            missing.append(f"de opgeslagen botcheck ({history_error})")
        if report is None:
            missing.append(f"het dagrapport ({report_error})")
        return (f"Ik kan {' en '.join(missing)} voor {symbol} nu niet vergelijken. "
                "Verander de weging of bot niet om een koop te forceren; controleer de bronnen opnieuw.")
    requested_report_clock = re.search(
        r"\b(?:dagrapport|ochtendrapport|rapport)\b[^.!?\n]{0,80}?\b([01]?\d|2[0-3]):([0-5]\d)\b",
        message, re.I,
    )
    report_generated = report.get("generated_at_amsterdam") or _moment(report.get("generated_at"))
    if requested_report_clock and (
        not report_generated or
        not re.search(rf"\b{int(requested_report_clock.group(1)):02d}:"
                      rf"{requested_report_clock.group(2)}(?::\d{{2}})?\b", str(report_generated))
    ):
        missing_check = not any(
            isinstance(row, dict) and str(row.get("symbol") or "").upper().split("/", 1)[0] == symbol
            for row in history.get("referenced_bot_decisions") or []
        )
        return (f"Het gelezen {symbol}-dagrapport heeft niet het genoemde uitleesmoment "
                f"{requested_report_clock.group(1)}:{requested_report_clock.group(2)}. "
                "Het specifiek gevraagde rapport is daarmee niet geverifieerd. "
                + (f"Ook de genoemde {symbol}-botcheck is niet gevonden. " if missing_check else "")
                + "Ik kan de botredenen daarom niet betrouwbaar vergelijken.")
    historical = [row for row in history.get("referenced_bot_decisions") or []
                  if isinstance(row, dict) and str(row.get("symbol") or "").upper().split("/", 1)[0] == symbol]
    if len(historical) != 1:
        report_status = (f"Ik heb een opgeslagen {symbol}-dagrapport van {report_generated} gelezen. "
                         if report_generated else
                         f"Ik heb een opgeslagen {symbol}-dagrapport gelezen, zonder controleerbaar rapportmoment. ")
        check_status = (f"De genoemde {symbol}-botcheck ontbreekt in de gelezen beslissingen "
                        "en is daarom niet eenduidig te koppelen. "
                        if not historical else
                        f"De genoemde {symbol}-botcheck koppelt aan meerdere beslissingen. ")
        return (report_status + check_status
                + "Daarom kan ik de twee botredenen niet betrouwbaar vergelijken. "
                "Controleer de beslissing in Automatisering; wijzig de weging niet om een koop te forceren.")
    check = historical[0]
    snapshot = report.get("score_source_snapshot") or {}
    report_v2 = snapshot.get("report_v2") if isinstance(snapshot, dict) else None
    automation = report_v2.get("automation") if isinstance(report_v2, dict) else None
    bots = automation.get("bots") if isinstance(automation, dict) else None
    report_bots = [bot for bot in bots or [] if isinstance(bot, dict)
                   and bot.get("bot_id") == check.get("bot_id")
                   and str(bot.get("symbol") or "").upper().split("/", 1)[0] == symbol]
    if len(report_bots) != 1 or not isinstance(report_bots[0].get("latest_decision"), dict):
        return (f"De check voor {symbol} is gevonden, maar het dagrapport bevat geen eenduidig besluit "
                "voor dezelfde bot. De verschillende redenen zijn daarom niet verifieerbaar.")
    report_decision = report_bots[0]["latest_decision"]
    report_at = report_decision.get("at_amsterdam") or _moment(report_decision.get("at"))
    check_at = check.get("decision_at_amsterdam") or _moment(check.get("decision_at"))
    report_reason, raw_report_reason = _report_reason(report_decision)
    check_reason = str(check.get("safety_reason") or "").strip()
    lines = [f"Ik heb de opgeslagen besluiten van dezelfde {symbol}-bot vergeleken."]
    lines.append(
        f"Het dagrapport{f' van {report_generated}' if report_generated else ''} is een momentopname. "
        f"Het botbesluit daarin is van {report_at or 'een onbekend bronmoment'}: "
        f"{report_reason.rstrip('.') if report_reason else 'geen controleerbare reden opgeslagen'}."
    )
    if raw_report_reason and raw_report_reason != report_reason:
        lines.append(f"De ruwe opgeslagen botreden in de rapportsnapshot luidt: {raw_report_reason.rstrip('.')}.")
    lines.append(
        f"De afzonderlijke botcheck van {check_at or 'een onbekend bronmoment'} vermeldt "
        f"{check_reason or 'geen controleerbare reden'}; "
        f"actie {check.get('action') or 'onbekend'}."
    )
    lines.append(
        "Dit zijn twee beoordelingen op verschillende momenten. De tweede reden vervangt de "
        "eerste niet achteraf. Verander de weging of bot niet om alsnog een koopmatch te maken. "
        "Controleer bij de volgende beursopening de verse koers, de score tegenover je opgeslagen "
        "band en de nieuwe botbeslissing voordat je iets verandert of handelt."
    )
    return "\n\n".join(lines)


def render_multi_asset_report_bot_comparison(
    results: list[dict[str, Any]], *, symbols: tuple[str, ...],
    named_pairs: tuple[str, ...] = (),
) -> str:
    """Compare several owner-read bot histories with one dated report snapshot.

    The model can confuse a report decision with a newer check when several
    assets appear in one turn. This narrow read-only answer binds each reason
    and source moment to its own saved row, and reports gaps explicitly.
    """
    reports: dict[tuple[str, str], dict[str, Any]] = {}
    histories: list[dict[str, Any]] = []
    for result in results:
        for row in result.get("results") or []:
            if not isinstance(row, dict) or row.get("status") != "completed" \
                    or not isinstance(row.get("data"), dict):
                continue
            data = row["data"]
            if row.get("scope") == "read_latest_report":
                key = (str(data.get("report_date") or ""), str(data.get("generated_at") or ""))
                reports[key] = data
            elif row.get("scope") == "read_review_history":
                histories.append(data)
    if len(reports) != 1:
        return ("Ik kan het gevraagde dagrapport niet eenduidig teruglezen. "
                "Ik vergelijk daarom geen botredenen of bronmomenten.")
    report = next(iter(reports.values()))
    report_at = report.get("generated_at_amsterdam") or _moment(report.get("generated_at"))
    snapshot = report.get("score_source_snapshot") or {}
    report_v2 = snapshot.get("report_v2") if isinstance(snapshot, dict) else None
    automation = report_v2.get("automation") if isinstance(report_v2, dict) else None
    bots = automation.get("bots") if isinstance(automation, dict) else None
    if not report_at or not isinstance(bots, list):
        return ("Het dagrapport mist een controleerbaar rapportmoment of de opgeslagen "
                "botmomentopname. Ik vergelijk daarom geen botredenen.")
    lines = [f"Dagrapport gegenereerd op {report_at}: dit is de bevroren momentopname."]
    for symbol in symbols:
        report_bots = [bot for bot in bots if isinstance(bot, dict)
                       and str(bot.get("symbol") or "").upper() == symbol
                       and bot.get("is_live") is False]
        current = [decision for history in histories
                   for decision in history.get("latest_bot_decisions") or []
                   if isinstance(decision, dict)
                   and str(decision.get("symbol") or "").upper().split("/", 1)[0] == symbol
                   and decision.get("is_live") is False]
        # Repeated owner reads are duplicates, not separate bot decisions.
        current_by_bot = {str(row.get("bot_id")): row for row in current
                          if row.get("bot_id") is not None}
        report_ids = {str(bot.get("bot_id")) for bot in report_bots
                      if bot.get("bot_id") is not None}
        if not report_bots:
            lines.append(f"{symbol}: in dit rapport is geen Paper-botbesluit vastgelegd.")
        for bot in report_bots[:5]:
            bot_id = bot.get("bot_id")
            pair = str(bot.get("trading_pair") or symbol).upper()
            saved = bot.get("latest_decision")
            if isinstance(saved, dict):
                at = saved.get("at_amsterdam") or _moment(saved.get("at"))
                reason, raw = _report_reason(saved)
                lines.append(
                    f"{pair}, bot {bot_id}: rapportbesluit van {at or 'onbekend bronmoment'}; "
                    f"rapportreden: {(reason or 'geen controleerbare reden').rstrip('.')}."
                )
                if raw and raw != reason:
                    lines.append(f"De ruwe reden van dit rapportbesluit luidt: {raw.rstrip('.')}.")
            else:
                lines.append(f"{pair}, bot {bot_id}: geen besluit in de rapportmomentopname.")
            later = current_by_bot.get(str(bot_id))
            if later:
                later_at = later.get("decision_at_amsterdam") or _moment(later.get("decision_at"))
                later_reason = str(later.get("safety_reason") or "").strip()
                lines.append(
                    f"{pair}, bot {bot_id}: laatst gelezen Paper-check van "
                    f"{later_at or 'onbekend bronmoment'}; reden: "
                    f"{(later_reason or 'geen controleerbare reden').rstrip('.')}."
                )
            else:
                lines.append(f"{pair}, bot {bot_id}: geen latere Paper-check eenduidig gelezen.")
        for bot_id, row in current_by_bot.items():
            if bot_id not in report_ids:
                pair = str(row.get("pair") or row.get("symbol") or symbol).upper()
                at = row.get("decision_at_amsterdam") or _moment(row.get("decision_at"))
                lines.append(f"{pair}, bot {bot_id}: huidige Paper-check van "
                             f"{at or 'onbekend bronmoment'}, zonder gekoppeld rapportbesluit.")
    for pair in named_pairs:
        if pair.split("/", 1)[0] in symbols and not any(
            str(bot.get("trading_pair") or "").upper() == pair for bot in bots
            if isinstance(bot, dict) and bot.get("is_live") is False
        ):
            lines.append(f"{pair}: in deze rapportmomentopname is geen gekoppelde Paper-bot "
                         "vastgelegd. Een bot voor een ander BTC-paar hoort hier niet bij.")
    lines.append("Een latere botcheck wijzigt het opgeslagen dagrapport niet; "
                 "dit antwoord plaatst geen order en wijzigt geen bot.")
    return "\n".join(lines)


def render_selected_paper_feed_decision(
    result: dict[str, Any], *, symbol: str, expected_source_at: str | None = None,
) -> str:
    """Answer a clicked Paper card only from its owner-verified decision row."""
    data, reason = _read(result, "read_review_history")
    if data is None:
        return (f"Ik kan het geselecteerde historische Paper-botbesluit voor {symbol} "
                f"nu niet verifiëren ({reason}). Probeer de kaart later opnieuw.")
    selected = data.get("selected_feed_decision")
    if not isinstance(selected, dict):
        return (f"Ik kan het geselecteerde historische Paper-botbesluit voor {symbol} "
                "niet aan een opgeslagen beslissing koppelen. Ik gebruik geen later botbesluit als vervanging.")
    action = str(selected.get("action") or "").lower()
    at = _moment(selected.get("decision_at"))
    if expected_source_at:
        try:
            expected = datetime.fromisoformat(str(expected_source_at).replace("Z", "+00:00"))
            actual = datetime.fromisoformat(str(selected.get("decision_at")).replace("Z", "+00:00"))
            if expected.tzinfo is None or actual.tzinfo is None or abs((actual - expected).total_seconds()) > 2:
                raise ValueError("selected_feed_source_mismatch")
        except (TypeError, ValueError):
            return (f"Het geselecteerde Paper-botbesluit voor {symbol} hoort niet bij "
                    "het bronmoment van de aangeklikte kaart. Ik gebruik geen later besluit als vervanging.")
    if action not in {"hold", "houd_vast", "buy", "sell"} or not at:
        return (f"Het geselecteerde Paper-botbesluit voor {symbol} mist een "
                "controleerbare actie of tijd. Ik kan de uitkomst niet bevestigen.")
    label = str(selected.get("pair") or selected.get("symbol") or symbol).upper()
    action_text = {"hold": "wachten (hold)", "houd_vast": "wachten (hold)", "buy": "kopen (buy)",
                   "sell": "verkopen (sell)"}[action]
    if selected.get("paper_executed") is True:
        amount = _number(selected.get("filled_amount_eur"))
        execution = (f"De gekoppelde Paper-order is als gevuld opgeslagen"
                     + (f" voor €{amount}" if amount else "") + ".")
    else:
        execution = "Bij dit besluit is geen gevulde Paper-order bevestigd."
    reasons = selected.get("reasons")
    saved_reasons = []
    seen_reasons = set()
    for reason in reasons if isinstance(reasons, list) else []:
        if not isinstance(reason, str) or not reason.strip():
            continue
        cleaned = reason.strip()[:240].rstrip(".!? ")
        normalized = cleaned.casefold()
        if normalized in seen_reasons:
            continue
        seen_reasons.add(normalized)
        saved_reasons.append(cleaned)
        if len(saved_reasons) == 2:
            break
    reason_text = (" Opgeslagen beoordelingsreden: " + "; ".join(saved_reasons) + "."
                   if saved_reasons else " De opgeslagen beslissing bevat geen controleerbare reden.")
    if action == "sell" and selected.get("paper_executed") is True:
        next_step = (" De gevulde order alleen bewijst niet dat de hele positie is gesloten; "
                     "controleer de resterende hoeveelheid in je Paper-portefeuille. "
                     "Reflectievraag: kwam deze verkoop overeen met je vooraf opgeslagen uitstapregel?")
    elif action in {"hold", "houd_vast"}:
        next_step = (" Controleer vóór een volgende beoordeling de actuele score en de "
                     "opgeslagen botvoorwaarden; dit historische besluit is geen nieuwe handelsinstructie.")
    else:
        next_step = " Controleer de huidige Paper-positie en de opgeslagen botvoorwaarden vóór een volgende actie."
    revision_note = (" De huidige botrij is later bijgewerkt; dit antwoord gebruikt de "
                     "opgeslagen momentopname van de aangeklikte kaart."
                     if selected.get("source_row_changed") is True else "")
    return (f"Het geselecteerde historische Paper-botbesluit voor {label} was "
            f"{action_text} op {at} (Europe/Amsterdam). {execution} "
            f"Een latere botcontrole verandert dit opgeslagen besluit niet."
            f"{reason_text}{next_step}{revision_note}")


def render_selected_paper_position_risk(result: dict[str, Any], *, symbol: str) -> str:
    """Explain one owner-scoped risk card from its historical and current reads."""
    data, reason = _read(result, "read_selected_paper_position_risk")
    if data is None:
        return f"Ik kan het positierisico voor {symbol} nu niet verifiëren ({reason})."
    historical = data.get("historical") or {}
    current = data.get("current") or {}
    if not isinstance(historical, dict) or not isinstance(current, dict):
        return f"Ik kan het positierisico voor {symbol} nu niet verifiëren."
    if str(current.get("symbol") or "").upper() != symbol:
        return f"Ik kan de actuele Paper-positie voor {symbol} niet aan deze kaart koppelen."
    pair = str(current.get("trading_pair") or symbol).upper()
    if pair != symbol and not pair.startswith(f"{symbol}/"):
        return f"Ik kan de actuele Paper-positie voor {symbol} niet aan deze kaart koppelen."
    limit = _number(current.get("limit_pct"))
    exposure = _number(current.get("exposure_pct"))
    at = _moment(current.get("valuation_as_of"))
    status = current.get("status")
    if status == "above_saved_limit" and limit is not None and exposure is not None and at:
        return (f"Voor je {pair} Paper-bot is de huidige positieconcentratie {exposure}% "
                f"op het waarderingsmoment {at} (Europe/Amsterdam). De opgeslagen limiet "
                f"is {limit}%; die is overschreden. Controleer de actuele koers- en FX-bron "
                "en de botlimiet voordat je een beslissing neemt. Ik wijzig niets en plaats geen order.")
    if status == "within_limit" and limit is not None and exposure is not None and at:
        return (f"De melding voor {pair} was historisch. Op het huidige waarderingsmoment "
                f"{at} (Europe/Amsterdam) is de positieconcentratie {exposure}% bij een "
                f"opgeslagen limiet van {limit}%; die limiet is nu niet overschreden. "
                "Controleer bij een volgende beoordeling de actuele koers- en FX-bron. "
                "Ik wijzig niets en plaats geen order.")
    old_limit = _number(historical.get("limit_pct"))
    limit_text = f" De kaart noemde destijds een limiet van {old_limit}%." if old_limit else ""
    return (f"De actuele positieconcentratie voor {pair} kan ik niet verifiëren: "
            f"er is geen bruikbare, gedateerde Paper-waardering beschikbaar.{limit_text} "
            "Controleer de koers- en FX-bron en probeer daarna opnieuw. "
            "Ik wijzig niets en plaats geen order.")


def render_paper_exit_position_status(result: dict[str, Any], *, symbol: str) -> str:
    """Verify whether a historical Paper exit left a current owner-held position."""
    portfolio, reason = _read(result, "read_portfolio")
    if portfolio is None or portfolio.get("environment") != "paper":
        return (f"Ik kan de huidige Paper-positie voor {symbol} niet verifiëren "
                f"({reason or 'Paper-portefeuille niet beschikbaar'}).")
    rows = [row for row in portfolio.get("bots") or []
            if isinstance(row, dict) and row.get("is_live") is False
            and str(row.get("symbol") or "").upper() == symbol]
    if len(rows) != 1:
        return (f"Ik kan de historische Paper-exit voor {symbol} niet eenduidig "
                "aan één huidige botpositie koppelen.")
    try:
        quantity = Decimal(str(rows[0].get("position_qty")))
    except (InvalidOperation, TypeError, ValueError):
        quantity = None
    at = _moment(portfolio.get("read_at"))
    if quantity is None or not quantity.is_finite() or quantity < 0 or not at:
        return f"Ik kan de resterende Paper-hoeveelheid voor {symbol} nu niet verifiëren."
    amount = format(quantity.normalize(), "f").replace(".", ",")
    state = ("geen open positie meer" if quantity == 0
             else f"nog {amount} {symbol} open")
    return (f"Volgens de huidige Paper-portefeuille heeft deze {symbol}-bot {state} "
            f"op {at} (Europe/Amsterdam). De historische gevulde verkoop alleen "
            "bewijst geen volledige sluiting; deze uitgelezen hoeveelheid is de huidige stand. "
            "Ik plaats geen order.")


def render_report_and_quote_times(
    result: dict[str, Any], *, symbol: str, quote_currency: str,
) -> str:
    report, report_reason = _read(result, "read_latest_report")
    market, market_reason = _read(result, "read_market_snapshot")
    pair = f"{symbol}/{quote_currency}"
    if report is None or market is None:
        missing = []
        if report is None:
            missing.append(f"dagrapport: {report_reason}")
        if market is None:
            missing.append(f"huidige koersbron: {market_reason}")
        return "Ik kan de bronmomenten nog niet volledig vergelijken (" + "; ".join(missing) + ")."
    assets = (report.get("score_source_snapshot") or {}).get("assets") or []
    matched = [row for row in assets if isinstance(row, dict)
               and str(row.get("symbol") or "").upper() == symbol
               and str(row.get("pair") or row.get("display_symbol") or "").upper() == pair]
    if len(matched) != 1 or str(market.get("symbol") or "").upper() != symbol \
            or str(market.get("quote_currency") or "").upper() != quote_currency:
        return f"Ik kan de rapport- en koersbronnen voor {pair} niet eenduidig koppelen."
    snapshot = matched[0].get("market_snapshot") or {}
    generated = _moment(report.get("generated_at"))
    historical = _moment(snapshot.get("as_of") or snapshot.get("source_observed_at"))
    current = _moment(market.get("source_observed_at_utc") or market.get("source_observed_at"))
    if not all((generated, historical, current)):
        return f"Voor {pair} ontbreekt een controleerbaar rapport- of koersbronmoment."
    return (f"Dagrapport {report.get('report_date')} voor {pair}: gegenereerd op {generated}. "
            f"De koersbron in dat rapport is historisch: {historical}. "
            f"De nieuwste afzonderlijk gelezen {pair}-koersbron is {current} "
            f"(Europe/Amsterdam); dit is de huidige beschikbare meting, "
            f"niet het bronmoment van het opgeslagen rapport.")


def render_account_market_report_facts(result: dict[str, Any], *, symbol: str) -> str:
    """Compare a saved plan, Paper decision and two dated prices from one owner read.

    A stale market row is useful planning context, but never an execution quote.
    Every requested source must be present and internally consistent before a
    numeric comparison is shown.
    """
    required = {
        "read_active_setup": "setups",
        "read_linked_strategy": "strategies",
        "read_asset_scores": "daily_scores_and_source_indicators",
        "read_market_snapshot": "market_data",
        "read_latest_report": "daily_reports",
        "read_bot_status": "bot_configs",
    }
    rows: dict[str, dict[str, Any]] = {}
    for row in result.get("results") or []:
        if not isinstance(row, dict) or row.get("scope") not in required:
            continue
        scope = row["scope"]
        if (row.get("status") != "completed" or row.get("source") != required[scope]
                or not isinstance(row.get("data"), dict)):
            return f"Ik kan de opgeslagen bronnen voor {symbol} niet volledig verifiëren."
        if scope in rows and rows[scope] != row["data"]:
            return f"Ik kan de opgeslagen bronnen voor {symbol} niet eenduidig koppelen."
        rows[scope] = row["data"]
    missing = [scope for scope in required if scope not in rows]
    if missing:
        return (f"Ik kan de vergelijking voor {symbol} niet afronden: "
                f"de bron {', '.join(missing)} ontbreekt.")

    setup, strategy = rows["read_active_setup"], rows["read_linked_strategy"]
    scores, market = rows["read_asset_scores"], rows["read_market_snapshot"]
    report, bot = rows["read_latest_report"], rows["read_bot_status"]
    if (any(str(data.get("symbol") or "").upper() != symbol
            for data in (setup, strategy, scores, market))
            or not isinstance(setup.get("setup_id"), int)
            or strategy.get("setup_id") != setup["setup_id"]
            or not isinstance(strategy.get("strategy_id"), int)
            or not isinstance(bot.get("bot_id"), int)
            or (bot.get("strategy_id") is not None
                and bot.get("strategy_id") != strategy["strategy_id"])
            or (bot.get("symbol") is not None
                and str(bot["symbol"]).upper() != symbol)
            or bot.get("is_live") is not False):
        return f"Ik kan het plan, de strategie en de Paper-bot voor {symbol} niet eenduidig koppelen."
    score_values = scores.get("reported_scores")
    if not isinstance(score_values, dict) or not any(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in score_values.values()
    ):
        return f"Ik heb het plan voor {symbol} gelezen, maar de opgeslagen score ontbreekt."
    assets = (report.get("score_source_snapshot") or {}).get("assets") or []
    matching = [row for row in assets if isinstance(row, dict)
                and str(row.get("symbol") or "").upper() == symbol]
    if len(matching) != 1 or not isinstance(matching[0].get("market_snapshot"), dict):
        return f"Ik kan de historische rapportkoers voor {symbol} niet eenduidig koppelen."
    old = matching[0]["market_snapshot"]
    decision = bot.get("latest_decision")
    if (not isinstance(decision, dict) or not decision.get("reason_code")
            or str(market.get("quote_currency") or "").upper() != "USD"
            or str(old.get("quote_currency") or "").upper() != "USD"):
        return f"Ik kan de Paper-botreden en de twee USD-koersen voor {symbol} niet verifiëren."

    def utc_instant(value: Any) -> datetime | None:
        try:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None

    current_at = utc_instant(market.get("source_observed_at_utc") or market.get("source_observed_at"))
    old_at = utc_instant(old.get("as_of") or old.get("source_observed_at_utc"))
    try:
        current_price = Decimal(str(market.get("price")))
        old_price = Decimal(str(old.get("price")))
    except (InvalidOperation, TypeError, ValueError):
        return f"Ik kan de twee koerswaarden voor {symbol} niet verifiëren."
    if (not current_at or not old_at or current_at <= old_at
            or not current_price.is_finite() or not old_price.is_finite()
            or current_price <= 0 or old_price <= 0):
        return f"Ik kan de volgorde van de gedateerde koersbronnen voor {symbol} niet verifiëren."

    benchmark = _number(scores.get("benchmark_score"))
    score_text = (f"De opgeslagen benchmarkscore is {benchmark}/100. " if benchmark is not None
                  else "Er is nog geen complete benchmarkscore; deelmetingen zijn wel opgeslagen. ")

    def amount(value: Decimal) -> str:
        return format(value, ".2f").replace(".", ",")

    def clock(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M UTC")

    reason_text = ("een te oude marktprijs voor een Paper-order"
                   if decision["reason_code"] == "market_price_stale"
                   else "een opgeslagen blokkadereden die ik hier niet kan duiden")
    return (
        f"Ik heb je opgeslagen {symbol}-setup en gekoppelde strategie gelezen. {score_text}"
        f"De nieuwste beschikbare {symbol}-koersbron is USD {amount(current_price)} "
        f"met bronmoment {clock(current_at)}. "
        f"Het oudere opgeslagen dagrapport bevatte historisch USD {amount(old_price)} "
        f"met bronmoment {clock(old_at)}. "
        f"De Paper-bot vermeldt {reason_text}; die laatst bekende koers is geen "
        "geverifieerde uitvoeringskoers. Ik plaats geen order."
    )


def _requested_technical_names(message: str, names: set[str]) -> list[str]:
    """Match measured indicator names, including generic moving-average phrasing."""
    selected = []
    for name in sorted(names):
        normalized = str(name).casefold().replace("-", "_").replace(" ", "_")
        parts = normalized.split("_")
        label = indicator_display_name(name).casefold()
        normalized_pattern = re.escape(normalized).replace("_", r"[\s_-]*")
        label_pattern = re.escape(label).replace(r"\ ", r"[\s_-]*")
        patterns = [
            rf"\b{normalized_pattern}\b",
            rf"\b{label_pattern}\b",
        ]
        if len(parts) >= 2 and parts[1].isdigit():
            prefix, period = parts[0], parts[1]
            patterns.append(rf"\b{re.escape(prefix)}[\s_-]*{period}\b")
            if prefix == "ma":
                patterns.append(rf"\b{period}[\s_-]*(?:daags?|dagen|day)[\s_-]+(?:gemiddelde|moving[\s_-]+average)\b")
        elif len(parts[0]) >= 3:
            patterns.append(rf"\b{re.escape(parts[0])}\b")
        if any(re.search(pattern, message, re.I) for pattern in patterns):
            selected.append(name)
    return selected


def mentions_technical_indicator(message: str) -> bool:
    """Recognize the technical domain from language or the active catalog."""
    if re.search(r"\b(?:indicator\w*|technisch\w*|gemiddelde|moving[\s_-]+average)\b", message, re.I):
        return True
    names = {str(item["name"]) for item in get_active_technical_indicator_definitions()}
    return bool(_requested_technical_names(message, names))


def is_report_technical_comparison_request(message: str) -> bool:
    """A measured-report read, even when the user says what Analyse can read."""
    return bool(
        re.search(r"\b(?:dagrapport|ochtendrapport|rapport|report)\b", message, re.I)
        and re.search(r"\b(?:analyse|nu|actuel\w*|huidig\w*|nieuwste|laatste|naast|vergelijk\w*)\b", message, re.I)
        and re.search(r"\b(?:naast|vergelijk\w*|verhoud\w*|verschil\w*|beide|revisi\w*|moment\w*|waarden?)\b", message, re.I)
        and mentions_technical_indicator(message)
    )


def render_report_and_technical_read(
    result: dict[str, Any], *, symbol: str, message: str, pair: str | None = None,
) -> str:
    """Compare saved report evidence with a separately timed owner-scoped read."""
    report, report_reason = _read(result, "read_latest_report")
    technical, technical_reason = _read(result, "read_technical_snapshot")
    if report is None or technical is None:
        missing = []
        if report is None:
            missing.append(f"dagrapport: {report_reason}")
        if technical is None:
            missing.append(f"huidige indicatoren: {technical_reason}")
        return "Ik kan het rapport en de huidige indicatormeting nog niet volledig vergelijken (" + "; ".join(missing) + ")."
    assets = (report.get("score_source_snapshot") or {}).get("assets") or []
    matched = [row for row in assets if isinstance(row, dict)
               and str(row.get("symbol") or "").upper() == symbol
               and (pair is None or str(row.get("pair") or row.get("display_symbol") or "").upper() == pair)]
    if len(matched) != 1 or str(technical.get("symbol") or "").upper() != symbol \
            or (pair is not None and str(technical.get("pair") or "").upper() != pair):
        return f"Ik kan de rapport- en indicatorbronnen voor {pair or symbol} niet eenduidig koppelen."
    indicator_evidence = matched[0].get("verified_indicator_evidence") or {}
    if not isinstance(indicator_evidence, dict):
        indicator_evidence = {}
    raw_report_items = indicator_evidence.get("technical") or {}
    if not isinstance(raw_report_items, dict):
        raw_report_items = {}
    report_items = {
        str(name).casefold(): item
        for name, item in raw_report_items.items()
        if isinstance(item, dict)
    }
    current_items = {
        str(item.get("indicator") or "").casefold(): item
        for item in technical.get("items") or [] if isinstance(item, dict)
    }
    common = set(report_items).intersection(current_items)
    selected = _requested_technical_names(message, common)
    if not selected and len(common) == 1:
        selected = list(common)
    if not selected:
        if not common:
            return f"Voor {pair or symbol} kan ik geen technische indicator met zowel rapport- als huidige meetwaarde verifiëren."
        labels = ", ".join(indicator_display_name(name) for name in sorted(common))
        return f"Welke indicator van {pair or symbol} bedoel je: {labels}?"
    generated = _moment(report.get("generated_at"))
    read_at = _moment(technical.get("read_at"))
    if not generated or not read_at:
        return f"Voor {pair or symbol} ontbreekt een controleerbaar rapport- of uitleesmoment."
    comparisons = []
    for name in selected:
        historical = report_items.get(name)
        current = current_items.get(name)
        if not isinstance(historical, dict) or not isinstance(current, dict):
            continue
        old_value, new_value = _number(historical.get("value")), _number(current.get("value"))
        old_source = _moment(historical.get("source_observed_at"))
        new_source = _moment(current.get("source_observed_at"))
        if not all((old_value, new_value, old_source, new_source)):
            continue
        conclusion = (
            "Het bronmoment is gelijk; dit bewijst geen nieuwe candle. De latere uitlezing kan een herziene "
            "meting tonen, maar de oorzaak van het verschil en welke waarde wiskundig juist is, zijn hiermee niet bewezen."
            if old_source == new_source and old_value != new_value else
            "Beide uitlezingen hebben hetzelfde bronmoment en dezelfde waarde."
            if old_source == new_source else
            "De bronmomenten verschillen; dit zijn metingen van verschillende candles."
        )
        comparisons.append(
            f"{indicator_display_name(name)}: rapportwaarde {old_value} (bron {old_source}); "
            f"huidige uitlezing {new_value} (bron {new_source}). {conclusion}"
        )
    if not comparisons:
        return f"Voor {pair or symbol} ontbreken controleerbare waarden of bronmomenten voor de bedoelde indicator."
    return (f"Dagrapport {report.get('report_date')} voor {pair or symbol}: opgesteld op {generated}. "
            f"De huidige indicatoren zijn afzonderlijk uitgelezen op {read_at} (Europe/Amsterdam). "
            + " ".join(comparisons))


def render_latest_quote(
    result: dict[str, Any], *, symbol: str, quote_currency: str | None = None,
    user_time_zone: str | None = None,
) -> str:
    market, reason = _read(result, "read_market_snapshot")
    if market is None:
        return f"Ik kan de laatst beschikbare {symbol}-koersbron nu niet lezen ({reason})."
    if str(market.get("symbol") or "").upper() != symbol or (
        quote_currency and str(market.get("quote_currency") or "").upper() != quote_currency
    ):
        return f"De gelezen koersbron hoort niet bij {symbol}."
    price = _number(market.get("price"))
    at, zone_name = _moment_in_zone(
        market.get("source_observed_at_utc") or market.get("source_observed_at"), user_time_zone,
    )
    unit = str(market.get("quote_currency") or "")
    provider = str(market.get("price_provider") or "onbekend")
    if not price or not at or not unit:
        return f"De laatst beschikbare {symbol}-koers mist prijs, valuta of bronmoment."
    # Outside regular New York hours the main US session is closed. During
    # those hours a holiday or halt cannot be inferred from a price row.
    ny_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    regular_session = ny_now.weekday() < 5 and (
        (ny_now.hour, ny_now.minute) >= (9, 30)
        and (ny_now.hour, ny_now.minute) < (16, 0)
    )
    asset_class = str((DEFAULT_ASSET_CATALOG.get(symbol) or {}).get("asset_class") or "").lower()
    if asset_class == "crypto":
        session = " Cryptohandel kent geen reguliere beurssluiting; dit is de laatst beschikbare meting."
    elif asset_class == "stock" and not regular_session:
        session = " De reguliere Amerikaanse beurssessie is nu gesloten; dit is de laatst beschikbare koers."
    else:
        session = " De beursstatus is niet in deze koersmeting vastgelegd."
    label = f"{symbol}/{quote_currency}" if quote_currency else symbol
    return (f"De laatst beschikbare {label}-koers is {price} {unit} van {provider}, "
            f"met bronmoment {at} ({zone_name}).{session}")


def render_portfolio_read_time(result: dict[str, Any]) -> str:
    portfolio, reason = _read(result, "read_portfolio")
    if portfolio is None:
        return f"Ik kan het Paper-portefeuilleuitleesmoment nu niet lezen ({reason})."
    at = _moment(portfolio.get("read_at"))
    if not at:
        return "De Paper-portefeuillebron bevat geen controleerbaar uitleesmoment."
    return (f"Ik heb je Paper-portefeuille uitgelezen op {at} (Europe/Amsterdam). "
            "Dit is het uitleesmoment van de portefeuille, niet het bronmoment van een koers.")
