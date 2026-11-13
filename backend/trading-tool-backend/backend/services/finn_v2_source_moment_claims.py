"""Check user-facing source moments against the facts read for this turn."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo


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


def current_source_moments_supported(answer: str, evidence: tuple[dict[str, Any], ...]) -> bool:
    """Reject wrong current quote table moments and current portfolio read times.

    Historical reports and saved plan timestamps are outside this check.
    """
    market_rows: dict[tuple[str, str], datetime] = {}
    portfolio_reads: list[datetime] = []
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
                return False

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
                pairs = {(match.group("symbol").upper(), match.group("quote").upper())
                         for match in re.finditer(
                             r"\b(?P<symbol>[A-Z][A-Z0-9]*)/(?P<quote>EUR|USD|USDT)\b",
                             sentence, re.I,
                         )}
                symbols = {symbol for symbol, _ in market_rows if re.search(
                    rf"\b{re.escape(symbol)}\b", sentence, re.I,
                )}
                candidates = [moment for key, moment in market_rows.items()
                              if key in pairs] if pairs else [
                                  moment for (symbol, _), moment in market_rows.items()
                                  if not symbols or symbol in symbols
                              ]
                if claim is None or len(candidates) != 1 or len(symbols) > 1 or not _same_moment(
                    claim, candidates[0],
                ):
                    return False

    # "Fresh portfolio read" refers to read_at, not the oldest valuation
    # quote. Check its declared zone as well as its wall clock.
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        mentioned = re.search(r"\b(?:Paper[- ]?)?portefeuille\b|\bPaper[- ]?snapshot\b", sentence, re.I)
        if not mentioned:
            continue
        nearby_prefix = sentence[max(0, mentioned.start() - 25):mentioned.start()]
        if re.search(r"\b(?:oud(?:e|er)?|vorige|historisch(?:e)?|older|previous)\s*$",
                     nearby_prefix, re.I):
            continue
        if not re.search(
            r"\b(?:vers(?:e)?|actueel|actuele|huidige|nieuwste|opgehaald|uitgelezen|"
            r"uitlezing|snapshot|read|retrieved|current|latest)\b", sentence, re.I,
        ):
            continue
        following = sentence[mentioned.end():]
        claim = _claimed_moment(following)
        if _ZONED_CLOCK.search(following) and (
            claim is None or not portfolio_reads or not any(
                _same_moment(claim, observed) for observed in portfolio_reads
            )
        ):
            return False
    return True
