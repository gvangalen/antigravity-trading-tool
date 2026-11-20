"""Answer narrow source-fact questions from typed owner-scoped reads."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from zoneinfo import ZoneInfo

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


def _number(value: Any) -> str | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return format(amount.normalize(), "f") if amount.is_finite() else None


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
    referenced_minute: bool = False,
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
    at = _moment(row.get("decision_at"))
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
            f"op {at} (Europe/Amsterdam). Dit is een {kind}, geen actuele "
            f"marktbeoordeling. Opslagstatus: {status}.{safety_text}")


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
        r"\b(?:dagrapport|ochtendrapport|rapport)\s+(?:van|om|dat\s+om)\s+([01]?\d|2[0-3]):([0-5]\d)\b",
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
        return (f"Het opgeslagen dagrapport voor {symbol} heeft niet het genoemde "
                f"uitleesmoment {requested_report_clock.group(1)}:{requested_report_clock.group(2)}. "
                + (f"Ook de genoemde {symbol}-botcheck is niet gevonden. " if missing_check else "")
                + "Ik kan de botredenen daarom niet betrouwbaar vergelijken.")
    historical = [row for row in history.get("referenced_bot_decisions") or []
                  if isinstance(row, dict) and str(row.get("symbol") or "").upper().split("/", 1)[0] == symbol]
    if len(historical) != 1:
        return (f"Ik kan de bedoelde opgeslagen {symbol}-botcheck niet eenduidig aan één bot koppelen of hij ontbreekt. "
                "Daarom kan ik de twee botredenen niet betrouwbaar vergelijken. "
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
    report_reason = str(report_decision.get("reason") or "").strip()
    check_reason = str(check.get("safety_reason") or "").strip()
    lines = [f"Ik heb de opgeslagen besluiten van dezelfde {symbol}-bot vergeleken."]
    lines.append(
        f"Het dagrapport{f' van {report_generated}' if report_generated else ''} is een momentopname. "
        f"Het botbesluit daarin is van {report_at or 'een onbekend bronmoment'}: "
        f"{report_reason or 'geen controleerbare reden opgeslagen'}."
    )
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
    saved_reasons = [str(reason).strip()[:240] for reason in reasons[:2]
                     if isinstance(reason, str) and reason.strip()] if isinstance(reasons, list) else []
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
) -> str:
    market, reason = _read(result, "read_market_snapshot")
    if market is None:
        return f"Ik kan de laatst beschikbare {symbol}-koersbron nu niet lezen ({reason})."
    if str(market.get("symbol") or "").upper() != symbol or (
        quote_currency and str(market.get("quote_currency") or "").upper() != quote_currency
    ):
        return f"De gelezen koersbron hoort niet bij {symbol}."
    price = _number(market.get("price"))
    at = _moment(market.get("source_observed_at_utc") or market.get("source_observed_at"))
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
            f"met bronmoment {at} (Europe/Amsterdam).{session}")


def render_portfolio_read_time(result: dict[str, Any]) -> str:
    portfolio, reason = _read(result, "read_portfolio")
    if portfolio is None:
        return f"Ik kan het Paper-portefeuilleuitleesmoment nu niet lezen ({reason})."
    at = _moment(portfolio.get("read_at"))
    if not at:
        return "De Paper-portefeuillebron bevat geen controleerbaar uitleesmoment."
    return (f"Ik heb je Paper-portefeuille uitgelezen op {at} (Europe/Amsterdam). "
            "Dit is het uitleesmoment van de portefeuille, niet het bronmoment van een koers.")
