"""Source-bound recovery for a read-only, single-asset coach answer.

This is used when a model answer misses a required source fact or fails
source-moment verification. It reports the current turn's owner-scoped reads
separately and never invents a trade recommendation or treats a missing read
as a current value.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.services.finn_v2_tool_adapters.display_source_moment import display_source_moment
from backend.services.finn_v2_paper_position_answer import asks_about_bot_decision


def _source_moment(value: Any, user_time_zone: str | None) -> str | None:
    instant = display_source_moment(value)
    if isinstance(instant, str):
        try:
            instant = datetime.fromisoformat(instant.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(instant, datetime):
        return None
    try:
        zone = ZoneInfo(user_time_zone) if user_time_zone else timezone.utc
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = timezone.utc
    return instant.replace(tzinfo=instant.tzinfo or timezone.utc).astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")


def _number(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.normalize(), "f").replace(".", ",")


def _money(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.quantize(Decimal("0.01")), ".2f").replace(".", ",")


def _has_overprecise_euro_amount(answer: str) -> bool:
    for match in re.finditer(r"€\s*\d[\d.,]*", answer):
        value = match.group().lstrip("€ ")
        separator = max(value.rfind("."), value.rfind(","))
        fractional_digits = len(value) - separator - 1
        if separator >= 0 and fractional_digits > 2 and not (
            fractional_digits == 3 and separator <= 3 and value.count(".") + value.count(",") == 1
        ):
            return True
    return False


def _rows(evidence: tuple[dict[str, Any], ...], scope: str, asset: str) -> list[dict[str, Any]]:
    """Return the last completed read for this scope and asset in the turn.

    The Responses loop may reread the same source several times. Counting
    those copies as separate bots, reports or portfolios creates false
    ambiguity and suppresses the source-bound recovery.
    """
    rows = []
    for item in evidence:
        if item.get("scope") != scope or item.get("status") != "completed":
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        symbol = str(data.get("symbol") or data.get("asset") or item.get("asset") or "").upper()
        if symbol and symbol.split("/", 1)[0] != asset:
            continue
        rows.append(data)
    return rows[-1:]


def _bot_row(question: str, evidence: tuple[dict[str, Any], ...], asset: str) -> dict[str, Any] | None:
    portfolios = _rows(evidence, "read_portfolio", asset)
    bots = portfolios[0].get("bots") or [] if portfolios else []
    matching = [bot for bot in bots if isinstance(bot, dict) and bot.get("is_live") is False
                and str(bot.get("symbol") or "").upper().split("/", 1)[0] == asset]
    # A bot-focused answer must bind the name the user actually named. A
    # singleton BTC portfolio is not proof that it is the bot in the question.
    normalized_question = " ".join(question.split())
    requested_clause = re.split(
        r"\blees\s+alleen\b|\bwijzig\s+geen\b", normalized_question,
        maxsplit=1, flags=re.I,
    )[0]
    # A negated order is still a request about this bot. Keep negated bot
    # identity exclusions fail closed, but do not discard the trade reason.
    identity_clause = re.sub(
        r"\bgeen\s+(?:paper[-\s]?)?order(?:\s+geplaatst)?\b|"
        r"\bniet\s+gekocht\b|\bkocht\b[^.!?]{0,80}\bniet\b",
        "", requested_clause, flags=re.I,
    )
    if (re.search(r"\b(?:niet|geen|behalve)\b", identity_clause, re.I)
            or len(re.findall(r"\bbot\b", requested_clause, re.I)) != 1):
        return None
    named = [bot for bot in matching if str(bot.get("name") or "").strip()
             and re.search(
                 rf"(?<!\w){re.escape(' '.join(str(bot['name']).split()))}"
                 r"(?=\s+(?:voor|in|met|en|van|bij|op|uit)\b|"
                 r"\s+(?:geen\s+(?:paper[-\s]?)?order|"
                 r"heeft\s+geen\s+(?:paper[-\s]?)?order|"
                 r"niet\s+gekocht|kocht\s+niet)\b|[.,!?;:]|$)",
                 normalized_question, re.I,
             )]
    generic_reference = re.search(
        rf"\b(?:mijn|de)\s+{re.escape(asset)}\s+Paper[-\s]?bot\b"
        r"(?=\s+(?:voor|in|met|en|van|bij|op|uit|volgens|geen|niet|"
        r"heeft|had|is|was|wacht|kocht|koop)\b|[.,!?;:]|$)",
        requested_clause, re.I,
    )
    if generic_reference:
        # A generic label can equal a literal saved bot name. It still does
        # not select that bot when another Paper-bot shares the asset.
        return matching[0] if len(matching) == 1 else None
    if len(named) == 1:
        return named[0]
    if named or len(matching) != 1:
        return None
    return None


def _bot_evidence_consistent(
    question: str, evidence: tuple[dict[str, Any], ...], asset: str,
) -> bool:
    bot = _bot_row(question, evidence, asset)
    if bot is None or bot.get("bot_id") is None:
        return False
    bot_id = str(bot["bot_id"])
    statuses = _rows(evidence, "read_bot_status", asset)
    status_requested = bool(re.search(r"\b(?:bot[-\s]?status|status\s+van\s+(?:de\s+)?bot)\b", question, re.I))
    if status_requested and (len(statuses) != 1
                             or not _source_moment(statuses[0].get("read_at"), None)
                             or statuses[0].get("operational_status") not in {"active", "paused"}):
        return False
    if statuses and str(statuses[0].get("bot_id")) != bot_id:
        return False
    if statuses and statuses[0].get("is_live") is True:
        return False
    histories = _rows(evidence, "read_review_history", asset)
    decisions = [row for data in histories for row in data.get("latest_bot_decisions") or []
                 if isinstance(row, dict)
                 and str(row.get("symbol") or "").upper().split("/", 1)[0] == asset
                 and str(row.get("bot_id")) == bot_id]
    if asks_about_bot_decision(question) and len(decisions) != 1:
        return False
    if len(decisions) > 1 or any(row.get("is_live") is True for row in decisions):
        return False
    pair = re.search(rf"\b{re.escape(asset)}/(EUR|USDT|USD)\b", question, re.I)
    if pair and (len(decisions) != 1 or
                 str(decisions[0].get("pair") or "").upper() != pair.group().upper()):
        return False
    return True


def _requires_bound_bot(question: str, topics: tuple[str, ...]) -> bool:
    return "bot" in topics and (
        asks_about_bot_decision(question)
        or ("portfolio" in topics and bool(re.search(
            r"\b(?:bot[-\s]?status|botbudget|budgetlimiet|botbudgetlimiet|paper[-\s]?holdbesluit)\b",
            question, re.I,
        )))
    )


def coach_source_coverage_gap(
    *, asset: str, topics: tuple[str, ...], evidence: tuple[dict[str, Any], ...],
    answer: str, question: str = "", user_time_zone: str | None = None,
) -> str | None:
    """Check that a broad answer includes the saved reason and bot cash it read."""
    bound_bot = _requires_bound_bot(question, topics)
    if bound_bot and not _bot_evidence_consistent(question, evidence, asset):
        return "bot_evidence_ambiguous"
    selected_bot = _bot_row(question, evidence, asset) if bound_bot else None
    if "bot" in topics:
        if re.search(r"\b(?:bot[-\s]?status|status\s+van\s+(?:de\s+)?bot)\b", question, re.I):
            statuses = _rows(evidence, "read_bot_status", asset)
            status_at = _source_moment(statuses[0].get("read_at"), user_time_zone) if len(statuses) == 1 else None
            if not re.search(r"\bbotstatus\b", answer, re.I):
                return "bot_status_missing"
            if status_at and status_at not in answer:
                return "bot_status_read_moment_missing"
        decisions = [row for data in _rows(evidence, "read_review_history", asset)
                     for row in data.get("latest_bot_decisions") or []
                     if isinstance(row, dict)
                     and str(row.get("symbol") or "").upper().split("/", 1)[0] == asset
                     and (not selected_bot or str(row.get("bot_id")) == str(selected_bot.get("bot_id")))]
        if len(decisions) == 1:
            reason = str(decisions[0].get("safety_reason") or "").strip()
            if reason and reason.casefold() not in answer.casefold():
                return "saved_bot_reason_missing"
    if "portfolio" in topics:
        if re.search(r"\b(?:botbudget|budgetlimiet|botbudgetlimiet)\b", question, re.I):
            budget = _money((selected_bot or {}).get("budget_total_eur"))
            if budget is None or not re.search(
                rf"\b(?:botbudget|budgetlimiet|botbudgetlimiet)\b[^.!?]{{0,100}}?€\s*{re.escape(budget)}(?!\d)",
                answer, re.I,
            ):
                return "bot_budget_mismatch"
        if re.search(r"\b(?:belegd|geïnvesteerd|investeerd)\b", question, re.I):
            invested = _money((selected_bot or {}).get("invested_eur"))
            if invested is None or not re.search(
                rf"\b(?:belegd|geïnvesteerd|investeerd)\b[^.!?]{{0,100}}?€\s*{re.escape(invested)}(?!\d)",
                answer, re.I,
            ):
                return "paper_invested_mismatch"
        if _has_overprecise_euro_amount(answer):
            return "money_precision_invalid"
        portfolios = _rows(evidence, "read_portfolio", asset)
        bots = (portfolios[0].get("bots") or []) if len(portfolios) == 1 else []
        matching = ([selected_bot] if selected_bot is not None else
                    [bot for bot in bots if isinstance(bot, dict) and not bot.get("is_live")
                     and str(bot.get("symbol") or "").upper().split("/", 1)[0] == asset])
        if len(matching) == 1:
            cash = _money(matching[0].get("paper_cash_eur"))
            if cash is not None and not re.search(
                rf"\b(?:botkas|kas\s+van\s+de\s+bot)\b[^.!?]{{0,100}}?€\s*{re.escape(cash)}(?!\d)",
                answer, re.I,
            ):
                return "paper_bot_cash_missing"
            if re.search(r"\b(?:positie|posities|position)\b", question, re.I):
                quantity = _number(matching[0].get("position_qty"))
                if quantity is not None and not re.search(
                    rf"\b{re.escape(quantity)}\s+{re.escape(asset)}\b|\b(?:positie|position)\b[^.!?]{{0,40}}\b{re.escape(quantity)}\b",
                    answer, re.I,
                ):
                    return "paper_bot_position_missing"
        if re.search(r"\b(?:totale|gezamenlijke)\s+Paper[-\s]?kas\b", question, re.I):
            global_cash = _money((portfolios[0].get("global") or {}).get("cash_balance")) if portfolios else None
            account_wide = any(item.get("scope") == "read_portfolio"
                               and item.get("status") == "completed" and not item.get("asset")
                               and item.get("data") is portfolios[0]
                               for item in evidence) if portfolios else False
            if not account_wide or global_cash is None or not re.search(
                rf"\b(?:Paper[-\s]?(?:portefeuille|kas)|totale\s+kas)\b[^.!?]{{0,100}}?€\s*{re.escape(global_cash)}(?!\d)",
                answer, re.I,
            ):
                return "paper_total_cash_mismatch"
    if re.search(r"\b(?:vervolgstap|wat\s+(?:doe|moet|kan)\s+ik)\b", question, re.I):
        decisions = [row for data in _rows(evidence, "read_review_history", asset)
                     for row in data.get("latest_bot_decisions") or []
                     if isinstance(row, dict)
                     and str(row.get("symbol") or "").upper().split("/", 1)[0] == asset
                     and (not selected_bot or str(row.get("bot_id")) == str(selected_bot.get("bot_id")))]
        reason = str(decisions[0].get("safety_reason") or "") if len(decisions) == 1 else ""
        if "valuta" in reason.casefold() and "koersniv" in reason.casefold() and not re.search(
            r"(?:^|\n)\s*(?:veilige\s+)?vervolgstap\s*:[^\n]*\b(?:controleer|bevestig)\b[^\n]*\bvaluta\b",
            answer, re.I,
        ):
            return "specific_next_step_missing"
    return None


def render_coach_source_fallback(
    *, asset: str, topics: tuple[str, ...], evidence: tuple[dict[str, Any], ...],
    question: str = "", user_time_zone: str | None = None,
) -> str | None:
    """Compose only requested topics from completed reads of the current turn."""
    if not asset or not topics or not evidence:
        return None
    bound_bot = _requires_bound_bot(question, topics)
    if bound_bot and not _bot_evidence_consistent(question, evidence, asset):
        return None
    selected_bot = _bot_row(question, evidence, asset) if bound_bot else None
    lines = [f"Ik heb de bronnen voor {asset} afzonderlijk gecontroleerd:"]
    verified = False
    for topic in topics:
        if topic == "setup":
            setups = _rows(evidence, "read_active_setup", asset)
            strategies = _rows(evidence, "read_linked_strategy", asset)
            if len(setups) == 1:
                setup = setups[0]
                name = str(setup.get("name") or "naam onbekend")
                band = ""
                minimum = _number(setup.get("min_benchmark_score"))
                maximum = _number(setup.get("max_benchmark_score"))
                if minimum and maximum:
                    band = f", scoreband {minimum}–{maximum}"
                strategy = (f"; gekoppelde strategie ‘{strategies[0]['name']}’"
                            if len(strategies) == 1 and strategies[0].get("name") else "")
                lines.append(f"- Plan: opgeslagen setup ‘{name}’{band}{strategy}.")
                verified = True
            else:
                lines.append("- Plan: geen eenduidige opgeslagen setup uitgelezen.")
        elif topic == "score":
            scores = _rows(evidence, "read_asset_scores", asset)
            score = _number(scores[0].get("benchmark_score")) if len(scores) == 1 else None
            if score:
                source = (scores[0].get("oldest_indicator_source_observed_at") or
                          scores[0].get("as_of"))
                at = _source_moment(source, user_time_zone)
                lines.append(f"- Benchmarkscore: {score} volgens de gelezen scorebron"
                             + (f"; oudste indicatorbron {at}." if at else "; bronmoment onbekend."))
                verified = True
            else:
                lines.append("- Benchmarkscore: geen verifieerbare actuele score uitgelezen.")
        elif topic == "bot":
            history = _rows(evidence, "read_review_history", asset)
            decisions = [row for data in history for row in data.get("latest_bot_decisions") or []
                         if isinstance(row, dict)
                         and str(row.get("symbol") or "").upper().split("/", 1)[0] == asset
                         and (not selected_bot or row.get("bot_id") is None
                              or str(row.get("bot_id")) == str(selected_bot.get("bot_id")))]
            if len(decisions) == 1:
                decision = decisions[0]
                at = _source_moment(decision.get("decision_at"), user_time_zone)
                reason = str(decision.get("safety_reason") or "").strip()
                lines.append(
                    f"- Botbeslissing: {decision.get('action') or 'actie onbekend'}"
                    + (f" op {at}" if at else " op een onbekend bronmoment")
                    + (f"; opgeslagen reden: {reason.rstrip('.!?')}." if reason else
                       "; geen concrete reden in de gelezen beslissing.")
                )
                verified = True
            else:
                lines.append("- Botbeslissing: geen eenduidig opgeslagen besluit uitgelezen.")
            if re.search(r"\b(?:bot[-\s]?status|status\s+van\s+(?:de\s+)?bot)\b", question, re.I):
                statuses = _rows(evidence, "read_bot_status", asset)
                status = (statuses[0] if len(statuses) == 1
                          and (not selected_bot or str(statuses[0].get("bot_id")) == str(selected_bot.get("bot_id")))
                          else {})
                status_at = _source_moment(status.get("read_at"), user_time_zone)
                if status_at and status.get("operational_status") in {"active", "paused"}:
                    lines.append(f"- Botstatus: {status['operational_status']}, uitgelezen op {status_at}.")
                    verified = True
                else:
                    lines.append("- Botstatus: huidige status of apart uitleesmoment niet verifieerbaar.")
        elif topic == "report":
            reports = _rows(evidence, "read_latest_report", asset)
            at = _source_moment(reports[0].get("generated_at"), user_time_zone) if len(reports) == 1 else None
            if at:
                lines.append(f"- Dagrapport: momentopname van {at}.")
                verified = True
            else:
                lines.append("- Dagrapport: geen eenduidig rapportmoment uitgelezen.")
        elif topic == "quote":
            quotes = _rows(evidence, "read_market_snapshot", asset)
            quote = quotes[0] if len(quotes) == 1 else {}
            price = _number(quote.get("price"))
            at = _source_moment(quote.get("source_observed_at") or
                                         quote.get("source_observed_at_utc") or
                                         quote.get("source_at") or quote.get("timestamp"), user_time_zone)
            if price and at:
                currency = str(quote.get("quote_currency") or "").upper()
                lines.append(f"- Koers: {price} {currency}, bronmoment {at}.")
                verified = True
            else:
                lines.append("- Koers: geen actuele koers met controleerbaar bronmoment uitgelezen.")
        elif topic == "portfolio":
            portfolios = _rows(evidence, "read_portfolio", asset)
            portfolio = portfolios[0] if len(portfolios) == 1 else {}
            global_data = portfolio.get("global") or {}
            cash = _money(global_data.get("cash_balance"))
            at = _source_moment(portfolio.get("read_at"), user_time_zone)
            bot_cash = [
                (bot, str(bot.get("name") or asset), _money(bot.get("paper_cash_eur")),
                 _number(bot.get("position_qty")))
                for bot in portfolio.get("bots") or []
                if isinstance(bot, dict) and not bot.get("is_live")
                and str(bot.get("symbol") or "").upper().split("/", 1)[0] == asset
                and (not selected_bot or str(bot.get("bot_id")) == str(selected_bot.get("bot_id")))
                and _money(bot.get("paper_cash_eur")) is not None
            ]
            for bot, name, amount, quantity in bot_cash:
                if re.search(r"\b(?:botbudget|budgetlimiet|botbudgetlimiet)\b", question, re.I):
                    budget = _money(bot.get("budget_total_eur"))
                    lines.append(f"- {name} ingestelde botbudgetlimiet: "
                                 + (f"€{budget}; dit is geen extra kas of belegde positie."
                                    if budget is not None else "niet verifieerbaar in de gelezen bron."))
                lines.append(f"- {name} botkas (Paper): €{amount}"
                             + (f", uitgelezen op {at}." if at else ", uitleesmoment onbekend."))
                lines.append(f"- {name} positie (Paper): "
                             + (f"{quantity} {asset} open." if quantity is not None else
                                "geen verifieerbare hoeveelheid uitgelezen."))
                if re.search(r"\b(?:belegd|geïnvesteerd|investeerd)\b", question, re.I):
                    invested = _money(bot.get("invested_eur"))
                    lines.append(f"- {name} werkelijk belegd (Paper): "
                                 + (f"€{invested}." if invested is not None else
                                    "niet verifieerbaar in de gelezen bron."))
                verified = True
            # A selected-asset portfolio projection can carry only that bot's
            # cash. Never relabel it as the account-wide Paper cash total.
            portfolio_sources = [item for item in evidence if item.get("scope") == "read_portfolio"
                                 and item.get("status") == "completed"
                                 and item.get("data") is portfolio]
            account_wide = bool(portfolio_sources and not portfolio_sources[-1].get("asset"))
            if cash is not None and account_wide:
                lines.append(f"- Paper-portefeuille: kas €{cash}"
                             + (f", uitgelezen op {at}." if at else ", uitleesmoment onbekend."))
                verified = True
            elif not bot_cash:
                lines.append("- Paper-portefeuille: geen controleerbare kas uitgelezen.")
            if not bot_cash:
                lines.append("- Paper-positie: geen verifieerbare hoeveelheid uitgelezen.")
    if not verified:
        return None
    decisions = [row for data in _rows(evidence, "read_review_history", asset)
                 for row in data.get("latest_bot_decisions") or []
                 if isinstance(row, dict)
                 and str(row.get("symbol") or "").upper().split("/", 1)[0] == asset
                 and (not selected_bot or str(row.get("bot_id")) == str(selected_bot.get("bot_id")))]
    reason = str(decisions[0].get("safety_reason") or "") if len(decisions) == 1 else ""
    if re.search(r"\b(?:vervolgstap|wat\s+(?:doe|moet|kan)\s+ik)\b", question, re.I):
        if "valuta" in reason.casefold() and "koersniv" in reason.casefold():
            lines.append("Veilige vervolgstap: controleer in de opgeslagen strategie de valuta van de instap-, stop- en koersdoelniveaus en bevestig die voordat je de Paper-bot opnieuw laat beoordelen.")
        elif reason:
            lines.append("Veilige vervolgstap: controleer de opgeslagen blokkadereden bij de strategie voordat je de Paper-bot opnieuw laat beoordelen.")
        else:
            lines.append("Veilige vervolgstap: lees eerst een nieuw, controleerbaar botbesluit voordat je instellingen wijzigt.")
    else:
        lines.append("Deze bronnen hebben eigen tijdstippen. Controleer een verse score, koers en botreden "
                     "voordat je handelt of instellingen wijzigt.")
    return "\n".join(lines)
