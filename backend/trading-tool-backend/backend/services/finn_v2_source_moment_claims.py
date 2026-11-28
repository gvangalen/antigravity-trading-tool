"""Check user-facing source moments against the facts read for this turn."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.services.asset_catalog_service import mentioned_catalog_symbols


_AMSTERDAM = ZoneInfo("Europe/Amsterdam")
_MONTHS = {name: number for number, name in enumerate((
    "januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
    "september", "oktober", "november", "december",
), 1)}
_MONTHS.update({name: number for number, name in enumerate((
    "jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec",
), 1)})
_MONTHS.update({name: number for number, name in enumerate((
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
), 1)})
_MONTHS.update({name: number for number, name in enumerate((
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
), 1)})
_MONTH_PATTERN = "|".join(re.escape(name) for name in sorted(_MONTHS, key=len, reverse=True))
_DATED_MOMENT = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>" + _MONTH_PATTERN + r")\s+(?P<year>20\d{2})"
    r"\s*,?\s*(?:om\s+)?(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2}))?\s*(?P<zone>UTC|CET|CEST)\b"
    r"|(?P<iso_year>20\d{2})-(?P<iso_month>\d{2})-(?P<iso_day>\d{2})"
    r"[ T](?P<iso_hour>\d{1,2}):(?P<iso_minute>\d{2})"
    r"(?::(?P<iso_second>\d{2}))?\s*(?P<iso_zone>UTC|CET|CEST)\b",
    re.I,
)
_ZONED_CLOCK = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|CET|CEST)\b", re.I)
_DATE_ONLY = re.compile(
    r"\b\d{1,2}\s+(?:" + _MONTH_PATTERN + r")\s+20\d{2}\b|"
    r"\b20\d{2}-\d{2}-\d{2}\b", re.I,
)
_REPORT_CLOCK = re.compile(
    r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*"
    r"(?:(?:in\s+)?Europe/Amsterdam\s*,?\s*)?(?P<zone>UTC|CET|CEST)\b",
    re.I,
)


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _claimed_moment(text: str) -> tuple[datetime, bool] | None:
    match = _DATED_MOMENT.search(text)
    if match is None:
        return None
    fields = match.groupdict()
    iso = fields["iso_year"] is not None
    try:
        year = int(fields["iso_year"] if iso else fields["year"])
        month = int(fields["iso_month"]) if iso else _MONTHS[fields["month"].lower()]
        day = int(fields["iso_day"] if iso else fields["day"])
        hour = int(fields["iso_hour"] if iso else fields["hour"])
        minute = int(fields["iso_minute"] if iso else fields["minute"])
        seconds = fields["iso_second"] if iso else fields["second"]
        second = int(seconds or 0)
        zone = (fields["iso_zone"] if iso else fields["zone"]).upper()
        if zone == "UTC":
            return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc), seconds is not None
        for fold in (0, 1):
            local = datetime(year, month, day, hour, minute, second,
                             tzinfo=_AMSTERDAM, fold=fold)
            if (local.tzname() == zone and
                    local.astimezone(timezone.utc).astimezone(_AMSTERDAM).replace(tzinfo=None)
                    == local.replace(tzinfo=None)):
                return local.astimezone(timezone.utc), seconds is not None
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _same_moment(claim: tuple[datetime, bool], observed: datetime) -> bool:
    stated, has_seconds = claim
    expected = observed.replace(microsecond=0)
    return stated == (expected if has_seconds else expected.replace(second=0))


def _one_requested_paper_exit_decision(
    evidence: tuple[dict[str, Any], ...], *, question: str | None, answer: str,
    user_time_zone: str | None,
) -> tuple[tuple[int | None, str, datetime] | None, bool]:
    """Bind an old bot clock to one owner-read closed dossier, never another trade."""
    review_pattern = re.compile(
        r"\b(?:dossier|trade(?:[- ]?(?:reflectie|review))?|review)\s*#\s*(\d+)\b", re.I,
    )
    historical_request = bool(re.search(
        r"\b(?:historisch\w*|afgesloten|gesloten\s+trade|"
        r"trade[- ]?reflectie|weekreflectie|dossier\s*#\s*\d+)\b",
        f"{question or ''}\n{answer}", re.I,
    ))
    if not historical_request:
        return None, False
    requested_ids = {int(match.group(1)) for match in review_pattern.finditer(question or "")}
    stated_ids = {int(match.group(1)) for match in review_pattern.finditer(answer)}
    if len(requested_ids) > 1 or len(stated_ids) > 1 or (
        requested_ids and stated_ids and requested_ids != stated_ids
    ):
        return None, True
    selected_ids = requested_ids or stated_ids
    requested_symbols = mentioned_catalog_symbols(question or "")
    stated_symbols = mentioned_catalog_symbols(answer)
    if (len(requested_symbols) > 1 or len(stated_symbols) > 1
            or requested_symbols and stated_symbols and requested_symbols != stated_symbols):
        return None, True
    selected_symbols = requested_symbols or stated_symbols
    without_week = re.sub(
        r"\b\d{1,2}\s*[–—-]\s*\d{1,2}\s+(?:" + _MONTH_PATTERN + r")\b",
        "", question or "", flags=re.I,
    )
    without_week = re.sub(
        r"\b20\d{2}-\d{2}-\d{2}\s*(?:tot|t/m|[–—-])\s*20\d{2}-\d{2}-\d{2}\b",
        "", without_week, flags=re.I,
    )
    named_dates = {
        (int(match.group(1)), _MONTHS[match.group(2).lower()],
         int(match.group(3)) if match.group(3) else None)
        for match in re.finditer(
            r"\b(\d{1,2})\s+(" + _MONTH_PATTERN + r")(?:\s+(20\d{2}))?\b",
            without_week, re.I,
        )
    }
    if len(named_dates) > 1:
        return None, True
    iso_dates = set(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", without_week))
    if len(iso_dates) > 1:
        return None, True
    if iso_dates:
        try:
            iso_day = datetime.fromisoformat(next(iter(iso_dates))).date()
        except ValueError:
            return None, True
        iso_selector = (iso_day.day, iso_day.month, iso_day.year)
        if named_dates and next(iter(named_dates)) not in {
            iso_selector, (iso_day.day, iso_day.month, None),
        }:
            return None, True
        named_dates = {iso_selector}
    requested_date = next(iter(named_dates), None)
    try:
        date_zone = ZoneInfo(user_time_zone) if user_time_zone else None
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        date_zone = None
    if requested_date is not None and date_zone is None:
        return None, True
    selected: dict[int, tuple[int | None, str, datetime, datetime]] = {}
    for item in evidence:
        if (item.get("scope") != "read_review_history" or item.get("status") != "completed"
                or not isinstance(item.get("data"), dict)):
            continue
        for row in item["data"].get("closed_trades") or []:
            if not isinstance(row, dict) or str(row.get("environment") or "").lower() != "paper":
                continue
            review_id = row.get("review_id")
            exit_facts = row.get("paper_exit_evidence")
            decision_at = _utc(row.get("paper_exit_decision_at"))
            exit_at = _utc(row.get("exit_at"))
            symbol = str(row.get("symbol") or "").upper()
            if (type(review_id) is not int or not isinstance(exit_facts, dict)
                    or exit_facts.get("trigger") not in {"first_target", "stop_loss"}
                    or decision_at is None or exit_at is None or not symbol):
                continue
            candidate = (row.get("bot_id"), symbol, decision_at, exit_at)
            if review_id in selected and selected[review_id] != candidate:
                return None, True
            selected[review_id] = candidate
    candidates = [(review_id, value) for review_id, value in selected.items()
                  if (not selected_ids or review_id in selected_ids)
                  and (not selected_symbols or value[1] in selected_symbols)]
    if requested_date is not None:
        day, month, year = requested_date
        candidates = [(review_id, value) for review_id, value in candidates
                      if (local := value[3].astimezone(date_zone))
                      and (local.day, local.month) == (day, month)
                      and (year is None or local.year == year)]
    if len(candidates) != 1:
        return None, bool(selected_ids or requested_date or selected_symbols)
    bot_id, symbol, decision_at, _ = candidates[0][1]
    return (bot_id, symbol, decision_at), False


def _bot_decision_clocks_supported(
    answer: str, evidence: tuple[dict[str, Any], ...], *, question: str | None = None,
    typed_recovery: bool = False, user_time_zone: str | None = None,
) -> bool:
    """Check bot clocks in prose against saved report or current decision rows."""
    decisions: list[tuple[int | None, str, datetime]] = []
    current_decisions: list[tuple[int | None, str, datetime]] = []
    historical_decision, historical_unsafe = _one_requested_paper_exit_decision(
        evidence, question=question, answer=answer, user_time_zone=user_time_zone,
    )
    if historical_unsafe and re.search(
        r"\b(?:(?:bot)?besluit\w*|(?:bot)?besliss\w*|(?:bot)?beoordel\w*)\b",
        answer, re.I,
    ) and (_DATED_MOMENT.search(answer) or _ZONED_CLOCK.search(answer)):
        return False
    historical_question = bool(question and re.search(
        r"\b(?:afgesloten|gesloten\s+trade|trade[- ]?reflectie|weekreflectie|"
        r"historisch\w*|dossier\s*#)\b", question, re.I,
    ))
    for item in evidence:
        if item.get("status") != "completed" or not isinstance(item.get("data"), dict):
            continue
        data = item["data"]
        if item.get("scope") == "read_review_history":
            rows = data.get("latest_bot_decisions") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                instant = _utc(row.get("decision_at"))
                if instant:
                    decision = (row.get("bot_id"), str(row.get("symbol") or "").upper(), instant)
                    decisions.append(decision)
                    current_decisions.append(decision)
        elif item.get("scope") == "read_bot_status":
            latest = data.get("latest_decision")
            instant = _utc(latest.get("decision_at")) if isinstance(latest, dict) else None
            if instant:
                decision = (data.get("bot_id"), str(item.get("asset") or "").upper(), instant)
                decisions.append(decision)
                current_decisions.append(decision)
        elif item.get("scope") == "read_latest_report":
            snapshot = data.get("score_source_snapshot") or {}
            report = (snapshot.get("report_v2") or {}) if isinstance(snapshot, dict) else {}
            automation = (report.get("automation") or {}) if isinstance(report, dict) else {}
            for bot in automation.get("bots") or []:
                if not isinstance(bot, dict):
                    continue
                decision = bot.get("latest_decision") or {}
                instant = _utc(decision.get("at")) if isinstance(decision, dict) else None
                if instant:
                    decisions.append((bot.get("bot_id"), str(bot.get("symbol") or "").upper(), instant))
    marker = re.compile(r"\b(?:bot\w*|beoordeling\w*|besluit\w*|beslissing\w*|hold)\b", re.I)
    invalid = re.compile(r"\b(?:fout|onjuist|incorrect|wrong|not\s+correct|falsch)\b", re.I)
    current_requested = bool(question and re.search(r"\b(?:bot\w*|besliss\w*)\b", question, re.I)
                             and re.search(r"\b(?:actuele|huidige|laatste|nieuwste|vandaag|nu|latest|current|"
                                           r"(?:bot)?check\w*)\b", question, re.I))
    for clause in re.split(
        r"(?<=[.!?])\s+|\n+|;\s*|,\s*(?:maar|terwijl|but|however)\s+|"
        r"\s+en\s+(?=(?:de\s+)?(?:Paper[- ]portefeuille|bot\s*status\w*)\b)",
        answer, flags=re.I,
    ):
        subject = marker.search(clause)
        if subject is None:
            continue
        ids = {int(match.group(1)) for match in re.finditer(r"\bbot\s*#?\s*(\d+)\b", clause, re.I)}
        # Locate the clock nearest the status read verb. A sentence may also
        # contain a saved Hold decision in either order; only the read clock
        # is removed before the decision clock is checked below.
        if re.search(r"\bbot\s*status\w*\b", clause, re.I):
            read_verbs = list(re.finditer(r"\b(?:gelezen|uitgelezen|opgehaald)\b", clause, re.I))
            dated_moments = list(_DATED_MOMENT.finditer(clause))
            bare_clocks = [clock for clock in _ZONED_CLOCK.finditer(clause)
                           if not any(dated.start() <= clock.start() and clock.end() <= dated.end()
                                      for dated in dated_moments)]
            moments = sorted(dated_moments + bare_clocks, key=lambda match: match.start())
            if read_verbs and moments:
                read_verb = read_verbs[-1]
                conjunctions = list(re.finditer(
                    r"\ben\s+(?=(?:toont|meldt|vermeldt)\s+(?:de\s+)?"
                    r"(?:(?:laatste|nieuwste)\s+)?Hold\b|is\s+(?:opnieuw\s+)?"
                    r"(?:gelezen|uitgelezen|opgehaald)\b)", clause, re.I,
                ))
                segment_start = max((word.end() for word in conjunctions
                                     if word.end() <= read_verb.start()), default=0)
                segment_end = min((word.start() for word in conjunctions
                                   if word.start() >= read_verb.end()), default=len(clause))
                read_moments = [match for match in moments
                                if segment_start <= match.start() and match.end() <= segment_end]
                if not read_moments:
                    read_verb = None
            if read_verbs and moments and read_verb is not None:
                status_rows = [item["data"] for item in evidence
                               if item.get("scope") == "read_bot_status"
                               and item.get("status") == "completed"
                               and isinstance(item.get("data"), dict)
                               and (not ids or item["data"].get("bot_id") in ids)]
                if not ids and len({row.get("bot_id") for row in status_rows}) > 1:
                    return False
                status_reads = [at for row in status_rows if (at := _utc(row.get("read_at"))) is not None]
                for moment in read_moments:
                    claim = _claimed_moment(moment.group(0))
                    if claim is not None:
                        if not any(_same_moment(claim, at) for at in status_reads):
                            return False
                    else:
                        clock = re.match(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"
                                         r"(?::(?P<second>\d{2}))?\s*(?P<zone>UTC|CET|CEST)",
                                         moment.group(0), re.I)
                        if clock is None or not any(
                            local.hour == int(clock["hour"]) and local.minute == int(clock["minute"])
                            and (clock["second"] is None or local.second == int(clock["second"]))
                            and local.tzname() == clock["zone"].upper()
                            for at in status_reads
                            for local in (at if clock["zone"].upper() == "UTC" else at.astimezone(_AMSTERDAM),)
                        ):
                            return False
                for moment in reversed(read_moments):
                    clause = clause[:moment.start()] + " " * (moment.end() - moment.start()) + clause[moment.end():]
        latest_claim = bool(re.search(r"\b(?:laatste|nieuwste|actuele|huidige|latest|current)\b", clause, re.I))
        report_claim = bool(re.search(r"\b(?:dagrapport|ochtendrapport|rapportmomentopname|rapport)\b", clause, re.I))
        historical_clause = bool(re.search(
            r"\b(?:historisch\w*|afgesloten|dossier\s*#\s*\d+|"
            r"trade\s*#\s*\d+|Paper[- ]?exit|Paper[- ]?uitstap)\b", clause, re.I,
        ))
        if historical_clause and latest_claim:
            return False
        historical_scope = historical_clause or (
            historical_question and not latest_claim and not current_requested and not report_claim
        )
        scoped_decisions = ([historical_decision] if historical_decision else []) \
            if historical_scope else decisions
        relevant = [(bot_id, symbol, at) for bot_id, symbol, at in scoped_decisions
                    if not ids or bot_id in ids]
        named = [(bot_id, symbol, at) for bot_id, symbol, at in relevant
                 if symbol and re.search(rf"\b{re.escape(symbol)}\b", clause, re.I)]
        relevant = named or relevant
        if not relevant:
            if re.search(r"\b(?:(?:bot)?besluit\w*|(?:bot)?besliss\w*|"
                         r"(?:bot)?beoordel\w*|hold)\b", clause, re.I) and (
                _DATED_MOMENT.search(clause) or _ZONED_CLOCK.search(clause)
            ):
                return False
            continue
        # A report can correctly show its own earlier bot snapshot. An
        # unqualified claim about the latest/current decision must instead
        # match the owner-scoped decision read for that bot.
        decision_claim = bool(re.search(
            r"\b(?:besluit\w*|besliss\w*|beoordel\w*|hold)\b", clause, re.I,
        ))
        has_clock_claim = bool(_DATED_MOMENT.search(clause) or _ZONED_CLOCK.search(clause))
        # Only the deterministic, typed-read recovery may distinguish its
        # clockless status/plan sentences from a current decision claim.
        # Free model text keeps the stricter original boundary.
        needs_current = ((latest_claim or current_requested) and not report_claim
                         and (not typed_recovery or decision_claim or has_clock_claim))
        if needs_current:
            current = [(bot_id, symbol, at) for bot_id, symbol, at in current_decisions
                       if not ids or bot_id in ids]
            named_current = [(bot_id, symbol, at) for bot_id, symbol, at in current
                             if symbol and re.search(rf"\b{re.escape(symbol)}\b", clause, re.I)]
            relevant = named_current or current
            if not relevant:
                return False
        following = clause[subject.end():]
        dated = list(_DATED_MOMENT.finditer(following))
        if dated:
            for match in dated:
                if re.search(r"\b(?:indicator\w*|koers\w*|prijs\w*|portfolio|portefeuille|"
                             r"rapport\w*|score\w*)\b", following[:match.start()], re.I):
                    continue
                claim = _claimed_moment(match.group(0))
                if (claim and re.search(r"\b(?:geen|no|nicht|none)\b", clause[:match.start() + subject.end()], re.I)
                        and not re.search(r"\b(?:geen|no|nicht)\s+(?:nieuwe?|actuele?|latest|current)\b",
                                          clause[:match.start() + subject.end()], re.I)
                        and any(_same_moment(claim, at) for _, _, at in relevant)):
                    return False
                if claim and any(_same_moment(claim, at) for _, _, at in relevant):
                    continue
                if invalid.search(following[match.end():match.end() + 55]):
                    continue
                return False
        else:
            for match in _ZONED_CLOCK.finditer(following):
                if re.search(r"\b(?:indicator\w*|koers\w*|prijs\w*|portfolio|portefeuille|"
                             r"rapport\w*|score\w*)\b", following[:match.start()], re.I):
                    continue
                clock = re.match(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"
                                 r"(?::(?P<second>\d{2}))?\s*(?P<zone>UTC|CET|CEST)",
                                 match.group(0), re.I)
                if clock is None:
                    continue
                if (re.search(r"\b(?:geen|no|nicht|none)\b", clause[:match.start() + subject.end()], re.I)
                        and not re.search(r"\b(?:geen|no|nicht)\s+(?:nieuwe?|actuele?|latest|current)\b",
                                          clause[:match.start() + subject.end()], re.I)
                        and any(
                            local.hour == int(clock["hour"]) and local.minute == int(clock["minute"])
                            and (clock["second"] is None or local.second == int(clock["second"]))
                            and local.tzname() == clock["zone"].upper()
                            for _, _, at in relevant
                            for local in (at if clock["zone"].upper() == "UTC" else at.astimezone(_AMSTERDAM),)
                        )):
                    return False
                if any(
                    local.hour == int(clock["hour"]) and local.minute == int(clock["minute"])
                    and (clock["second"] is None or local.second == int(clock["second"]))
                    and local.tzname() == clock["zone"].upper()
                    for _, _, at in relevant
                    for local in (at if clock["zone"].upper() == "UTC" else at.astimezone(_AMSTERDAM),)
                ):
                    continue
                if invalid.search(following[match.end():match.end() + 55]):
                    continue
                return False
    return True


def source_moment_repair_facts(evidence: tuple[dict[str, Any], ...]) -> list[dict[str, str]]:
    """Give a read-only answer retry the exact, source-scoped clock facts.

    The verifier still decides whether a claim is valid. This projection only
    includes observed instants, never prices, portfolio balances or identities.
    """
    moments: dict[tuple[str, str], datetime] = {}
    for item in evidence:
        if item.get("status") != "completed" or not isinstance(item.get("data"), dict):
            continue
        data = item["data"]
        scope = str(item.get("scope") or "")
        if scope == "read_market_snapshot":
            symbol = str(data.get("symbol") or "").upper()
            quote = str(data.get("quote_currency") or "").upper()
            if not symbol or not quote or data.get("price") is None:
                continue
            label = f"{symbol}/{quote}"
            value = data.get("source_observed_at_utc") or data.get("source_observed_at") or data.get("as_of")
            kind = "quote_source"
        elif scope == "read_portfolio":
            label, value, kind = "portfolio", data.get("read_at"), "read_time"
        elif scope == "read_bot_status":
            label, value, kind = str(data.get("bot_id") or "bot"), data.get("read_at"), "bot_status_read_time"
        elif scope == "read_latest_report":
            label, value, kind = "report", data.get("generated_at"), "generation_time"
            snapshot = data.get("score_source_snapshot")
            report = snapshot.get("report_v2") if isinstance(snapshot, dict) else None
            automation = report.get("automation") if isinstance(report, dict) else None
            for bot in automation.get("bots", []) if isinstance(automation, dict) else []:
                if not isinstance(bot, dict):
                    continue
                decision = bot.get("latest_decision")
                observed = _utc(decision.get("at")) if isinstance(decision, dict) else None
                if observed:
                    bot_label = str(bot.get("bot_id") or bot.get("bot_name") or bot.get("symbol") or "bot")
                    moments[("report_bot_decision", bot_label)] = observed
            for asset in snapshot.get("assets", []) if isinstance(snapshot, dict) else []:
                if not isinstance(asset, dict):
                    continue
                market = asset.get("market_snapshot")
                report_observed = _utc(market.get("as_of")) if isinstance(market, dict) else None
                pair = str(asset.get("pair") or asset.get("display_symbol") or "").upper()
                if report_observed and pair:
                    key = ("report_quote_source", pair)
                    moments[key] = max(report_observed, moments.get(key, report_observed))
        elif scope == "read_review_history":
            for row in data.get("latest_bot_decisions") or []:
                if not isinstance(row, dict):
                    continue
                observed = _utc(row.get("decision_at"))
                if observed:
                    bot_label = str(row.get("bot_id") or row.get("bot_name") or row.get("symbol") or "bot")
                    moments[("current_bot_decision", bot_label)] = observed
            continue
        else:
            continue
        observed = _utc(value)
        if observed is None:
            continue
        key = (kind, label)
        moments[key] = max(observed, moments.get(key, observed))
    facts = []
    for (kind, label), observed in list(moments.items())[:16]:
        facts.append({
            "kind": kind, "source": label,
            "utc": observed.isoformat(timespec="seconds"),
            "amsterdam": observed.astimezone(_AMSTERDAM).isoformat(timespec="seconds"),
        })
    return facts


def complete_requested_bot_status_read_time(
    answer: str, evidence: tuple[dict[str, Any], ...], *, question: str,
    user_time_zone: str | None,
) -> str:
    """Include the separately requested status read clock, using its own typed read."""
    if not (re.search(r"\bbotstatus\b", question, re.I)
            and re.search(r"\bbronmomenten?\b", question, re.I)):
        return answer
    status_clauses = [part[match.start():]
                      for part in re.split(r"(?<=[.!?])\s+|\n+|;\s*", answer)
                      for match in [re.search(r"\bbotstatus\b", part, re.I)] if match]
    status_clock = re.compile(
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|CET|CEST|[A-Za-z_]+/[A-Za-z_]+)\b", re.I,
    )
    status_clauses = [re.split(r"\b(?:bot)?besluit\b|\bbeslissing\b|\bHold\b", part,
                               maxsplit=1, flags=re.I)[0]
                      for part in status_clauses]
    # A shared "botstatus en Paper-portefeuille" clock does not show the two
    # independently read source moments. State the bot read separately.
    standalone_clock = any(
        status_clock.search(part)
        and not re.search(r"\b(?:portefeuille|portfolio|botkas|paper[- ]kas)\b", part, re.I)
        for part in status_clauses
    )
    if not status_clauses or standalone_clock:
        return answer
    reads = [
        (item["data"].get("bot_id"), str(item.get("asset") or "").upper(),
         observed, {key: value for key, value in item["data"].items() if key != "read_at"})
        for item in evidence
        if item.get("scope") == "read_bot_status" and item.get("status") == "completed"
        and isinstance(item.get("data"), dict)
        if (observed := _utc(item["data"].get("read_at"))) is not None
    ]
    # A single response can reread the same bot while gathering decision and
    # portfolio facts. Only a different bot/asset makes the source ambiguous.
    if (not reads or len({(bot_id, asset) for bot_id, asset, _, _ in reads}) != 1
            or any(row[3] != reads[0][3] for row in reads[1:])):
        return answer
    bot_id, asset, read_at, _ = max(reads, key=lambda row: row[2])
    named_ids = {int(match.group(1)) for value in (question, answer)
                 for match in re.finditer(r"\bbot\s*#?\s*(\d+)\b", value, re.I)}
    if len(named_ids) > 1 or (named_ids and bot_id != next(iter(named_ids))):
        return answer
    named_assets = mentioned_catalog_symbols(f"{question}\n{answer}")
    if len(named_assets) > 1 or (named_assets and asset != next(iter(named_assets))):
        return answer
    try:
        zone = ZoneInfo(user_time_zone or "UTC")
    except (KeyError, ValueError):
        zone = timezone.utc
    local = read_at.astimezone(zone)
    # Keep the user's IANA zone explicit when its abbreviation is ambiguous.
    zone_label = local.tzname() if isinstance(zone, ZoneInfo) and zone.key == "Europe/Amsterdam" else (
        zone.key if isinstance(zone, ZoneInfo) else "UTC"
    )
    month_names = ("januari", "februari", "maart", "april", "mei", "juni", "juli",
                   "augustus", "september", "oktober", "november", "december")
    moment = f"{local.day} {month_names[local.month - 1]} {local.year} om {local:%H:%M:%S} {zone_label}"
    return f"{answer.rstrip()}\n- Botstatus opnieuw gelezen: {moment}."


def current_source_moments_supported(
    answer: str, evidence: tuple[dict[str, Any], ...], *, question: str | None = None,
    diagnostics: list[str] | None = None,
    typed_recovery: bool = False,
    user_time_zone: str | None = None,
) -> bool:
    """Check stated quote, portfolio and report times against their own reads."""
    def reject(rule: str) -> bool:
        if diagnostics is not None:
            diagnostics.append(rule)
        return False

    if not _bot_decision_clocks_supported(
        answer, evidence, question=question, typed_recovery=typed_recovery,
        user_time_zone=user_time_zone,
    ):
        return reject("bot_decision_clock_mismatch")

    # A shared status/portfolio sentence asserts one clock for two independent
    # reads. Both sources must really have that clock before it may be shown.
    for shared in re.finditer(
        r"\bbotstatus\s+en\s+(?:de\s+)?(?:Paper[- ])?portefeuille\b[^.!?\n]*", answer, re.I,
    ):
        dated_matches = list(_DATED_MOMENT.finditer(shared.group(0)))
        bare_matches = [clock for clock in _ZONED_CLOCK.finditer(shared.group(0))
                        if not any(dated.start() <= clock.start() and clock.end() <= dated.end()
                                   for dated in dated_matches)]
        if len(dated_matches) + len(bare_matches) > 1:
            return reject("shared_status_portfolio_multiple_clocks")
        stated = _claimed_moment(shared.group(0))
        bare_clock = bare_matches[0] if stated is None and bare_matches else None
        if stated is None and bare_clock is None:
            continue
        def matches_shared_clock(at: datetime) -> bool:
            if stated is not None:
                return _same_moment(stated, at)
            clock = re.fullmatch(
                r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*"
                r"(?P<zone>UTC|CET|CEST)", bare_clock.group(0), re.I,
            )
            if clock is None:
                return False
            zone = clock["zone"].upper()
            local = at if zone == "UTC" else at.astimezone(_AMSTERDAM)
            return (local.tzname() == zone and local.hour == int(clock["hour"])
                    and local.minute == int(clock["minute"])
                    and (clock["second"] is None or local.second == int(clock["second"])))
        status_rows = [item for item in evidence
                       if item.get("scope") == "read_bot_status"
                       and item.get("status") == "completed"
                       and isinstance(item.get("data"), dict)]
        status_reads = [_utc(item["data"].get("read_at")) for item in status_rows]
        portfolio_reads_for_claim = [_utc(item["data"].get("read_at")) for item in evidence
                                     if item.get("scope") == "read_portfolio"
                                     and item.get("status") == "completed"
                                     and isinstance(item.get("data"), dict)]
        status_reads = [at for at in status_reads if at is not None]
        portfolio_reads_for_claim = [at for at in portfolio_reads_for_claim if at is not None]
        if (not status_reads or not portfolio_reads_for_claim
                or len({(item["data"].get("bot_id"), str(item.get("asset") or "").upper())
                        for item in status_rows}) != 1
                or any({key: value for key, value in item["data"].items() if key != "read_at"}
                       != {key: value for key, value in status_rows[0]["data"].items()
                           if key != "read_at"} for item in status_rows[1:])
                or not matches_shared_clock(max(status_reads))
                or not matches_shared_clock(max(portfolio_reads_for_claim))):
            return reject("shared_status_portfolio_clock_mismatch")

    market_rows: dict[tuple[str, str], datetime] = {}
    portfolio_reads: list[datetime] = []
    report_generations: list[datetime] = []
    report_quote_sources: list[tuple[str, datetime]] = []
    for item in evidence:
        if item.get("status") != "completed" or not isinstance(item.get("data"), dict):
            continue
        data = item["data"]
        if item.get("scope") == "read_market_snapshot":
            observed = _utc(data.get("source_observed_at_utc") or data.get("source_observed_at")
                            or data.get("as_of"))
            symbol = str(data.get("symbol") or "").upper()
            quote = str(data.get("quote_currency") or "").upper()
            if observed and symbol and quote and data.get("price") is not None:
                key = (symbol, quote)
                market_rows[key] = max(observed, market_rows.get(key, observed))
        elif item.get("scope") == "read_portfolio":
            observed = _utc(data.get("read_at"))
            if observed:
                portfolio_reads.append(observed)
        elif item.get("scope") == "read_latest_report":
            generated = _utc(data.get("generated_at"))
            if generated:
                report_generations.append(generated)
            snapshot = data.get("score_source_snapshot")
            for asset in snapshot.get("assets", []) if isinstance(snapshot, dict) else []:
                if not isinstance(asset, dict):
                    continue
                market = asset.get("market_snapshot")
                observed = _utc(market.get("as_of")) if isinstance(market, dict) else None
                pair = str(asset.get("pair") or asset.get("display_symbol") or "").upper()
                if observed and pair:
                    report_quote_sources.append((pair, observed))

    # A user asking for all report/quote moments in CET/CEST should receive
    # the saved report quote source converted too, not only its UTC clock.
    if question and re.search(r"\b(?:CET|CEST)\b", question, re.I) and re.search(
        r"\b(?:dagrapport|ochtendrapport|rapport|report)\b", question, re.I,
    ) and re.search(r"\b(?:koersbron|bronmoment|source\s+time)\b", question, re.I):
        requested_pairs = {match.group(0).upper() for match in re.finditer(
            r"\b[A-Z][A-Z0-9]*/(?:EUR|USD|USDT)\b", question, re.I,
        )}
        relevant = [observed for pair, observed in report_quote_sources
                    if not requested_pairs or pair in requested_pairs]
        if len(relevant) == 1 and not any(
            claim is not None and _same_moment(claim, relevant[0])
            and match.group("zone" if match.group("zone") else "iso_zone").upper() in {"CET", "CEST"}
            for match in _DATED_MOMENT.finditer(answer)
            for claim in (_claimed_moment(match.group(0)),)
        ):
            return reject("requested_report_quote_local_time_missing")

    # A report's UTC and Amsterdam times must describe the same instant. The
    # model may put the local clock in parentheses without a repeated date,
    # which the dated quote checks below cannot validate.
    if len(report_generations) == 1:
        generated = report_generations[0]
        local = generated.astimezone(_AMSTERDAM)
        for marker in re.finditer(
            r"\b(?:gegenereerd|opgesteld|rapportmoment(?:opname)?|generated)\b",
            answer, re.I,
        ):
            fragment = re.split(r"[.!?\n;]", answer[marker.end():marker.end() + 130], maxsplit=1)[0]
            first = _REPORT_CLOCK.search(fragment[:75])
            if first is None or re.search(
                r"\b(?:koersbron|prijsbron|bronmeting|koersbronmoment)\b",
                fragment[:first.start()], re.I,
            ):
                continue
            # Only an immediately parenthesized conversion belongs to this
            # report time. A later clock after "en de koersbron" is another fact.
            parenthesized = re.match(r"\s*\(\s*(.*?)\s*\)", fragment[first.end():])
            paired = _REPORT_CLOCK.match(parenthesized[1].strip()) if parenthesized else None
            for clock in (first, paired):
                if clock is None:
                    continue
                zone = clock["zone"].upper()
                expected = generated if zone == "UTC" else local
                claimed = (int(clock["hour"]), int(clock["minute"]), int(clock["second"] or 0))
                actual = (expected.hour, expected.minute,
                          expected.second if clock["second"] is not None else 0)
                if claimed != actual:
                    return reject("report_generation_clock_mismatch")
                if zone != "UTC" and zone != local.tzname():
                    return reject("report_generation_zone_mismatch")

    # A table can claim a current source time without giving a price. The
    # sentence-level price verifier cannot see such a claim.
    source_header = re.compile(
        r"\|\s*(?:(?:koers|markt)?bronmoment|quote\s+source\s+time|source\s+time)\s*\|",
        re.I,
    )
    for table_block in re.split(r"\n\s*\n", answer):
        header = source_header.search(table_block)
        if header is None:
            continue
        rows_text = table_block[header.end():]
        next_header = re.search(
            r"\|\s*(?:Instrument|Asset|Symbool|Symbol)\s*\|\s*"
            r"(?:Type|Benchmark|Markt|Market|Categorie|Category)\b",
            rows_text, re.I,
        )
        if next_header:
            rows_text = rows_text[:next_header.start()]
        for row in re.finditer(
            r"\|\s*(?P<symbol>[A-Z][A-Z0-9]*(?:/(?:EUR|USD|USDT))?)\s*\|"
            r"(?:\s*[^|\n]*\|){1,2}\s*(?P<moment>[^|\n]+)\|",
            rows_text, re.I,
        ):
            label = row.group("symbol").upper()
            if label in {"INSTRUMENT", "ASSET", "SYMBOOL", "SYMBOL"}:
                continue
            symbol, _, quoted = label.partition("/")
            claim = _claimed_moment(row.group("moment"))
            candidates = [moment for (asset, unit), moment in market_rows.items()
                          if asset == symbol and (not quoted or unit == quoted)]
            if claim is None or not candidates or not _same_moment(claim, max(candidates)):
                return reject("quote_source_table_row_mismatch")

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        market_claim = re.search(
            r"\b(?:nieuwste|laatste|actuele|huidige|latest|current)\b"
            r"[^.!?\n]{0,100}\b(?:(?:koers|markt|quote)?bronmoment|"
            r"(?:quote\s+)?source\s+time)\b",
            sentence, re.I,
        )
        if market_claim:
            prefix = sentence[:market_claim.start()]
            if re.search(
                r"\b(?:oud(?:e|er)?|vorige|historisch(?:e)?|older|previous)\b"
                r"[^.!?]{0,35}\b(?:dagrapport|ochtendrapport|rapport|report)\b",
                prefix, re.I,
            ) and not re.search(r"\b(?:maar|terwijl|whereas|but)\b|;", prefix, re.I):
                continue
            suffix = sentence[market_claim.end():market_claim.end() + 100]
            if _ZONED_CLOCK.search(suffix):
                dated = _DATED_MOMENT.search(suffix)
                if dated and re.search(
                    r"\b(?:oud(?:e|er)?|vorige|historisch(?:e)?|older|previous)\b"
                    r"[^.!?]{0,35}\b(?:dagrapport|ochtendrapport|rapport|report)\b",
                    suffix[:dated.start()], re.I,
                ):
                    continue
                claim = _claimed_moment(suffix)
                pair_pattern = (
                    r"\b(?P<symbol>[A-Z][A-Z0-9]*)/(?P<quote>EUR|USD|USDT)\b"
                )
                # A sentence may compare a setup and a separate bot before
                # naming the quote whose source time follows. Scope the pair
                # to the actual source-time claim when that claim names one.
                claim_pairs = {
                    (match.group("symbol").upper(), match.group("quote").upper())
                    for match in re.finditer(pair_pattern, market_claim.group(0), re.I)
                }
                pairs = claim_pairs or {
                    (match.group("symbol").upper(), match.group("quote").upper())
                    for match in re.finditer(pair_pattern, sentence, re.I)
                }
                symbols = {symbol for symbol, _ in pairs} if claim_pairs else {
                    symbol for symbol, _ in market_rows if re.search(
                        rf"\b{re.escape(symbol)}\b", sentence, re.I,
                    )
                }
                candidates = [moment for key, moment in market_rows.items()
                              if key in pairs] if pairs else [
                                  moment for (symbol, _), moment in market_rows.items()
                                  if not symbols or symbol in symbols
                              ]
                if claim is None or len(candidates) != 1 or len(symbols) > 1 or not _same_moment(
                    claim, candidates[0],
                ):
                    return reject("current_quote_source_prose_mismatch")

    # A concise answer to a latest-price question may consist only of a price,
    # provider and timestamp. It has no "bronmoment" label or asset name to
    # trigger the prose check above, but the question and tool read identify
    # the current quote unambiguously.
    if question and re.search(
        r"\b(?:nieuwste|laatste|actuele|huidige|latest|current)\b"
        r"(?:(?!\b(?:score|indicator\w*|benchmark|setup|bot|plan)\b)[^.!?\n]){0,80}"
        r"\b(?:koers|prijs|price|quote)\b",
        question, re.I,
    ):
        requested_pairs = {(match.group("symbol").upper(), match.group("quote").upper())
                           for match in re.finditer(
                               r"\b(?P<symbol>[A-Z][A-Z0-9]*)/(?P<quote>EUR|USD|USDT)\b",
                               question, re.I,
                           )}
        requested_symbols = {symbol for symbol, _ in market_rows if re.search(
            rf"\b{re.escape(symbol)}\b", question, re.I,
        )}
        candidates = [moment for key, moment in market_rows.items()
                      if key in requested_pairs] if requested_pairs else [
                          moment for (symbol, _), moment in market_rows.items()
                          if not requested_symbols or symbol in requested_symbols
                      ]
        if len(candidates) == 1:
            sentences = re.split(
                r"(?<=[.!?])\s+|\n+|;\s*|\b(?:maar|but|terwijl|whereas)\b\s*|"
                r"\ben\s+(?=(?:de\s+)?(?:nieuwste|laatste|actuele|huidige)\b)",
                answer, flags=re.I,
            )
            quote_cue = re.compile(r"\b(?:koers|prijs|price|quote|USD|EUR|USDT)\b|[$€]", re.I)
            unrelated_moment = re.compile(
                r"\b(?:oud(?:e|er)?|vorige|historisch(?:e)?|older|previous|"
                r"dagrapport|rapport|report|portefeuille\w*|portfolio\w*|"
                r"Paper[- ]?(?:waardering|kas(?:stand)?|saldo|balans)|plan|setup|"
                r"strategie|bot|order|indicator\w*|technisch\w*|rsi|macd|"
                r"ma\d+|candle\w*)\b|\banalyse\s+is\s+(?:aangemaakt|bijgewerkt)\b",
                re.I,
            )
            for index, sentence in enumerate(sentences):
                if not _ZONED_CLOCK.search(sentence):
                    continue
                dated = _DATED_MOMENT.search(sentence)
                before_date = sentence[:dated.start()] if dated else sentence
                unrelated = list(unrelated_moment.finditer(before_date))
                if unrelated:
                    current_quotes = list(re.finditer(
                        r"\b(?:nieuwste|actuele|huidige|latest|current)\b"
                        r"[^.!?\n]{0,100}\b(?:koers|prijs|price|quote)\b",
                        before_date, re.I,
                    ))
                    if not current_quotes or current_quotes[-1].start() < unrelated[-1].end():
                        continue
                    sentence = sentence[current_quotes[-1].start():]
                if re.match(r"\s*(?:beurs\s+nu|market\s+(?:is\s+)?(?:open|closed))\b", sentence, re.I):
                    continue
                dated_claim = _DATED_MOMENT.search(sentence)
                current_quote_text = sentence[:dated_claim.end()] if dated_claim else sentence
                nearby = sentences[max(0, index - 2):index] + [current_quote_text]
                if not any(quote_cue.search(part) and not unrelated_moment.search(part)
                           for part in nearby):
                    continue
                claim = _claimed_moment(sentence)
                if claim is None or not _same_moment(claim, candidates[0]):
                    return reject("latest_price_context_clock_mismatch")

    # "Fresh portfolio read" refers to read_at, not the oldest valuation
    # quote. Check its declared zone as well as its wall clock.
    for sentence in re.split(
        r"(?<=[.!?])\s+|\n+|;\s*|"
        r"(?:,\s*|\s+en\s+)(?=(?:de\s+)?(?:bot\s*status\w*|botcheck|botbesliss\w*|botbeoordeling\w*|"
        r"benchmarkscore|scorerapport|koersbron)\b)",
        answer, flags=re.I,
    ):
        mentioned = re.search(
            r"\b(?:Paper[- ]?)?portefeuille(?:uitlezing|lezing|meting|waardering)?\b|"
            r"\bPaper[- ]?snapshot\b|"
            r"\bPaper[- ]?(?:waardering|kas(?:stand)?|saldo|balans)\b",
            sentence, re.I,
        )
        if not mentioned:
            continue
        nearby_prefix = sentence[max(0, mentioned.start() - 25):mentioned.start()]
        if re.search(r"\b(?:oud(?:e|er)?|vorige|historisch(?:e)?|older|previous)\s*$",
                     nearby_prefix, re.I):
            continue
        if not re.search(
            r"\b(?:vers(?:e)?|actueel|actuele|huidige|nieuwste|opgehaald|uitgelezen|"
            r"uitlezing|meting|waardering|portefeuille(?:uitlezing|lezing|meting|waardering)?|snapshot|read|retrieved|current|latest)\b",
            sentence, re.I,
        ):
            continue
        following = sentence[mentioned.end():]
        claim = _claimed_moment(following)
        zoned_clocks = list(_ZONED_CLOCK.finditer(following))
        clocks = list(_REPORT_CLOCK.finditer(following))
        prefix = sentence[:mentioned.start()]
        prefix_dates = list(_DATE_ONLY.finditer(prefix))
        prefix_years_supported = len(re.findall(r"\b20\d{2}\b", prefix)) == len(prefix_dates)
        # A portfolio read may be stated as a zoned time without repeating
        # today's date. Match that clock to a read from this turn, while a
        # stated date must still match the full source instant.
        def clock_matches_read(clock: re.Match[str]) -> bool:
            for observed in portfolio_reads:
                local = observed if clock["zone"].upper() == "UTC" else observed.astimezone(_AMSTERDAM)
                if (local.hour == int(clock["hour"])
                        and local.minute == int(clock["minute"])
                        and (clock["second"] is None or local.second == int(clock["second"]))
                        and local.tzname() == clock["zone"].upper()):
                    return True
            return False

        clocks_supported = len(clocks) == len(zoned_clocks) and all(
            clock_matches_read(clock) for clock in clocks
        )
        prefix_dates_supported = all(
            any(
                parsed is not None and _same_moment(parsed, observed)
                for observed in portfolio_reads
                for parsed in (_claimed_moment(f"{date_match.group(0)} {clock.group(0)}"),)
            )
            for date_match in prefix_dates for clock in clocks
        )
        if zoned_clocks and (
            not portfolio_reads or not clocks_supported
            or not prefix_years_supported or not prefix_dates_supported
            or (claim is not None and not any(
                _same_moment(claim, observed) for observed in portfolio_reads
            ))
            or (claim is None and re.search(r"\b20\d{2}\b", following) is not None)
        ):
            return reject("portfolio_read_clock_mismatch")
    return True
