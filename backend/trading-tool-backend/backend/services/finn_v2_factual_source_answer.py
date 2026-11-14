"""Answer narrow source-fact questions from typed owner-scoped reads."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

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


def render_bot_decision(
    result: dict[str, Any], *, symbol: str, paper: bool | None,
    pair: str | None = None,
) -> str:
    data, reason = _read(result, "read_review_history")
    if data is None:
        return f"Ik kan de opgeslagen botbesluiten voor {symbol} nu niet lezen ({reason})."
    decisions = [row for row in data.get("latest_bot_decisions") or []
                 if isinstance(row, dict)
                 and str(row.get("symbol") or "").upper().split("/", 1)[0] == symbol
                 and (pair is None or str(row.get("pair") or row.get("symbol") or "").upper() == pair)
                 and (paper is None or bool(row.get("is_live")) is paper)]
    if not decisions:
        return f"Ik vind geen opgeslagen besluit voor een {symbol}-bot in dit account."
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
    status = {"planned": "besluit opgeslagen", "completed": "besluit afgerond",
              "failed": "besluit mislukt"}.get(str(row.get("persistence_status") or ""),
                                          "opslagstatus onbekend")
    try:
        instant = datetime.fromisoformat(str(row["decision_at"]).replace("Z", "+00:00"))
        historical = instant.astimezone(timezone.utc) < datetime.now(timezone.utc)
    except (TypeError, ValueError):
        historical = True
    kind = "historische opgeslagen beoordeling" if historical else "opgeslagen beoordeling"
    label = pair or symbol
    return (f"Het laatst opgeslagen besluit van je {label} {mode}-bot is {action_text}, "
            f"op {at} (Europe/Amsterdam). Dit is een {kind}, geen actuele "
            f"marktbeoordeling. Opslagstatus: {status}.")


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
