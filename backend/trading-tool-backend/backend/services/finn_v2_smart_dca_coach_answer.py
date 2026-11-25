"""Explain one saved Smart DCA curve from coherent, owner-scoped read evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _display(value: Decimal, *, money: bool = False) -> str:
    if money:
        value = value.quantize(Decimal("0.01"))
    return format(value.normalize(), "f").replace(".", ",")


def _moment(value: Any, user_time_zone: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        zone = ZoneInfo(user_time_zone) if user_time_zone else timezone.utc
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return None
    return parsed.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")


def smart_dca_identity_question(pair: str) -> str:
    return (
        f"Welke opgeslagen Smart DCA-setup voor {pair.upper()} bedoel je precies? "
        "Noem de setupnaam; dan lees ik de gekoppelde strategie, score en staffel opnieuw."
    )


def smart_dca_source_unavailable_text() -> str:
    return "Ik kan de actuele score, opgeslagen staffel of botkoppeling voor deze Smart DCA nu niet volledig verifiëren."


def saved_smart_dca_identity_matched(
    tool_trace: tuple[dict[str, Any], ...], *, message: str, pair: str,
    selected_setup_name: str | None = None,
) -> bool:
    """Check only the named, owner-read setup and linked strategy identity."""
    setups = [item.get("data") for call in tool_trace if call.get("name") == "get_active_plan_and_strategy"
              for item in (call.get("result") or {}).get("results") or []
              if item.get("scope") == "read_active_setup" and item.get("status") == "completed"]
    strategies = [item.get("data") for call in tool_trace if call.get("name") == "get_active_plan_and_strategy"
                  for item in (call.get("result") or {}).get("results") or []
                  if item.get("scope") == "read_linked_strategy" and item.get("status") == "completed"]
    if len(setups) != 1 or len(strategies) != 1 or not all(isinstance(row, dict) for row in (*setups, *strategies)):
        return False
    setup, strategy = setups[0], strategies[0]
    setup_name = str(setup.get("name") or "").strip()
    strategy_name = str(strategy.get("name") or "").strip()
    if (not setup_name or not isinstance(setup.get("setup_id"), int)
            or setup.get("setup_id") != strategy.get("setup_id")
            or str(setup.get("pair") or "").upper() != pair.upper()
            or str(strategy.get("pair") or "").upper() != pair.upper()
            or (selected_setup_name is not None and setup_name.casefold() != selected_setup_name.strip().casefold())
            or (selected_setup_name is None and not re.search(
                rf"(?<!\w){re.escape(setup_name)}(?!\w)", message, re.I,
            ))):
        return False
    if (re.search(rf"\b(?:niet|not)\b.{{0,40}}(?<!\w){re.escape(setup_name)}(?!\w)", message, re.I)
            or re.search(r"\b(?:ander|andere|other)\s+(?:plan|setup|strategie|strategy)\b", message, re.I)):
        return False
    explicit_strategy = re.search(
        r"\bstrategie\s+(?:genaamd\s+|met\s+de\s+naam\s+)?"
        r"(?!(?:is|heeft|kan|van|voor|met|die|en|zonder|bij|aan|wordt|welke)\b"
        r"|(?:al\s+)?(?:een\s+)?(?:(?:paper|live)[ -])?bot\b)([^.,;?]+)",
        message, re.I,
    )
    return not (explicit_strategy and strategy_name
                and not re.search(rf"(?<!\w){re.escape(strategy_name)}(?!\w)", explicit_strategy.group(1), re.I))


def render_saved_smart_dca_coach_answer(
    tool_trace: tuple[dict[str, Any], ...], *, message: str, pair: str, locale: str,
    user_time_zone: str | None, selected_setup_name: str | None = None,
) -> str | None:
    """Return facts only when the selected setup, strategy, score and bot scope agree."""
    if not locale.lower().startswith("nl") or not pair:
        return None
    rows: dict[str, dict[str, Any]] = {}
    for call in tool_trace:
        if not isinstance(call, dict) or call.get("name") != "get_active_plan_and_strategy":
            continue
        for item in (call.get("result") or {}).get("results") or []:
            if not isinstance(item, dict) or item.get("scope") not in {
                "read_active_setup", "read_linked_strategy", "read_asset_scores",
                "read_linked_bot", "read_bot_status",
            }:
                continue
            scope = item["scope"]
            if scope in rows and rows[scope] != item:
                return None
            rows[scope] = item
    if not {"read_active_setup", "read_linked_strategy", "read_asset_scores"} <= rows.keys():
        return None
    if any(rows[scope].get("status") != "completed" for scope in (
        "read_active_setup", "read_linked_strategy", "read_asset_scores",
    )):
        return None
    setup, strategy, score = (rows[scope].get("data") for scope in (
        "read_active_setup", "read_linked_strategy", "read_asset_scores",
    ))
    if not all(isinstance(data, dict) for data in (setup, strategy, score)):
        return None
    setup_id = setup.get("setup_id")
    strategy_id = strategy.get("strategy_id")
    symbol, quote = pair.upper().split("/", 1) if pair.count("/") == 1 else ("", "")
    if (not isinstance(setup_id, int) or not isinstance(strategy_id, int)
            or setup_id <= 0 or strategy_id <= 0 or strategy.get("setup_id") != setup_id
            or str(setup.get("pair") or "").upper() != pair.upper()
            or str(strategy.get("pair") or "").upper() != pair.upper()
            or str(score.get("symbol") or "").upper() != symbol
            or str(score.get("quote_currency") or "").upper() != quote
            or score.get("market_id") != setup.get("market_id")
            or str(setup.get("setup_type") or "").lower() != "dca"
            or strategy.get("dca_amount_mode") != "score_bands"
            or strategy.get("score_source") != "benchmark_score"
            or str(strategy.get("currency") or "").upper() != "EUR"):
        return None
    setup_name = str(setup.get("name") or "").strip()
    if not saved_smart_dca_identity_matched(
        tool_trace, message=message, pair=pair, selected_setup_name=selected_setup_name,
    ):
        return None
    current = _decimal(score.get("benchmark_score"))
    base = _decimal(strategy.get("base_amount"))
    score_day = str(score.get("as_of") or "")
    requested_base = re.search(
        r"\b(?:op\s+basis\s+van|basisbedrag(?:\s+van)?)\s*€\s*(\d+(?:[.,]\d+)?)",
        message, re.I,
    )
    if requested_base and base is not None:
        user_base = _decimal(requested_base.group(1).replace(",", "."))
        if user_base is not None and user_base != base:
            return (
                f"Je noemt €{_display(user_base, money=True)} als basisbedrag, maar de "
                f"opgeslagen strategie bij {setup_name} voor {pair.upper()} gebruikt "
                f"€{_display(base, money=True)}. Ik reken de gevraagde scorevoorbeelden "
                "niet met een ander bedrag door. Bedoel je het opgeslagen basisbedrag "
                "of wil je een afzonderlijk wijzigingsvoorstel?"
            )
    if (score.get("source_status") != "available" or current is None or base is None
            or not 0 <= current <= 100 or base <= 0
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", score_day)):
        return None
    bands = strategy.get("dca_score_bands")
    if not isinstance(bands, list) or not bands:
        return None
    matching: list[tuple[Decimal, Decimal | None, Decimal, Decimal]] = []
    verified_bands: list[tuple[Decimal, Decimal | None, Decimal, Decimal]] = []
    previous_upper: Decimal | None = None
    percentages: list[Decimal] = []
    for index, band in enumerate(bands):
        if not isinstance(band, dict) or band.get("amount_status") != "hypothetical_before_exposure_not_purchase":
            return None
        lower = _decimal(band.get("from_score_inclusive"))
        upper = _decimal(band.get("to_score_exclusive")) if band.get("to_score_exclusive") is not None else None
        percent = _decimal(band.get("percent_of_base"))
        amount = _decimal(band.get("planned_amount"))
        if lower is None or percent is None or amount is None or lower < 0 or percent < 0 or amount < 0:
            return None
        if (index == 0 and lower != 0) or (index > 0 and lower != previous_upper):
            return None
        if upper is not None and upper <= lower:
            return None
        if upper is None and index != len(bands) - 1:
            return None
        previous_upper = upper
        percentages.append(percent)
        verified_bands.append((lower, upper, percent, amount))
        if (upper is None or current < upper) and current >= lower:
            matching.append((lower, upper, percent, amount))
    if len(matching) != 1:
        return None
    lower, upper, percent, amount = matching[0]
    # The saved curve engine rounds the planned amount; tolerate only cents.
    if abs(amount - base * percent / 100) > Decimal("0.01"):
        return None
    source = _moment(score.get("oldest_indicator_source_observed_at"), user_time_zone)
    if not source:
        return None
    bot_rows = [rows[key] for key in ("read_linked_bot", "read_bot_status") if key in rows]
    if len(bot_rows) != 2:
        return None
    if all(row.get("status") == "unavailable" and row.get("reason") == "bot_not_resolved" for row in bot_rows):
        bot_text = "Aan deze strategie is geen bot gekoppeld."
    elif all(row.get("status") == "completed" and isinstance(row.get("data"), dict) for row in bot_rows):
        linked_bot = rows["read_linked_bot"]["data"]
        bot_status = rows["read_bot_status"]["data"]
        linked_id = linked_bot.get("bot_id")
        if (linked_bot.get("strategy_id") != strategy_id
                or not isinstance(linked_id, int) or isinstance(linked_id, bool)
                or linked_id <= 0 or bot_status.get("bot_id") != linked_id):
            return None
        if (not isinstance(linked_bot.get("is_live"), bool)
                or bot_status.get("is_live") is not linked_bot["is_live"]):
            return None
        mode = "Live" if linked_bot["is_live"] else "Paper"
        bot_text = (f"Aan deze strategie is een bot gekoppeld ({mode}); controleer diens "
                    "afzonderlijke beslissing en uitvoeringsvoorwaarden.")
    else:
        return None
    range_text = f"{_display(lower)}–{_display(upper)}" if upper is not None else f"vanaf {_display(lower)}"
    if all(left >= right for left, right in zip(percentages, percentages[1:])) and percentages[0] > percentages[-1]:
        curve_direction = "De lage scorebanden hebben in deze curve een hoger percentage dan de hoge. "
    elif all(left <= right for left, right in zip(percentages, percentages[1:])) and percentages[0] < percentages[-1]:
        curve_direction = "De lage scorebanden hebben in deze curve een lager percentage dan de hoge. "
    else:
        curve_direction = "De opgeslagen percentages lopen niet overal in dezelfde richting. "
    hypothetical_text = ""
    score_question = re.search(
        r"\b(?:bij|voor)\s+(?:een\s+)?(?:hypothetische\s+)?"
        r"(?:benchmark(?:t)?scores?|scores?)\s+(?:van\s+)?"
        r"(\d{1,3})(?:\s*(?:en|/|,)\s*(?:van\s+)?(\d{1,3}))?\b",
        message, re.I,
    )
    if score_question:
        requested_scores = [Decimal(value) for value in score_question.groups() if value is not None]
        if all(Decimal("0") <= requested <= Decimal("100") for requested in requested_scores):
            examples: list[str] = []
            for requested in dict.fromkeys(requested_scores):
                matching_bands = [band for band in verified_bands
                                  if requested >= band[0]
                                  and (band[1] is None or requested < band[1])]
                if len(matching_bands) != 1:
                    return None
                _, _, requested_percent, requested_amount = matching_bands[0]
                if abs(requested_amount - base * requested_percent / 100) > Decimal("0.01"):
                    return None
                examples.append(
                    f"score {_display(requested)}: {_display(requested_percent)}% van "
                    f"€{_display(base, money=True)} = hypothetisch "
                    f"€{_display(requested_amount, money=True)}"
                )
            hypothetical_text = "Bij de gevraagde benchmarkscores geldt " + "; ".join(examples) + ". "
    return (
        f"Je opgeslagen Smart DCA-plan {setup_name} voor {pair.upper()} gebruikt een "
        f"basisbedrag van €{_display(base, money=True)}. De laatst geverifieerde "
        f"benchmarkscore is {_display(current)}/100 (scorerapport {score_day}; oudste "
        f"indicatorbron {source}). Die valt in de scoreband {range_text} "
        f"(ondergrens inbegrepen, bovengrens uitgesloten). De opgeslagen curve zet "
        f"daar {_display(percent)}% van het basisbedrag tegenover: hypothetisch "
        f"€{_display(amount, money=True)} per toegestane aankoop. "
        f"{hypothetical_text}"
        f"{curve_direction}Een lage benchmarkscore bewijst op zichzelf geen oversold RSI. Als je bij "
        "oversold meer dan het basisbedrag wilt inzetten, bepaal dan zelf eerst de "
        "scoregrens, het maximum en je risicobudget; ik kan daarna een wijzigingsvoorstel "
        "voor Paper voorbereiden. Dit bedrag is geen kooporder of gegarandeerde uitvoering: "
        f"de opgeslagen timing en overige veiligheidscontroles gelden ook. {bot_text}"
    )
