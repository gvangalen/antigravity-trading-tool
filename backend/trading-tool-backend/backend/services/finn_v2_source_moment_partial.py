"""A bounded, source-only answer when a multi-source clock claim fails.

The model's rejected wording is never reused here. Only completed reads from
the current turn can contribute account facts; ambiguous facts stay open.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from backend.services.asset_catalog_service import mentioned_catalog_symbols


_PAIR = re.compile(r"\b([A-Z][A-Z0-9]*)/(EUR|USD|USDT)\b", re.I)
_BOT_ID = re.compile(r"\bbot\s*#?\s*(\d+)\b", re.I)


def is_mixed_bot_position_question(question: str) -> bool:
    """A named bot and another asset's position need one bounded source answer."""
    assets = mentioned_catalog_symbols(question)
    bot_assets = {
        match.group(1).upper() for match in re.finditer(
            r"\b([A-Z]{2,10})[-\s]+bot\s*#?\s*\d+\b", question, re.I,
        )
    }
    position_assets = {
        match.group(1).upper() for match in re.finditer(
            r"\b([A-Z]{2,10})[-\s]+(?:Paper[-\s]+)?(?:positie|position)\b",
            question, re.I,
        )
    }
    return bool(_BOT_ID.search(question) and bot_assets & assets
                and position_assets & assets and len(assets) > 1
                and any(bot != position for bot in bot_assets for position in position_assets))


def _quantity(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    if number == 0:
        return "0"
    return format(number.normalize(), "f").replace(".", ",")


def _score(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or not 0 <= number <= 100:
        return None
    return format(number.normalize(), "f").replace(".", ",")


def _single(rows: list[Any]) -> Any | None:
    """Use a fact only when repeated reads agree exactly."""
    return rows[0] if rows and all(row == rows[0] for row in rows) else None


def _safe_reason(value: Any) -> str | None:
    # Match only fixed phrases emitted by our bot engine. Never echo source text.
    return {
        "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark.":
            "de opgeslagen setupvoorwaarden niet bij de actuele benchmark passen",
        "Opgeslagen setupvoorwaarden passen niet bij de actuele scores.":
            "de opgeslagen setupvoorwaarden niet bij de actuele scores passen",
    }.get(value) if isinstance(value, str) else None


def render_source_moment_partial(
    *, question: str, evidence: tuple[dict[str, Any], ...], locale: str = "nl",
    require_facts: bool = False,
) -> str | None:
    """Recover a useful read-only answer without repeating an unverified clock."""
    language = str(locale or "nl").split("-")[0].lower()
    if language != "nl":
        return None
    assets = mentioned_catalog_symbols(question)
    pairs = {match.group(0).upper() for match in _PAIR.finditer(question)}
    if len(assets) < 2 and len(pairs) < 2:
        return None
    completed = [item for item in evidence if item.get("status") == "completed"
                 and isinstance(item.get("data"), dict)]
    if not completed:
        if require_facts:
            return None
        bot_ids = {int(match.group(1)) for match in _BOT_ID.finditer(question)}
        if len(pairs) > 1 and len(bot_ids) == 1:
            return f"Welk van de genoemde handelsparen hoort bij bot #{next(iter(bot_ids))}?"
        return "Welk asset of welke bron wil je als eerste laten controleren?"

    lines: list[str] = []
    source_fact_count = 0
    requested_bot_ids = {int(match.group(1)) for match in _BOT_ID.finditer(question)}
    named_bot_assets = {match.group(1).upper() for match in re.finditer(
        r"\b([A-Z]{2,10})[-\s]+bot\s*#?\s*\d+\b", question, re.I,
    )}
    asks_report = bool(re.search(r"\brapport\w*\b|\bdagrapport\b", question, re.I))
    asks_scores = bool(re.search(r"\b(?:score\w*|benchmark\w*)\b", question, re.I))
    asks_bot = bool(re.search(r"\bbot\b|\bbot\s*#?\s*\d+\b|\bbotplan\b", question, re.I))
    asks_position = bool(re.search(r"\bpositie\w*\b|\bportefeuille\b", question, re.I))
    named_position_assets = {
        match.group(1).upper() for match in re.finditer(
            r"\b([A-Z]{2,10})[-\s]+(?:Paper[-\s]+)?(?:positie|position)\b", question, re.I,
        ) if match.group(1).upper() in assets
    }
    asks_preview = bool(re.search(r"\bpreview\b", question, re.I))
    bot_asset = next(iter(named_bot_assets)) if len(named_bot_assets) == 1 else None
    paper_requested = bool(re.search(r"\bPaper\b", question, re.I))
    linked = [item["data"] for item in completed if item.get("scope") == "read_linked_bot"
              and item["data"].get("bot_id") in requested_bot_ids
              and item["data"].get("is_live") is False
              and str(item["data"].get("symbol") or "").upper() == bot_asset]
    selected_bot = _single(linked)
    bot_pair = str((selected_bot or {}).get("trading_pair") or (selected_bot or {}).get("pair") or "").upper()
    pair_bound = not pairs or bot_pair in pairs
    portfolio_reads = [item for item in completed if item.get("scope") == "read_portfolio"]
    portfolio_bot_refs = [
        bot for item in portfolio_reads for bot in item["data"].get("bots") or []
        if isinstance(bot, dict) and bot.get("bot_id") in requested_bot_ids
        and str(bot.get("symbol") or "").upper() == bot_asset
        and bot.get("is_live") is False
    ]
    portfolio_parent_consistent = all(
        (bot.get("setup_id") is None or bot.get("setup_id") == selected_bot.get("setup_id"))
        and (bot.get("strategy_id") is None
             or bot.get("strategy_id") == selected_bot.get("strategy_id"))
        for bot in portfolio_bot_refs
    ) if selected_bot is not None else False
    setups = [item["data"] for item in completed if item.get("scope") == "read_active_setup"
              and str(item["data"].get("symbol") or "").upper() == bot_asset]
    matched_setups = [row for row in setups if selected_bot is not None
                      and row.get("setup_id") == selected_bot.get("setup_id")
                      and row.get("setup_id") is not None]
    setup = _single(matched_setups)
    setup_pair = str((setup or {}).get("pair") or "").upper()
    if not setup_pair and setup is not None and setup.get("quote_currency"):
        setup_pair = f'{bot_asset}/{str(setup["quote_currency"]).upper()}'
    bot_market_id = (selected_bot or {}).get("market_id")
    setup_market_id = (setup or {}).get("market_id")
    same_market = (type(bot_market_id) is int and bot_market_id > 0
                   and bot_market_id == setup_market_id)
    market_id_conflict = (type(bot_market_id) is int and bot_market_id > 0
                          and type(setup_market_id) is int and setup_market_id > 0
                          and bot_market_id != setup_market_id)
    parent_linked = bool(selected_bot is not None and setup is not None
                         and portfolio_parent_consistent
                         and not market_id_conflict
                         and (not bot_pair or not setup_pair or bot_pair == setup_pair))
    verified_bot_plan = bool(selected_bot is not None and setup is not None
                             and portfolio_parent_consistent
                             and bot_pair and setup_pair == bot_pair and same_market)
    unbound_parent_plan = bool(parent_linked and not verified_bot_plan
                               and not bot_pair and not setup_pair
                               and bot_market_id is None and setup_market_id is None)
    linked_pairs = {
        str(row.get("trading_pair") or row.get("pair") or "").upper()
        for row in linked
        if row.get("trading_pair") or row.get("pair")
    }
    portfolio_status_pair_safe = not linked_pairs or (
        len(linked_pairs) == 1 and (pair_bound or verified_bot_plan)
    )
    if len(requested_bot_ids) == 1:
        bot_id = next(iter(requested_bot_ids))
        status_rows = [item["data"] for item in completed
                       if item.get("scope") == "read_bot_status"
                       and item["data"].get("bot_id") == bot_id
                       and str(item.get("asset") or "").upper() == bot_asset
                       and (pair_bound or verified_bot_plan)
                       and (not paper_requested or item["data"].get("is_live") is False)]
        statuses = {str(row.get("operational_status") or "").lower() for row in status_rows}
        if len(statuses) == 1:
            status = next(iter(statuses))
            if status in {"active", "paused"}:
                translated = "actief" if status == "active" else "gepauzeerd"
                lines.append(f"Bot #{bot_id} heeft volgens de gelezen botstatus de status {translated}.")
                source_fact_count += 1
        elif not status_rows and portfolio_status_pair_safe:
            portfolio_bot_rows = [bot for item in portfolio_reads
                                  for bot in item["data"].get("bots") or []
                                  if isinstance(bot, dict) and bot.get("bot_id") == bot_id
                                  and bot.get("is_live") is False
                                  and str(bot.get("symbol") or "").upper().split("/", 1)[0] == bot_asset]
            portfolio_bot = _single(portfolio_bot_rows)
            if portfolio_bot is not None and all(any(
                isinstance(bot, dict) and bot.get("bot_id") == bot_id
                and bot.get("is_live") is False
                for bot in item["data"].get("bots") or []
            ) for item in portfolio_reads):
                status = str(portfolio_bot.get("operational_status") or "").lower()
                if status in {"active", "paused"}:
                    translated = "actief" if status == "active" else "gepauzeerd"
                    lines.append(f"In de gelezen Paper-portefeuille staat bot #{bot_id} op {translated}.")
                    source_fact_count += 1
        decisions = [row for item in completed if item.get("scope") == "read_review_history"
                     for row in item["data"].get("latest_bot_decisions") or []
                     if isinstance(row, dict) and row.get("bot_id") == bot_id
                     and str(row.get("symbol") or "").upper() == bot_asset
                     and (pair_bound or verified_bot_plan)
                     and (not bot_pair or str(row.get("pair") or "").upper() == bot_pair)
                     and (not paper_requested or row.get("is_live") is False)]
        actions = {str(row.get("action") or "").lower() for row in decisions}
        if len(actions) == 1:
            action = next(iter(actions))
            if action in {"hold", "wait", "blocked"}:
                lines.append(f"De laatst gelezen beslissing voor bot #{bot_id} is wachten; dat is geen uitgevoerde koop.")
                source_fact_count += 1

        reasons = [_safe_reason(row.get("safety_reason"))
                   for row in decisions]
        reason = _single(reasons)
        if reason:
            lines.append(f"De opgeslagen botreden is dat {reason}.")
            source_fact_count += 1
        elif actions == {"hold"}:
            lines.append("De concrete reden voor dit wachtbesluit kan ik uit de gecontroleerde velden hier niet bevestigen.")

    reports = [item["data"] for item in completed if item.get("scope") == "read_latest_report"
               and item["data"].get("report_type") == "daily_reports"]
    if asks_report and _single(reports) is not None:
        lines.append("Het gelezen dagrapport is een opgeslagen momentopname. De scores daarin zijn geen actuele botbeslissing.")
        source_fact_count += 1
        report = reports[0]
        snapshot = report.get("score_source_snapshot") or {}
        assets_in_report = snapshot.get("assets") if isinstance(snapshot, dict) else None
        if isinstance(assets_in_report, list):
            for pair in sorted(pairs):
                rows = [row for row in assets_in_report if isinstance(row, dict)
                        and str(row.get("pair") or "").upper() == pair]
                values = [(_score(row.get("benchmark_score")) if row.get("score_status") == "available" else None)
                          for row in rows]
                value = _single(values)
                if value is not None:
                    lines.append(f"In die rapportmomentopname staat voor {pair} benchmarkscore {value}/100.")
                    source_fact_count += 1
    if (asks_report or asks_scores) and len(pairs) > 1 and (
        reports or any(item.get("scope") == "read_asset_scores" for item in completed)
    ):
        lines.append(f"{' en '.join(sorted(pairs))} zijn afzonderlijke handelsparen; hun scores en bronmomenten kunnen verschillen.")
    pair_score_rows: dict[str, set[tuple[int, str] | None]] = {}
    for item in completed:
        if item.get("scope") != "read_asset_scores":
            continue
        data = item["data"]
        pair = str(data.get("pair") or "").upper()
        score = _score(data.get("benchmark_score"))
        market_id = data.get("market_id")
        if pair in pairs:
            valid = (data.get("source_status") == "available" and score is not None
                     and type(market_id) is int and market_id > 0)
            pair_score_rows.setdefault(pair, set()).add((market_id, score) if valid else None)
    for pair, values in (sorted(pair_score_rows.items()) if asks_report or asks_scores else ()):
        if len(values) == 1 and None not in values:
            _, score = next(iter(values))
            lines.append(f"De gelezen paaranalyse voor {pair} heeft benchmarkscore {score}/100.")
            source_fact_count += 1
    if verified_bot_plan or unbound_parent_plan:
        low = _score(setup.get("min_benchmark_score"))
        high = _score(setup.get("max_benchmark_score"))
        if low is not None and high is not None:
            if verified_bot_plan:
                lines.append(
                    f"Bot #{selected_bot['bot_id']} hoort bij {bot_pair}; de gekoppelde setup "
                    f"vereist voor dat handelspaar een benchmarkscore tussen {low} en {high}."
                )
            else:
                timeframe = str(setup.get("timeframe") or "").strip()
                period = f" op {timeframe}" if timeframe else ""
                lines.append(
                    f"Bot #{selected_bot['bot_id']} is via zijn opgeslagen strategie gekoppeld "
                    f"aan een {bot_asset}-setup{period}. In die setup staat een benchmarkscore "
                    f"tussen {low} en {high}. Het exacte handelspaar of markt-ID van deze "
                    "botconfiguratie is niet bevestigd; ik kan niet bevestigen dat de bot "
                    "deze grens voor een specifiek handelspaar toepast."
                )
            source_fact_count += 1
            if verified_bot_plan:
                lines.append("Die grens hoort bij dit botplan. Een handmatige preview kan een andere setup en dus andere voorwaarden gebruiken.")
    if verified_bot_plan:
        lines.append("Een botplan beoordeelt daarnaast zijn eigen instapvoorwaarden; een rapportscore is geen koopopdracht.")

    positions: dict[tuple[int, str], set[str]] = {}
    known_position_bots: set[tuple[int, str]] = set()
    for item in portfolio_reads:
        for bot in item["data"].get("bots") or []:
            if not isinstance(bot, dict) or bot.get("is_live") is not False:
                continue
            symbol = str(bot.get("symbol") or "").upper().split("/", 1)[0]
            if symbol not in (named_position_assets or assets) or (
                item.get("asset") and str(item["asset"]).upper() != symbol
            ):
                continue
            quantity = _quantity(bot.get("position_qty"))
            if type(bot.get("bot_id")) is not int:
                continue
            positions.setdefault((bot["bot_id"], symbol), set()).add(quantity or "unknown")
    for (bot_id, symbol), quantities in (sorted(positions.items()) if asks_position else ()):
        eligible_reads = [item for item in portfolio_reads
                          if not item.get("asset") or str(item["asset"]).upper() == symbol]
        present_in_all = all(any(
            isinstance(bot, dict) and bot.get("bot_id") == bot_id
            and str(bot.get("symbol") or "").upper().split("/", 1)[0] == symbol
            and bot.get("is_live") is False
            for bot in item["data"].get("bots") or []
        ) for item in eligible_reads)
        if present_in_all and quantities == {"0"} and asks_position:
            lines.append(f"In de gelezen Paper-portefeuille heeft bot #{bot_id} geen open {symbol}-positie (0 {symbol}).")
            source_fact_count += 1
            known_position_bots.add((bot_id, symbol))
        elif present_in_all and len(quantities) == 1 and "unknown" not in quantities and "0" not in quantities:
            quantity = next(iter(quantities))
            lines.append(f"In de gelezen Paper-portefeuille staat bij bot #{bot_id} een open positie van {quantity} {symbol}.")
            source_fact_count += 1
            known_position_bots.add((bot_id, symbol))

    confirmed_position_assets = {
        symbol for symbol in named_position_assets
        if any(key[1] == symbol for key in positions)
        and all(key in known_position_bots for key in positions if key[1] == symbol)
    }

    if lines and len(pairs) == 1 and asks_bot and asks_position and not (asks_report or asks_scores):
        pair = next(iter(pairs))
        if unbound_parent_plan:
            lines.append(f"{pair} is het genoemde analysepaar; voor deze bot is geen eigen handelspaar geverifieerd.")
        else:
            lines.append(f"{pair} is het genoemde analysepaar; de botvoorwaarden horen bij het eigen botpaar.")

    if require_facts and source_fact_count == 0:
        return None
    if not lines:
        requested = []
        if asks_bot:
            requested.append("de bot en zijn plan")
        if re.search(r"\bscore\w*\b", question, re.I):
            requested.append("de scores")
        if asks_position:
            requested.append("de Paper-positie")
        subject = ", ".join(requested) if requested else "de genoemde bronnen"
        if asks_bot and asks_position and len(requested_bot_ids) == 1:
            bot_id = next(iter(requested_bot_ids))
            return (f"Ik kan {subject} hier niet eenduidig teruglezen. "
                    f"Wil je dat ik bot #{bot_id} en de Paper-portefeuille opnieuw controleer?")
        return f"Ik kan {subject} hier niet eenduidig teruglezen. Welk handelspaar wil je eerst laten controleren?"
    if re.search(r"\b(?:kopen|koop|buy|handelen|vervolgstap|wat\s+nu)\b", question, re.I):
        lines.append("Ik kan hiermee geen nieuwe koop onderbouwen. Controleer eerst de actuele score en de voorwaarden van het botplan voor het juiste handelspaar.")
    missing = []
    if asks_report and not reports:
        missing.append("het dagrapport")
    if asks_bot and not (verified_bot_plan or unbound_parent_plan):
        missing.append("de koppeling tussen bot en plan")
    elif asks_bot and unbound_parent_plan:
        missing.append("de exacte uitvoeringsmarkt van de bot")
    for symbol in sorted(named_position_assets - confirmed_position_assets):
        missing.append(f"de {symbol}-positie")
    if missing:
        lines.append("Ik kon " + ", ".join(missing) + " niet eenduidig bevestigen uit de gelezen gegevens.")
        if asks_bot and unbound_parent_plan:
            lines.append("Controleer het handelspaar in de botconfiguratie voordat je deze voor uitvoering gebruikt.")
        elif asks_bot and not pair_bound and requested_bot_ids:
            bot_id = next(iter(requested_bot_ids))
            if bot_pair and len(pairs) == 1:
                lines.append(f"Bot #{bot_id} is gelezen voor {bot_pair}; wil je de voorwaarden voor dat handelspaar apart laten controleren?")
            else:
                lines.append(f"Wil je dat ik de koppeling en het eigen handelspaar van bot #{bot_id} opnieuw controleer?")
        else:
            lines.append("Welk van deze ontbrekende onderdelen wil je eerst laten controleren?")
    elif asks_preview:
        lines.append("Wil je dat ik de handmatige preview en de bijbehorende setup apart controleer?")
    return "\n\n".join(lines)
