"""Daily report prose over the same owner-scoped facts FINN uses elsewhere."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.infrastructure.database import ASYNC_DATABASE_URL
from backend.infrastructure.repositories.asset_catalog_repository import AssetCatalogRepository
from backend.domain.indicator_display import indicator_display_name
from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.utils.openai_client import ask_gpt_json

logger = logging.getLogger(__name__)


REPORT_SECTIONS = (
    "executive_summary", "market_analysis", "macro_context", "technical_analysis",
    "setup_validation", "strategy_implication", "bot_strategy", "outlook",
)

REPORT_V2_SECTIONS = (
    "retrospective", "portfolio", "analysis", "plan", "automation", "outlook_v2",
)

REPORT_WEEKDAYS = {
    "nl": ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
}


def _report_v2_prompt_plan(row: dict[str, Any], locale: str) -> dict[str, Any]:
    """Give the writer a weekday name while keeping the frozen plan's numeric code."""
    projected = {key: value for key, value in row.items() if key != "dca_day"}
    if row.get("dca_frequency") == "weekly":
        try:
            day = int(row.get("dca_day"))
        except (TypeError, ValueError):
            day = 0
        if 1 <= day <= 7:
            projected["purchase_weekday"] = REPORT_WEEKDAYS.get(locale, REPORT_WEEKDAYS["en"])[day - 1]
    return projected

REPORT_V2_TERMINOLOGY = {
    "nl": {
        "market score": "marktscore", "technical scores": "technische scores",
        "technical score": "technische score", "total equity": "totale portefeuillewaarde",
        "p&l": "resultaat", "outlook": "vooruitblik", "cash": "kassaldo",
        "equity": "portefeuillewaarde",
    },
    "de": {
        "market score": "Marktbewertung", "technical scores": "technische Bewertungen",
        "technical score": "technische Bewertung", "total equity": "Gesamtportfoliowert",
        "p&l": "Ergebnis", "outlook": "Ausblick", "cash": "Barguthaben",
        "equity": "Portfoliowert",
    },
}


def _localize_report_v2_terms(value: str, locale: str, protected_names: list[str]) -> str:
    """Translate leaked source labels without rewriting FINN's report narrative."""
    glossary = REPORT_V2_TERMINOLOGY.get(locale)
    if not glossary:
        return value
    protected_spans = [match.span() for name in protected_names if name
                       for match in re.finditer(re.escape(name), value, re.I)]
    terms = "|".join(re.escape(term) for term in sorted(glossary, key=len, reverse=True))
    pattern = re.compile(rf"(?<!\w)(?:{terms})(?!\w)", re.I)

    def translate(match: re.Match[str]) -> str:
        start, end = match.span()
        if any(start < protected_end and end > protected_start
               for protected_start, protected_end in protected_spans):
            return match.group()
        replacement = glossary[match.group().casefold()]
        begins_sentence = not value[:start].strip() or value[:start].rstrip().endswith((".", "!", "?"))
        return (replacement[:1].upper() + replacement[1:]
                if locale == "nl" and begins_sentence else replacement)

    return pattern.sub(translate, value)


def _report_source_times(value: Any) -> Any:
    """Keep source instants, but omit subsecond provider precision in reports."""
    if isinstance(value, dict):
        return {key: _report_source_times(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_report_source_times(item) for item in value]
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.replace(microsecond=0).isoformat()
    return value


def _regular_session_at(observed_at: Any, asset_class: Any, market_timezone: Any) -> str:
    """Only assert outside hours when the catalog and clock prove it.

    Being inside scheduled hours does not prove the exchange was open: holidays,
    halts and provider delays still need exchange evidence.
    """
    if str(asset_class or "").lower() not in {"stock", "equity", "etf"}:
        return "not_applicable"
    if str(market_timezone or "") not in {"America/New_York", "US/Eastern"}:
        return "unknown"
    try:
        instant = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        local = instant.astimezone(ZoneInfo(str(market_timezone)))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return "unknown"
    if local.weekday() >= 5 or not (time(9, 30) <= local.time() < time(16, 0)):
        return "outside_regular_hours"
    return "unknown"


def _report_indicator_evidence(raw: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """Project measured fields only; old interpretation/action copy is not evidence."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for category in ("market", "macro", "technical"):
        rows = raw.get(category)
        if not isinstance(rows, dict):
            continue
        result[category] = {}
        for name, entry in rows.items():
            if not isinstance(entry, dict):
                continue
            result[category][str(name)] = {
                key: _report_source_times(value) if key == "source_observed_at" else value
                for key, value in entry.items()
                if key in {"value", "score", "source_observed_at", "unit"}
                and isinstance(value, (str, int, float, type(None)))
            }
    return result


def _saved_curve(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


async def _load_context(user_id: int, period: str = "daily") -> dict[str, Any]:
    # Celery invokes this from a short-lived event loop, while preview runs in
    # a thread beside live API requests. Give each invocation its own unpooled
    # connection; disposing the application's shared engines can interrupt a
    # concurrent /report/daily/latest request.
    report_engine = create_async_engine(ASYNC_DATABASE_URL, poolclass=NullPool)
    try:
        sessions = async_sessionmaker(report_engine, expire_on_commit=False)
        async with sessions() as session:
            context = await FinnSharedContextService(session).for_user(user_id)
            symbols = [item["symbol"] for item in context.get("assets") or [] if item.get("symbol")]
            try:
                catalog = await AssetCatalogRepository(session).get_assets(symbols)
            except Exception:
                logger.warning("Report market-hours metadata unavailable", exc_info=True)
                catalog = {}
            for item in context.get("assets") or []:
                metadata = catalog.get(item["symbol"]) or {}
                item["asset_class"] = metadata.get("asset_class")
                item["market_timezone"] = metadata.get("timezone")
            # Read the same owner-scoped projections as Portfolio and the bot
            # status screen at generation time. A report must never acquire
            # newer balances or decisions merely because it was opened later.
            from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter
            from backend.services.daily_report_trader_status_service import current_daily_trader_status
            adapter = PortfolioToolAdapter(session)
            context["report_portfolios"] = {}
            for environment in ("paper", "live"):
                try:
                    result = await adapter.execute(user_id=user_id, environment=environment)
                    context["report_portfolios"][environment] = jsonable_encoder(result["data"])
                except Exception:
                    logger.warning("Report %s portfolio unavailable for user=%s", environment, user_id, exc_info=True)
                    context["report_portfolios"][environment] = {"valuation_status": "unavailable"}
            try:
                context["report_bot_status"] = await current_daily_trader_status(session, user_id)
            except Exception:
                logger.warning("Report bot status unavailable for user=%s", user_id, exc_info=True)
                context["report_bot_status"] = {"bots": [], "status": "unavailable"}
            try:
                history_start = (date.today() - timedelta(days=7) if period == "daily"
                                 else _period_start(period, date.today()) - timedelta(days=100))
                rows = (await session.execute(text("""
                    SELECT report_date, score_source_snapshot
                    FROM daily_reports
                    WHERE user_id = :user_id AND report_date < CURRENT_DATE
                      AND report_date >= :history_start
                    ORDER BY report_date DESC LIMIT 200
                """), {"user_id": user_id, "history_start": history_start})).mappings().all()
                context["report_previous"] = [
                    {"report_date": row["report_date"].isoformat(),
                     "snapshot": row["score_source_snapshot"]}
                    for row in rows if isinstance(row["score_source_snapshot"], dict)
                ]
            except Exception:
                logger.warning("Prior report snapshots unavailable for user=%s", user_id, exc_info=True)
                context["report_previous"] = []
            return context
    finally:
        await report_engine.dispose()


def _fallback_sections(context: dict[str, Any]) -> dict[str, str]:
    assets = context.get("assets") or []
    symbols = ", ".join(item.get("pair") or item["symbol"] for item in assets)
    missing = [item.get("pair") or item["symbol"] for item in assets
               if item["benchmark"].get("source_status") != "available"]
    matches = [match for item in assets for match in item["benchmark"].get("matches") or []]
    active = [match for match in matches if match.get("is_active")]
    outside = [match for match in matches if match.get("status") == "outside_conditions"]
    bots = [bot for item in assets for bot in item.get("bots") or []]
    setup_names = [str(setup.get("name")) for item in assets
                   for setup in item.get("setups") or [] if setup.get("name")]
    named_plan = ", ".join(setup_names[:3])
    if len(setup_names) > 3:
        named_plan += f" (+{len(setup_names) - 3})"
    locale = str(context.get("locale") or "nl").lower()
    if locale == "en":
        return {
            "executive_summary": f"FINN follows {symbols or 'no selected assets'}{f' with saved plans {named_plan}' if named_plan else ''}. A complete current benchmark is missing for {', '.join(missing)}." if missing else f"FINN follows {symbols or 'no selected assets'}{f' with saved plans {named_plan}' if named_plan else ''}; current benchmarks are complete where configured.",
            "market_analysis": "The market layer needs current source measurements before it can support a conclusion.",
            "macro_context": "A missing or stale macro score is unknown, not neutral market evidence.",
            "technical_analysis": "Technical timing requires current indicator measurements.",
            "setup_validation": f"Across all followed assets, there are {len(active)} confirmed current setup matches." if active
            else "There is no confirmed setup match without a complete current benchmark." if missing
            else f"There is no current setup match: {len(outside)} saved setup(s) are outside their score conditions." if outside
            else "There is no confirmed current setup match.",
            "strategy_implication": "Review a saved strategy with its linked setup and current evidence; a stored entry price is not a live entry signal.",
            "bot_strategy": f"There are {len(bots)} linked bots; their budgets do not prove available cash or an executed purchase.",
            "outlook": "At the next data refresh, check which source measurements and setup conditions are actually available.",
        }
    if locale == "de":
        return {
            "executive_summary": f"FINN beobachtet {symbols or 'noch keine ausgewählten Assets'}{f' mit den gespeicherten Plänen {named_plan}' if named_plan else ''}. Für {', '.join(missing)} fehlt ein vollständiger aktueller Benchmark." if missing else f"FINN beobachtet {symbols or 'noch keine ausgewählten Assets'}{f' mit den gespeicherten Plänen {named_plan}' if named_plan else ''}; die konfigurierten Benchmarks sind aktuell vollständig.",
            "market_analysis": "Die Marktlage braucht aktuelle Quellmessungen, bevor sie eine Schlussfolgerung stützen kann.",
            "macro_context": "Ein fehlender oder veralteter Makrowert ist unbekannt und kein neutrales Marktsignal.",
            "technical_analysis": "Für eine technische Einschätzung sind aktuelle Indikatormessungen nötig.",
            "setup_validation": f"Über alle beobachteten Assets gibt es {len(active)} bestätigte aktuelle Setup-Treffer." if active
            else "Ohne vollständigen aktuellen Benchmark gibt es keinen bestätigten Setup-Treffer." if missing
            else f"Es gibt keinen aktuellen Setup-Treffer: {len(outside)} gespeicherte Setups liegen außerhalb ihrer Score-Bedingungen." if outside
            else "Es gibt keinen bestätigten aktuellen Setup-Treffer.",
            "strategy_implication": "Prüfe eine gespeicherte Strategie mit ihrem zugehörigen Setup und aktuellen Daten; ein Einstiegspreis ist kein aktuelles Einstiegssignal.",
            "bot_strategy": f"Es gibt {len(bots)} verknüpfte Bots; ihre Budgets belegen weder verfügbares Guthaben noch einen ausgeführten Kauf.",
            "outlook": "Prüfe nach der nächsten Datenaktualisierung, welche Quellmessungen und Setup-Bedingungen tatsächlich vorliegen.",
        }
    return {
        "executive_summary": f"FINN volgt {symbols or 'nog geen geselecteerde assets'}{f' met de opgeslagen plannen {named_plan}' if named_plan else ''}. Voor {', '.join(missing)} ontbreekt een complete actuele benchmark." if missing
        else f"FINN volgt {symbols or 'nog geen geselecteerde assets'}{f' met de opgeslagen plannen {named_plan}' if named_plan else ''}; de actuele benchmarks zijn compleet waar ze zijn ingericht.",
        "market_analysis": "De marktlaag is alleen bruikbaar als de onderliggende indicatoren een actuele bronmeting hebben.",
        "macro_context": "Een ontbrekende of verouderde macro-score is geen neutrale score en geen bevestiging van het marktbeeld.",
        "technical_analysis": "De technische laag vraagt actuele indicatorbronnen voordat FINN er een timingconclusie aan verbindt.",
        "setup_validation": f"Over alle gevolgde assets zijn er {len(active)} bevestigde actuele setupmatches." if active
        else "Er is zonder complete actuele benchmark geen bevestigde setupmatch." if missing
        else f"Er is geen actuele setupmatch: {len(outside)} opgeslagen setups vallen buiten hun scorevoorwaarden." if outside
        else "Er is geen bevestigde actuele setupmatch.",
        "strategy_implication": "Vergelijk een opgeslagen strategie pas met de bijbehorende setup en actuele brongegevens; een entryprijs is geen actueel instapsignaal.",
        "bot_strategy": f"Er zijn {len(bots)} gekoppelde bots; hun budget is geen bewijs van beschikbaar kassaldo of een uitgevoerde aankoop.",
        "outlook": "Controleer bij de volgende gegevensverversing welke bronmetingen en setupvoorwaarden daadwerkelijk beschikbaar zijn.",
    }


def _report_facts(context: dict[str, Any]) -> dict[str, Any]:
    """Project shared context into report facts; never expose unverified score rows.

    ``reported_scores`` contains only currently verified components. Apply the
    source status again at this boundary so reports never recover a stale value
    if an older context producer still provides one.
    """
    assets = []
    for item in context.get("assets") or []:
        benchmark = item.get("benchmark") or {}
        source_status = benchmark.get("component_source_status") or {}
        reported = benchmark.get("reported_scores") or {}
        scores = {
            key: reported.get(key) if source_status.get(key) == "fresh" else None
            for key in ("market_score", "macro_score", "technical_score")
        }
        configuration = item.get("indicator_configuration")
        configured = {
            category: [row.get("indicator") for row in configuration.get(category, [])
                       if isinstance(row, dict) and row.get("enabled", True) and row.get("indicator")]
            for category in ("market", "macro", "technical")
        } if isinstance(configuration, dict) else None
        setups_by_id = {row.get("id"): row for row in item.get("setups") or []}
        assets.append({
            "symbol": item.get("symbol"),
            "market_id": item.get("market_id"),
            "pair": item.get("pair"),
            "display_symbol": item.get("pair") or item.get("symbol"),
            "asset_class": item.get("asset_class"),
            "market_timezone": item.get("market_timezone"),
            "market_session_at_report": _regular_session_at(
                context.get("observed_at"), item.get("asset_class"),
                item.get("market_timezone"),
            ),
            "score_status": benchmark.get("source_status"),
            "score_report_date": benchmark.get("as_of"),
            "component_source_status": source_status,
            "component_source_observed_at": _report_source_times(
                benchmark.get("component_source_observed_at") or {}
            ),
            "scores": scores,
            "benchmark_score": benchmark.get("benchmark_score") if benchmark.get("source_status") == "available" else None,
            "market_snapshot": item.get("market_snapshot") or {},
            "verified_indicator_evidence": _report_indicator_evidence(
                item.get("verified_indicator_evidence")),
            "configured_indicators": configured,
            "indicator_lookup_status": item.get("indicator_lookup_status"),
            "setups": [{"id": row.get("id"), "name": row.get("name"),
                        "timeframe": row.get("timeframe"), "setup_type": row.get("setup_type"),
                        "dca_frequency": row.get("dca_frequency"),
                        "dca_day": row.get("dca_day") if row.get("dca_frequency") == "weekly" else None,
                        "dca_month_day": row.get("dca_month_day") if row.get("dca_frequency") == "monthly" else None,
                        "min_benchmark_score": row.get("min_benchmark_score"),
                        "max_benchmark_score": row.get("max_benchmark_score")}
                       for row in item.get("setups") or []],
            "strategies": [{"id": row.get("id"), "setup_id": row.get("setup_id"),
                            "name": row.get("name"),
                            "setup_name": (setups_by_id.get(row.get("setup_id")) or {}).get("name")
                                          or row.get("setup_name"),
                            "symbol": item.get("symbol"),
                            "pair": item.get("pair"),
                            "timeframe": row.get("timeframe") or
                                         (setups_by_id.get(row.get("setup_id")) or {}).get("timeframe"),
                            "setup_type": (setups_by_id.get(row.get("setup_id")) or {}).get("setup_type"),
                            "dca_frequency": (setups_by_id.get(row.get("setup_id")) or {}).get("dca_frequency"),
                            "dca_day": (setups_by_id.get(row.get("setup_id")) or {}).get("dca_day")
                                       if (setups_by_id.get(row.get("setup_id")) or {}).get("dca_frequency") == "weekly" else None,
                            "dca_month_day": (setups_by_id.get(row.get("setup_id")) or {}).get("dca_month_day")
                                             if (setups_by_id.get(row.get("setup_id")) or {}).get("dca_frequency") == "monthly" else None,
                            "execution_mode": row.get("execution_mode"),
                            "base_amount": row.get("base_amount"),
                            "decision_curve": _saved_curve(row.get("decision_curve")),
                            "entry": row.get("entry"), "stop_loss": row.get("stop_loss"),
                            "targets": row.get("targets")}
                           for row in item.get("strategies") or []],
            "bots": [{"id": row.get("id"), "name": row.get("name"),
                      "pair": item.get("pair"), "symbol": item.get("symbol"),
                      "is_live": row.get("is_live"), "is_active": row.get("is_active")}
                     for row in item.get("bots") or []],
            "matches": [{"setup_id": row.get("setup_id"), "name": row.get("name"),
                         "symbol": row.get("symbol"), "pair": item.get("pair"),
                         "timeframe": row.get("timeframe"),
                         "status": row.get("status"), "score": row.get("score"),
                         "is_active": row.get("is_active")}
                        for row in benchmark.get("matches") or []],
        })
    return {"locale": context.get("locale"), "profile": context.get("profile"),
            "trader_context": context.get("trader_context"), "assets": assets}


def _configured_highlights(facts: dict[str, Any], category: str, locale: str) -> list[dict[str, Any]]:
    return [{"indicator": _report_indicator_label(name, locale), "symbol": item["symbol"],
             **({"pair": item["pair"]} if item.get("pair") else {})}
            for item in facts["assets"]
            for name in (item.get("configured_indicators") or {}).get(category, [])]


def _report_indicator_label(name: object, locale: str) -> str:
    key = str(name or "").strip().casefold().replace("-", "_").replace(" ", "_")
    translations = {
        "nl": {"price": "Prijs", "volume": "Volume", "change_24h": "Koerswijziging 24 uur",
               "inflation_rate": "Inflatie", "cpi": "Consumentenprijsindex"},
        "en": {"change_24h": "24-hour price change", "inflation_rate": "Inflation rate"},
        "de": {"price": "Preis", "volume": "Volumen", "change_24h": "Kursänderung 24 Stunden",
               "inflation_rate": "Inflationsrate", "cpi": "Verbraucherpreisindex"},
    }
    return translations.get(locale, translations["en"]).get(key) or indicator_display_name(name)


def _category_fact_fallback(facts: dict[str, Any], category: str, locale: str) -> str:
    """A brief source-backed fallback only when the report writer is unavailable."""
    labels = {
        "nl": ("Ingesteld", "Geen indicatoren ingesteld", "Indicatorconfiguratie niet beschikbaar", "Geen bruikbare actuele score"),
        "en": ("Configured", "No indicators configured", "Indicator configuration unavailable", "No usable current score"),
        "de": ("Eingerichtet", "Keine Indikatoren eingerichtet", "Indikatorkonfiguration nicht verfügbar", "Kein brauchbarer aktueller Wert"),
    }.get(locale, ("Configured", "No indicators configured", "Indicator configuration unavailable", "No usable current score"))
    parts = []
    for item in facts["assets"]:
        names = (item.get("configured_indicators") or {}).get(category)
        configuration = (f"{labels[0]}: {', '.join(_report_indicator_label(name, locale) for name in names)}" if names
                         else labels[1] if names is not None else labels[2])
        value = item["scores"].get(f"{category}_score")
        score = f"{value:g}/100" if isinstance(value, (int, float)) else labels[3]
        parts.append(f"{item['display_symbol']}: {configuration}; {score}.")
    return " ".join(parts)


def _market_direction_contradicts_snapshot(text: str, facts: dict[str, Any]) -> bool:
    """Reject only a universal direction claim disproved by a measured move."""
    changes = []
    for item in facts["assets"]:
        snapshot = item.get("market_snapshot") or {}
        if snapshot.get("source_status") != "fresh":
            continue
        value = snapshot.get("change_24h")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            changes.append(float(value))
    if not changes:
        return False
    all_fall = re.search(
        r"\b(?:alle|all|sämtliche)\b.{0,100}\b(?:dal\w*|daal\w*|declin\w*|fall\w*|sink\w*|rück\w*)\b",
        text, re.I,
    )
    all_rise = re.search(
        r"\b(?:alle|all|sämtliche)\b.{0,100}\b(?:stijg\w*|rise\w*|risen|rising|gain\w*|steig\w*)\b",
        text, re.I,
    )
    return bool((all_fall and any(value > 0 for value in changes)) or
                (all_rise and any(value < 0 for value in changes)))


def _report_v2_prompt_market_snapshot(snapshot: dict[str, Any], locale: str) -> dict[str, Any]:
    """Give the writer an explicit percentage instead of an ambiguous bare number."""
    projected = {key: value for key, value in snapshot.items() if key != "change_24h"}
    change = snapshot.get("change_24h")
    if isinstance(change, (int, float)) and not isinstance(change, bool):
        number = f"{float(change):+.3f}".rstrip("0").rstrip(".")
        if locale in ("nl", "de"):
            number = number.replace(".", ",")
        projected["change_24h_percent"] = f"{number}%"
    return projected


def _report_v2_analysis_claims_contradict(value: str, facts: dict[str, Any]) -> bool:
    """Check pair-scoped price changes and plan names, leaving prose to Luna."""
    assets = [item for item in facts.get("assets") or [] if item.get("display_symbol")]
    if not assets:
        return False
    by_symbol = {str(item["display_symbol"]): item for item in assets}
    # A market component and the weighted benchmark are different scores. Repair
    # this narrow, misleading phrase with the report writer before publishing.
    if re.search(r"\b(?:marktscore|market score|Marktwert)\s*\(\s*(?:benchmark|Benchmarkwert)\s*\)", value, re.I):
        return True
    names = sorted(by_symbol, key=len, reverse=True)
    starts = list(re.finditer(
        rf"(?<![\w/])({'|'.join(re.escape(name) for name in names)})\s*:", value, re.I,
    ))
    for index, start in enumerate(starts):
        symbol = start.group(1)
        item = next((row for name, row in by_symbol.items() if name.casefold() == symbol.casefold()), None)
        if item is None:
            continue
        section = value[start.end(): starts[index + 1].start() if index + 1 < len(starts) else len(value)]
        snapshot = item.get("market_snapshot") or {}
        expected = snapshot.get("change_24h") if snapshot.get("source_status") == "fresh" else None
        # Market snapshots already express change_24h in percent, not as a ratio.
        change_terms = r"(?:24[-\s]?(?:hour|uur|stunden)|24h|24u|24-?stündig|daily change)"
        claims = re.findall(rf"{change_terms}[^;\n]{{0,55}}?([+\-−]?\d+(?:[.,]\d+)?)\s*%", section, re.I)
        claims += re.findall(rf"([+\-−]?\d+(?:[.,]\d+)?)\s*%[^;\n]{{0,35}}?{change_terms}", section, re.I)
        for claim in claims:
            number = float(claim.replace("−", "-").replace(",", "."))
            if not isinstance(expected, (int, float)) or isinstance(expected, bool):
                return True
            if abs(number - float(expected)) > max(0.05, abs(float(expected)) * 0.05):
                return True
        own_names = {str(row.get("name") or "").casefold() for row in item.get("setups") or []}
        for other in assets:
            if other is item:
                continue
            for setup in other.get("setups") or []:
                name = str(setup.get("name") or "").strip()
                if name and name.casefold() not in own_names and re.search(re.escape(name), section, re.I):
                    return True
    return False


def _bot_status_section(facts: dict[str, Any], locale: str) -> str:
    bots = [bot for asset in facts["assets"] for bot in asset["bots"]]
    if not bots:
        return {
            "nl": "Er is geen bot gekoppeld aan de opgeslagen plannen.",
            "en": "No bot is linked to the saved plans.",
            "de": "Mit den gespeicherten Plänen ist kein Bot verknüpft.",
        }.get(locale, "No bot is linked to the saved plans.")
    parts = []
    for bot in bots:
        name = str(bot.get("name") or "Bot").strip()
        if bot.get("is_active") is False:
            status = {"nl": "staat gepauzeerd en neemt nu geen beslissing",
                      "en": "is paused and cannot make a decision now",
                      "de": "ist pausiert und trifft derzeit keine Entscheidung"}
        elif bot.get("is_live") is False:
            status = {"nl": "staat in Paper; een setupmatch bewijst geen uitgevoerde aankoop",
                      "en": "is in Paper; a setup match does not prove an executed purchase",
                      "de": "läuft im Paper-Modus; ein Setup-Treffer belegt keinen ausgeführten Kauf"}
        else:
            status = {"nl": "is actief; een setupmatch bewijst geen uitgevoerde aankoop",
                      "en": "is active; a setup match does not prove an executed purchase",
                      "de": "ist aktiv; ein Setup-Treffer belegt keinen ausgeführten Kauf"}
        pair = f" ({bot['pair']})" if bot.get("pair") else ""
        parts.append(f"{name}{pair} {status.get(locale, status['en'])}.")
    budget_note = {
        "nl": "Beschikbaar kassaldo is in dit rapport niet vastgesteld; een botbudget is alleen een limiet.",
        "en": "Available cash has not been established in this report; a bot budget is only a limit.",
        "de": "Verfügbares Guthaben wurde in diesem Bericht nicht festgestellt; ein Bot-Budget ist nur ein Limit.",
    }
    return " ".join([*parts, budget_note.get(locale, budget_note["en"])])


def _report_v2_comparison(context: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """Compare like-for-like saved observations, never a prose prediction."""
    previous = context.get("report_previous") or []
    if not previous:
        return {"status": "no_prior_report", "previous_date": None, "changes": [],
                "previous_observations": []}
    def observations(report: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"asset": row.get("pair") or row.get("symbol") or row.get("market_id"),
                 "benchmark_score": row.get("benchmark_score"),
                 "scores": row.get("reported_scores") or {}}
                for row in (report.get("snapshot") or {}).get("assets") or []
                if isinstance(row, dict)]
    def changes_since(report: dict[str, Any]) -> list[dict[str, Any]]:
        prior_assets = {
            (row.get("pair") or row.get("symbol") or row.get("market_id")): row
            for row in (report.get("snapshot") or {}).get("assets") or []
            if isinstance(row, dict)
        }
        changes = []
        for asset in facts["assets"]:
            key = asset.get("pair") or asset.get("symbol") or asset.get("market_id")
            old = prior_assets.get(key)
            if not old:
                continue
            before, after = old.get("benchmark_score"), asset.get("benchmark_score")
            if isinstance(before, (int, float)) and isinstance(after, (int, float)) and before != after:
                changes.append({"asset": asset["display_symbol"], "fact": "benchmark_score",
                                "before": before, "after": after})
            elif (before is None) != (after is None):
                changes.append({"asset": asset["display_symbol"], "fact": "benchmark_availability",
                                "before": before is not None, "after": after is not None})
            prior_scores = old.get("reported_scores") or {}
            current_scores = asset.get("scores") or {}
            for category in ("market_score", "macro_score", "technical_score"):
                before, after = prior_scores.get(category), current_scores.get(category)
                if (isinstance(before, (int, float)) and not isinstance(before, bool)
                        and isinstance(after, (int, float)) and not isinstance(after, bool)
                        and before != after):
                    changes.append({"asset": asset["display_symbol"], "fact": category,
                                    "before": before, "after": after})
        return changes[:30]

    latest = previous[0]
    changes = changes_since(latest)
    earliest = previous[-1] if len(previous) > 1 else None
    def previous_outlook(report: dict[str, Any] | None) -> str | None:
        value = (((report or {}).get("snapshot") or {}).get("report_v2") or {}).get("sections") or {}
        outlook = value.get("outlook_v2") if isinstance(value, dict) else None
        return outlook[:1200] if isinstance(outlook, str) else None
    return {"status": "comparable" if changes else "no_comparable_change",
            "previous_date": latest.get("report_date"), "changes": changes,
            "previous_observations": observations(latest),
            "previous_outlook": previous_outlook(latest),
            "week_earliest_date": earliest.get("report_date") if earliest else None,
            "week_changes": changes_since(earliest) if earliest else [],
            "week_earliest_outlook": previous_outlook(earliest)}


def _report_v2_period_comparison(context: dict[str, Any], facts: dict[str, Any],
                                 period: str) -> dict[str, Any]:
    """Compare pair-scoped saved snapshots from this period with its starting point.

    Daily report snapshots are evidence. A missing baseline leaves the change
    unknown; it must never become a zero score or an invented trend.
    """
    today = date.today()
    start = _period_start(period, today)
    previous = sorted((row for row in context.get("report_previous") or []
                       if isinstance(row.get("snapshot"), dict)),
                      key=lambda row: str(row.get("report_date") or ""))
    within = [row for row in previous if str(row.get("report_date") or "") >= start.isoformat()]
    before = [row for row in previous if str(row.get("report_date") or "") < start.isoformat()]
    baseline = within[0] if within else (before[-1] if before else None)
    comparison = _report_v2_comparison(
        {"report_previous": [baseline] if baseline else []}, facts)
    observations = []
    for report in within:
        for asset in (report.get("snapshot") or {}).get("assets") or []:
            if not isinstance(asset, dict):
                continue
            observations.append({
                "date": str(report.get("report_date")),
                "asset": asset.get("pair") or asset.get("symbol") or asset.get("market_id"),
                "benchmark_score": asset.get("benchmark_score"),
                "scores": asset.get("reported_scores") or {},
            })
    comparison.update({
        "period": period,
        "period_start": start.isoformat(),
        "period_end": today.isoformat(),
        "observation_days": len(within),
        "baseline_date": baseline.get("report_date") if baseline else None,
        "period_observations": observations[:150],
    })
    return comparison


def _report_v2_factual_fallbacks(context: dict[str, Any], facts: dict[str, Any],
                                  comparison: dict[str, Any], locale: str) -> dict[str, str]:
    """Short factual copy for provider failure, with no inferred trade advice."""
    legacy = _fallback_sections(context)
    snapshots = context.get("report_portfolios") or {}
    bots = (context.get("report_bot_status") or {}).get("bots") or []
    paper = snapshots.get("paper") or {}
    live = snapshots.get("live") or {}
    comparisons = comparison.get("changes") or []
    prior = comparison.get("previous_observations") or []
    period = comparison.get("period", "daily")
    period_labels = {
        "nl": {"daily": "de afgelopen zeven dagen", "weekly": "deze week", "monthly": "deze maand", "quarterly": "dit kwartaal"},
        "en": {"daily": "the past seven days", "weekly": "this week", "monthly": "this month", "quarterly": "this quarter"},
        "de": {"daily": "der letzten sieben Tage", "weekly": "dieser Woche", "monthly": "dieses Monats", "quarterly": "dieses Quartals"},
    }
    period_label = period_labels.get(locale, period_labels["en"]).get(period, period)
    change_labels = {
        "nl": {"benchmark_score": "benchmarkscore", "market_score": "marktscore",
               "macro_score": "macroscore", "technical_score": "technische score",
               "benchmark_availability": "benchmark"},
        "en": {"benchmark_score": "benchmark score", "market_score": "market score",
               "macro_score": "macro score", "technical_score": "technical score",
               "benchmark_availability": "benchmark"},
        "de": {"benchmark_score": "Benchmarkwert", "market_score": "Marktwert",
               "macro_score": "Makrowert", "technical_score": "technischer Wert",
               "benchmark_availability": "Benchmark"},
    }
    def change_text(row: dict[str, Any]) -> str:
        label = change_labels.get(locale, change_labels["en"]).get(row["fact"], row["fact"])
        def display(value: Any) -> str:
            if row["fact"] == "benchmark_availability":
                return {
                    "nl": "beschikbaar" if value else "niet beschikbaar",
                    "en": "available" if value else "unavailable",
                    "de": "verfügbar" if value else "nicht verfügbar",
                }.get(locale, "available" if value else "unavailable")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                number = f"{float(value):g}"
                return f"{number.replace('.', ',') if locale in ('nl', 'de') else number}/100"
            return "—"
        return f"{row['asset']} {label}: {display(row['before'])} → {display(row['after'])}"
    if locale == "en":
        retrospective = (f"Compared with {comparison['previous_date']}: " + "; ".join(
            change_text(row) for row in comparisons)
            if comparisons else f"No comparable change from a saved report in {period_label}.")
        portfolio = f"Paper valuation: {paper.get('valuation_status', 'unknown')}; Live valuation: {live.get('valuation_status', 'unknown')}."
        states = "; ".join(f"{bot.get('trading_pair') or bot.get('symbol') or bot.get('bot_name') or 'Bot'}: "
                           f"{'active' if bot.get('is_active') else 'paused'}" for bot in bots)
        automation = f"{len(bots)} bot(s) read at report time. {states}. A prior decision is not a new order."
    elif locale == "de":
        retrospective = (f"Gegenüber {comparison['previous_date']}: " + "; ".join(
            change_text(row) for row in comparisons)
            if comparisons else f"Kein vergleichbarer Unterschied zu einem gespeicherten Bericht {period_label}.")
        portfolio = f"Paper-Bewertung: {paper.get('valuation_status', 'unbekannt')}; Live-Bewertung: {live.get('valuation_status', 'unbekannt')}."
        states = "; ".join(f"{bot.get('trading_pair') or bot.get('symbol') or bot.get('bot_name') or 'Bot'}: "
                           f"{'aktiv' if bot.get('is_active') else 'pausiert'}" for bot in bots)
        automation = f"{len(bots)} Bot(s) zum Berichtszeitpunkt gelesen. {states}. Eine ältere Entscheidung ist keine neue Order."
    else:
        retrospective = (f"Vergeleken met {comparison['previous_date']}: " + "; ".join(
            change_text(row) for row in comparisons)
            if comparisons else f"Er is geen vergelijkbare verandering uit een opgeslagen rapport van {period_label}.")
        if prior and not comparisons:
            score_labels = {"market_score": "markt", "macro_score": "macro",
                            "technical_score": "technisch"}
            measured = [f"{row['asset']}: " + ", ".join(
                [*([f"benchmark {row['benchmark_score']:g}"]
                    if isinstance(row.get('benchmark_score'), (int, float)) else []),
                 *(f"{score_labels.get(key, key)} {value:g}"
                   for key, value in row['scores'].items() if isinstance(value, (int, float)))])
                for row in prior if isinstance(row.get("benchmark_score"), (int, float))
                or any(isinstance(value, (int, float)) for value in row['scores'].values())]
            if measured:
                retrospective = (f"Het opgeslagen rapport van {comparison['previous_date']} bevatte "
                                 + "; ".join(measured) + ". Een vergelijkbare verandering van de "
                                 "volledige benchmark is niet vastgesteld.")
        portfolio = f"Paperwaardering: {paper.get('valuation_status', 'onbekend')}; Livewaardering: {live.get('valuation_status', 'onbekend')}."
        states = "; ".join(f"{bot.get('trading_pair') or bot.get('symbol') or bot.get('bot_name') or 'Bot'}: "
                           f"{'actief' if bot.get('is_active') else 'gepauzeerd'}"
                           for bot in bots)
        automation = (f"{len(bots)} bot(s) gelezen op het rapportmoment. {states}. "
                      "Een oudere beslissing is geen nieuwe order.")
    frequency_labels = {
        "nl": {"daily": "dagelijks", "weekly": "wekelijks", "monthly": "maandelijks"},
        "en": {"daily": "daily", "weekly": "weekly", "monthly": "monthly"},
        "de": {"daily": "täglich", "weekly": "wöchentlich", "monthly": "monatlich"},
    }
    timeframe_label = {"nl": "analysetijdframe", "en": "analysis timeframe", "de": "Analysezeitrahmen"}.get(locale, "analysis timeframe")
    plans = []
    for asset in facts["assets"]:
        for setup in asset.get("setups") or []:
            cadence = setup.get("dca_frequency") if setup.get("setup_type") == "dca" else None
            cadence_label = frequency_labels.get(locale, frequency_labels["en"]).get(cadence, cadence)
            if cadence == "weekly" and str(setup.get("dca_day") or "").isdigit():
                day = int(setup["dca_day"])
                if 1 <= day <= 7:
                    cadence_label += " " + REPORT_WEEKDAYS.get(locale, REPORT_WEEKDAYS["en"])[day - 1]
            elif cadence == "monthly" and str(setup.get("dca_month_day") or "").isdigit():
                day = int(setup["dca_month_day"])
                if 1 <= day <= 31:
                    cadence_label += f" {day}"
            plans.append(f"{asset['display_symbol']} · {setup.get('name') or 'Setup'}: "
                         f"{cadence_label or setup.get('setup_type') or 'unknown'}, "
                         f"{timeframe_label} {setup.get('timeframe') or 'unknown'}")
        for strategy in asset.get("strategies") or []:
            amount = strategy.get("base_amount")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                amount_label = f"{amount:g}"
                if locale == "nl":
                    plans.append(f"{asset['display_symbol']} · {strategy.get('name') or 'Strategie'}: "
                                 f"basisbedrag {amount_label} per uitvoering")
                elif locale == "de":
                    plans.append(f"{asset['display_symbol']} · {strategy.get('name') or 'Strategie'}: "
                                 f"Basisbetrag {amount_label} pro Ausführung")
                else:
                    plans.append(f"{asset['display_symbol']} · {strategy.get('name') or 'Strategy'}: "
                                 f"base amount {amount_label} per execution")
    analysis_parts = []
    component_names = {
        "nl": ("Markt", "Macro", "Technisch"),
        "en": ("Market", "Macro", "Technical"),
        "de": ("Markt", "Makro", "Technik"),
    }.get(locale, ("Market", "Macro", "Technical"))
    for asset in facts["assets"]:
        label = str(asset.get("display_symbol") or asset.get("symbol") or "").strip()
        if not label:
            continue
        scores = asset.get("scores") or {}
        components = [scores.get(key) for key in ("market_score", "macro_score", "technical_score")]
        def formatted(value: object) -> str:
            number = f"{float(value):g}"
            return number.replace(".", ",") if locale in ("nl", "de") else number
        available = [f"{name} {formatted(value)}/100" for name, value in zip(component_names, components)
                     if isinstance(value, (int, float)) and not isinstance(value, bool)]
        absent = [name for name, value in zip(component_names, components)
                  if not isinstance(value, (int, float)) or isinstance(value, bool)]
        benchmark = asset.get("benchmark_score")
        if isinstance(benchmark, (int, float)) and not isinstance(benchmark, bool):
            if locale == "de":
                detail = f"Benchmarkwert {formatted(benchmark)}/100; " + ", ".join(available) + "."
            elif locale == "nl":
                detail = f"Benchmarkscore {formatted(benchmark)}/100; " + ", ".join(available) + "."
            else:
                detail = f"Benchmark score {formatted(benchmark)}/100; " + ", ".join(available) + "."
        else:
            missing = ", ".join(absent)
            if locale == "de":
                detail = "Kein vollständiger aktueller Benchmark."
                if missing:
                    detail += f" {missing} ohne brauchbaren Score."
            elif locale == "nl":
                detail = "Geen complete actuele benchmark."
                if missing:
                    detail += f" {missing} zonder bruikbare score."
            else:
                detail = "No complete current benchmark."
                if missing:
                    detail += f" No usable score for {missing}."
            if available:
                detail += " " + ", ".join(available) + "."
        snapshot = asset.get("market_snapshot") or {}
        change = snapshot.get("change_24h") if snapshot.get("source_status") == "fresh" else None
        if isinstance(change, (int, float)) and not isinstance(change, bool):
            percent = _report_v2_prompt_market_snapshot(snapshot, locale)["change_24h_percent"]
            if locale == "de":
                detail += f" Gemessene Kursänderung über 24 Stunden: {percent}."
            elif locale == "nl":
                detail += f" Gemeten koerswijziging over 24 uur: {percent}."
            else:
                detail += f" Measured 24-hour price change: {percent}."
        analysis_parts.append(f"{label}: {detail}")
    return {
        "retrospective": retrospective,
        "portfolio": portfolio,
        "analysis": "\n\n".join(analysis_parts) if analysis_parts else " ".join(
            (legacy["market_analysis"], legacy["macro_context"], legacy["technical_analysis"])),
        "plan": "; ".join(plans) + "." if plans else legacy["setup_validation"],
        "automation": automation,
        "outlook_v2": legacy["outlook"],
    }


def _report_v2_contradicts_facts(section: str, value: str, facts: dict[str, Any],
                               context: dict[str, Any], comparison: dict[str, Any]) -> bool:
    """Reject only concrete contradictions with the frozen report facts."""
    if section == "retrospective":
        if re.search(r"\b(?:benchmark_availability|market_score|macro_score|technical_score)\b|"
                     r"\b(?:True|False)\s*→\s*(?:True|False)\b", value):
            return True
        prior_has_scores = any(
            isinstance(score, (int, float)) and not isinstance(score, bool)
            for row in comparison.get("previous_observations") or []
            for score in (row.get("benchmark_score"), *(row.get("scores") or {}).values())
        )
        if prior_has_scores and re.search(
            r"\b(?:geen|no|keine)\b.{0,65}\bbenchmarks?\b", value, re.I
        ):
            return True
        changed_components = any(
            row.get("fact") in ("market_score", "macro_score", "technical_score")
            for row in comparison.get("changes") or []
        )
        if changed_components and re.search(
            r"\b(?:deelscores?|component(?:scores?)?|partial scores?)\b.{0,90}"
            r"\b(?:gelijk gebleven|ongewijzigd|unchanged|unverändert)\b|"
            r"\b(?:gelijk gebleven|ongewijzigd|unchanged|unverändert)\b.{0,90}"
            r"\b(?:deelscores?|component(?:scores?)?|partial scores?)\b", value, re.I
        ):
            return True

    paused = [bot for bot in (context.get("report_bot_status") or {}).get("bots") or []
              if bot.get("is_active") is False] if section == "automation" else []
    if paused:
        for sentence in re.split(r"(?<=[.!?])\s+", value):
            if not re.search(r"\b(?:actief|active|aktiv)\b", sentence, re.I):
                continue
            if re.search(r"\b(?:niet|not|nicht)\s+(?:\w+\s+){0,2}(?:actief|active|aktiv)\b", sentence, re.I):
                continue
            if any(re.search(rf"\b{re.escape(str(bot.get('symbol') or ''))}\b", sentence, re.I)
                   for bot in paused if bot.get("symbol")):
                return True

    if section == "plan":
        frequencies = [setup.get("dca_frequency") for asset in facts["assets"]
                       for setup in asset.get("setups") or []
                       if setup.get("setup_type") == "dca"]
        if any(freq != "daily" for freq in frequencies) and re.search(
            r"\b(?:\d+|twee|drie|vier|two|three|four|zwei|drei|vier)\s+"
            r"(?:\w+\s+){0,3}(?:dagelijkse|daily|tägliche)\s+"
            r"(?:\w+\s+){0,2}(?:DCA[- ]?)?(?:plannen|plans|Pläne)\b", value, re.I
        ):
            return True
        if "daily" in frequencies and re.search(
            r"\b(?:wekelijkse?|wekelijks|weekly|wöchentliche?|wöchentlich)\b", value, re.I
        ):
            # The text may be about a different weekly plan. Use the exact
            # saved plan list instead of risking a wrong cadence assignment.
            return True
        has_amount = any(
            isinstance(strategy.get("base_amount"), (int, float))
            and not isinstance(strategy.get("base_amount"), bool)
            for asset in facts["assets"] for strategy in asset.get("strategies") or []
        )
        if has_amount and re.search(
            r"\b(?:geen|no|kein(?:e|en)?|niet|not)\b.{0,45}"
            r"\b(?:bedrag|amount|Betrag)\b", value, re.I
        ):
            return True
    return False


def generate_unified_daily_report_sections(user_id: int, period: str = "daily") -> dict[str, Any]:
    """Generate prose, preserving the report storage shape without old agent snapshots."""
    context = asyncio.run(_load_context(user_id) if period == "daily"
                          else _load_context(user_id, period))
    assets = context.get("assets") or []
    facts = _report_facts(context)
    locale = str(context.get("locale") or "nl").lower()
    comparison = (_report_v2_comparison(context, facts) if period == "daily"
                  else _report_v2_period_comparison(context, facts, period))
    report_v2_evidence = {
        "portfolio": context.get("report_portfolios") or {},
        "automation": context.get("report_bot_status") or {},
        "comparison": comparison,
    }
    factual_context = {**facts, "assets": [
        {**item, "market_snapshot": _report_v2_prompt_market_snapshot(item.get("market_snapshot") or {}, locale),
         "setups": [_report_v2_prompt_plan(row, locale) for row in item.get("setups") or []],
         "strategies": [_report_v2_prompt_plan(row, locale) for row in item.get("strategies") or []],
         "configured_indicators": {
            category: [_report_indicator_label(name, locale) for name in names]
            for category, names in (item.get("configured_indicators") or {}).items()
        } if item.get("configured_indicators") is not None else None}
        for item in facts["assets"][:30]
    ]}
    result = ask_gpt_json(
        system_role=(
            f"You are FINN, the user's trading coach. Write a complete, readable {period} report from only the "
            "provided owner-scoped facts. Missing or stale scores are unknown, never zero. "
            "A setup match is not an entry signal; a bot budget is not cash. "
            "The market_score is one component; benchmark_score is the weighted total. Never call the total a market score. "
            "Do not claim an order or trade occurred unless the supplied facts prove it. "
            "If market_session_at_report is outside_regular_hours, explain that the "
            "latest stock quote may be from the previous regular session; do not "
            "infer that a market was open from a timestamp alone. "
            "Use the localized indicator display names supplied in the context. "
            "Write every narrative value fully in the requested locale. JSON keys are data labels, "
            "not words to copy into the report. Translate financial source terms using the "
            "report_terminology glossary; preserve exact user-defined plan and bot names, "
            "asset symbols, trading pairs, and the Paper/Live mode labels. "
            "A setup timeframe is the analysis candle, never a DCA buying cadence. Use dca_frequency "
            "and the stored weekday or month day for purchase timing. A step decision_curve changes "
            "the planned amount by benchmark band; do not call such a strategy fixed. "
            "A DCA plan does not require trade entry, stop-loss or target prices; do not advise "
            "adding those merely because they are absent from the DCA strategy. "
            "Only verified_indicator_evidence contains measured indicator values. "
            "market_snapshot.change_24h_percent is already a percentage, not a fraction; "
            "copy its magnitude and sign without multiplying by 100. "
            "Each setup and match belongs only to the asset's exact display_symbol trading pair. "
            "Do not apply BTC/EUR plans or matches to BTC/USDT or vice versa. "
            "Write six Report 2.0 sections as useful narrative, naming relevant assets, "
            "measured scores, missing evidence and plan implications in the appropriate section. "
            "In analysis, use short paragraphs separated by blank lines, grouped by trading pair; "
            "keep each paragraph to two or three sentences. In plan and outlook, use the supplied "
            "purchase_weekday name rather than a numeric weekday code. "
            "Distinguish no configured indicator from a configured indicator without a usable score. "
            "Do not repeat the same asset inventory in every section. "
            "Never say all measured assets rise or fall unless every supplied 24-hour change has that direction. "
            "Return valid JSON with six Report 2.0 fields: retrospective, portfolio, analysis, plan, "
            "automation and outlook_v2. For a weekly, monthly or quarterly report, distinguish "
            "dated period history from the current snapshot. A trend requires at least two "
            "comparable dated observations. The retrospective may compare only the supplied "
            "prior observations; never claim a prior forecast was correct without evidence. "
            "Portfolio distinguishes Paper from Live and unknown balances from zero. "
            "Analysis explains the benchmark for each relevant pair, including absent components. "
            "Plan explains saved cadence, conditions and amount rule. Automation describes the "
            "bot state at the report instant, identifies old decisions as old, and never asserts "
            "that configured exit levels are being watched without execution evidence. "
            "The final outlook names concrete checks grounded in these facts, not a trade command."
        ),
        prompt=json.dumps({
            "task": f"Write the {period} report in the requested locale from this snapshot and dated period history only.",
            "period": period,
            "period_start": comparison.get("period_start"),
            "period_end": comparison.get("period_end"),
            "report_v2_sections": REPORT_V2_SECTIONS,
            "report_terminology": REPORT_V2_TERMINOLOGY.get(locale, {}),
            "context": factual_context,
            "report_v2_evidence": report_v2_evidence,
        }, ensure_ascii=False, default=str),
        max_tokens=5500,
        timeout_seconds=75,
        client_max_retries=0,
        model_override=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
        reasoning_effort="none",
    )
    if isinstance(result, dict) and result.get("error") == "ai_rate_limited":
        # Preserve the last stored report rather than replacing its personal
        # prose with an inventory when this regeneration hits the call limit.
        raise RuntimeError("daily_report_ai_rate_limited")
    fallbacks = _fallback_sections(context)
    for category, section in (("market", "market_analysis"), ("macro", "macro_context"),
                              ("technical", "technical_analysis")):
        fallbacks[section] = _category_fact_fallback(facts, category, locale) or fallbacks[section]
    strategy_names = [f"{item['display_symbol']}: {row['name']}"
                      for item in facts["assets"] for row in item["strategies"] if row.get("name")]
    if strategy_names:
        fallbacks["strategy_implication"] = f"{', '.join(strategy_names)}. {fallbacks['strategy_implication']}"
    fallbacks["bot_strategy"] = _bot_status_section(facts, locale)
    prose = {
        key: str(result.get(key) or "").strip() if isinstance(result, dict)
        and len(str(result.get(key) or "").strip()) >= 20 else fallbacks[key]
        for key in REPORT_SECTIONS
    }
    v2_fallbacks = _report_v2_factual_fallbacks(context, facts, comparison, locale)
    report_v2_prose = {}
    for key in REPORT_V2_SECTIONS:
        candidate = str(result.get(key) or "").strip() if isinstance(result, dict) else ""
        report_v2_prose[key] = candidate if len(candidate) >= 20 else v2_fallbacks[key]
    if _report_v2_analysis_claims_contradict(report_v2_prose["analysis"], facts):
        # Repair only the affected narrative. The measured facts remain the
        # authority; a failed repair falls back to a short factual section.
        repaired = ask_gpt_json(
            system_role=(
                "You are FINN. Rewrite only the analysis section in the requested locale. "
                "Use short paragraphs, one per exact trading pair. A 24-hour change "
                "is already in percent and must keep its measured sign and magnitude. "
                "A setup name, range or match may be attached only to its own pair. "
                "The market_score is a component, while benchmark_score is the weighted total; do not conflate them. "
                "Keep the useful explanation. Return JSON with one analysis string."
            ),
            prompt=json.dumps({
                "locale": locale,
                "assets": [{
                    "display_symbol": item["display_symbol"],
                    "market_snapshot": _report_v2_prompt_market_snapshot(item.get("market_snapshot") or {}, locale),
                    "scores": item["scores"],
                    "benchmark_score": item.get("benchmark_score"),
                    "setups": item.get("setups") or [],
                    "matches": item.get("matches") or [],
                } for item in facts["assets"]],
                "draft": report_v2_prose["analysis"],
            }, ensure_ascii=False, default=str),
            max_tokens=1400,
            retries=1,
            timeout_seconds=30,
            client_max_retries=0,
            model_override=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
            reasoning_effort="none",
        )
        candidate = str(repaired.get("analysis") or "").strip() if isinstance(repaired, dict) else ""
        report_v2_prose["analysis"] = (
            candidate if len(candidate) >= 20
            and not _report_v2_analysis_claims_contradict(candidate, facts)
            else v2_fallbacks["analysis"]
        )
    allowed_scores = {
        float(value)
        for item in facts["assets"]
        for value in (
            *item["scores"].values(),
            item.get("benchmark_score"),
            *(match.get("score") for match in item.get("matches") or []
              if item.get("score_status") == "available"),
        )
        if isinstance(value, (int, float))
    }
    # The retrospective may quote a prior verified score that no longer
    # appears in today's snapshot. Those values come from saved reports.
    prior_scores = {
        float(value)
        for row in comparison.get("previous_observations") or []
        for value in (row.get("benchmark_score"), *(row.get("scores") or {}).values())
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    if period != "daily":
        prior_scores.update(
            float(value)
            for row in comparison.get("period_observations") or []
            for value in (row.get("benchmark_score"), *(row.get("scores") or {}).values())
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
    for section, value in prose.items():
        # A reported numeric score must occur in the verified Score 2.0 snapshot.
        claims = [float(number.replace(",", ".")) for number in re.findall(r"(?<!\d)(\d+(?:[.,]\d+)?)/100\b", value)]
        has_unverified_score = any(claim not in allowed_scores for claim in claims)
        false_strategy_absence = bool(strategy_names) and bool(re.search(
            r"\b(?:geen|no|keine)\s+(?:opgeslagen\s+|saved\s+|gespeicherte\s+)?(?:strategie|strategy|Strategie)\b", value, re.I))
        if has_unverified_score or false_strategy_absence:
            prose[section] = fallbacks[section]
    for section, value in report_v2_prose.items():
        claims = [float(number.replace(",", ".")) for number in
                  re.findall(r"(?<!\d)(\d+(?:[.,]\d+)?)/100\b", value)]
        valid_scores = allowed_scores | (prior_scores if section == "retrospective" else set())
        false_strategy_absence = bool(strategy_names) and bool(re.search(
            r"\b(?:geen|no|keine)\s+(?:opgeslagen\s+|saved\s+|gespeicherte\s+)?(?:strategie|strategy|Strategie)\b", value, re.I))
        wrong_direction = section == "analysis" and _market_direction_contradicts_snapshot(value, facts)
        if (any(claim not in valid_scores for claim in claims) or false_strategy_absence
                or wrong_direction or _report_v2_contradicts_facts(section, value, facts, context, comparison)):
            report_v2_prose[section] = v2_fallbacks[section]
    protected_names = [
        str(row.get("name"))
        for item in facts["assets"]
        for group in ("setups", "strategies")
        for row in item.get(group) or []
        if row.get("name")
    ] + [
        str(bot.get("bot_name")) for bot in (context.get("report_bot_status") or {}).get("bots") or []
        if bot.get("bot_name")
    ]
    report_v2_prose = {
        section: _localize_report_v2_terms(value, locale, protected_names)
        for section, value in report_v2_prose.items()
    }
    if _market_direction_contradicts_snapshot(prose["market_analysis"], facts):
        # Give the report writer one chance to correct its own prose using the
        # same typed facts. A factual fallback is used only if that also fails.
        repaired = ask_gpt_json(
            system_role=(
                "You are FINN. Rewrite only the market_analysis section in the requested locale. "
                "Preserve a useful market explanation, but do not claim all measured assets "
                "moved in one direction when the supplied changes are mixed. "
                "Return JSON with one market_analysis string."
            ),
            prompt=json.dumps({"locale": locale, "market_snapshots": [
                {"asset": item["display_symbol"], "change_24h":
                 (item.get("market_snapshot") or {}).get("change_24h")}
                for item in facts["assets"]
            ], "draft": prose["market_analysis"]}, ensure_ascii=False, default=str),
            max_tokens=600,
            retries=1,
            timeout_seconds=30,
            client_max_retries=0,
            model_override=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
            reasoning_effort="none",
        )
        candidate = str(repaired.get("market_analysis") or "").strip() if isinstance(repaired, dict) else ""
        candidate_scores = [float(number.replace(",", ".")) for number in
                            re.findall(r"(?<!\d)(\d+(?:[.,]\d+)?)/100\b", candidate)]
        prose["market_analysis"] = (
            candidate if len(candidate) >= 20
            and not _market_direction_contradicts_snapshot(candidate, facts)
            and all(score in allowed_scores for score in candidate_scores)
            else fallbacks["market_analysis"]
        )
    # Reject a concrete contradiction, without replacing otherwise useful
    # coaching prose with canned score inventories.
    if facts["assets"] and all(item["score_status"] == "available" for item in facts["assets"]):
        if re.search(r"(?:zonder|geen|without|missing|ohne|fehl\w*)\s+(?:een\s+)?(?:complete\s+)?(?:actuele\s+)?benchmark", prose["setup_validation"], re.I):
            prose["setup_validation"] = fallbacks["setup_validation"]
        if re.search(r"\b(?:ontbre\w*|zonder|miss\w*|without|fehl\w*|ohne|unavailable)\b", prose["outlook"], re.I):
            prose["outlook"] = fallbacks["outlook"]
    # Keep Luna's section prose. Typed score and plan facts are projected into
    # separate evidence fields; replacing prose with a flat inventory made the
    # eight-chapter report unreadable for multiple assets.
    all_strategies = [row for item in facts["assets"] for row in item.get("strategies") or []]
    # ReportService deliberately hides historical AI setup scores unless each
    # stored match declares the measured Score 2.0 semantics. Preserve that
    # provenance when projecting the shared match into the report row.
    matches = [
        {**match, "score": match.get("score") if item["score_status"] == "available" else None,
         "score_semantics": "benchmark_setup_match_v1"}
        for item in facts["assets"] for match in item["matches"]
    ]
    matches.sort(key=lambda item: (
        bool(item.get("is_active")),
        item["score"] if isinstance(item.get("score"), (int, float)) else -1,
    ), reverse=True)
    best = next((match for match in matches
                 if match.get("is_active") and match.get("status") == "matches"
                 and isinstance(match.get("score"), (int, float))), None)
    best_setup = ({
        "id": best.get("setup_id"), "name": best.get("name"), "symbol": best.get("symbol"),
        "pair": best.get("pair"),
        "timeframe": best.get("timeframe"), "score": best.get("score"), "status": best.get("status"),
        "score_semantics": best.get("score_semantics"),
    } if best else None)
    # A report for one asset can fill its scalar score cards. With multiple
    # assets there is no single category score; the prose and watchlist retain
    # the per-asset values instead of silently selecting the first asset.
    single_scores = facts["assets"][0]["scores"] if len(facts["assets"]) == 1 else {}
    single_market_snapshot = facts["assets"][0]["market_snapshot"] if len(facts["assets"]) == 1 else {}
    if single_market_snapshot.get("source_status") != "fresh":
        single_market_snapshot = {}
    return {
        **prose,
        "watchlist": [{"symbol": item["symbol"], "pair": item.get("pair"), "benchmark": {
            "source_status": item["score_status"],
            "benchmark_score": item["benchmark_score"],
            "reported_scores": item["scores"],
            "matches": item["matches"],
        }} for item in facts["assets"]],
        "best_setup": best_setup,
        "top_setups": matches[:5],
        "active_strategy": ({
            "strategy_name": all_strategies[0].get("name"),
            "setup_name": all_strategies[0].get("setup_name"),
            "symbol": all_strategies[0].get("symbol"),
            "pair": all_strategies[0].get("pair"),
            "timeframe": all_strategies[0].get("timeframe"),
            "setup_type": all_strategies[0].get("setup_type"),
            "dca_frequency": all_strategies[0].get("dca_frequency"),
            "dca_day": all_strategies[0].get("dca_day"),
            "dca_month_day": all_strategies[0].get("dca_month_day"),
            "execution_mode": all_strategies[0].get("execution_mode"),
            "base_amount": all_strategies[0].get("base_amount"),
            "decision_curve": all_strategies[0].get("decision_curve"),
            "entry": all_strategies[0].get("entry"),
            "targets": all_strategies[0].get("targets"),
            "stop_loss": all_strategies[0].get("stop_loss"),
            "confidence_score": None,
        } if len(all_strategies) == 1 else {
            "strategies": [{"strategy_name": row.get("name"),
                            "setup_name": row.get("setup_name"),
                            "symbol": row.get("symbol"),
                            **({"pair": row["pair"]} if row.get("pair") else {}),
                            "timeframe": row.get("timeframe")}
                           for row in all_strategies]
        } if all_strategies else None),
        "bot_snapshot": None,
        "market_indicator_highlights": _configured_highlights(facts, "market", locale),
        "macro_indicator_highlights": _configured_highlights(facts, "macro", locale),
        "technical_indicator_highlights": _configured_highlights(facts, "technical", locale),
        "price": single_market_snapshot.get("price"),
        "change_24h": single_market_snapshot.get("change_24h"),
        "volume": single_market_snapshot.get("volume"),
        "macro_score": single_scores.get("macro_score"),
        "technical_score": single_scores.get("technical_score"),
        "market_score": single_scores.get("market_score"),
        "setup_score": best_setup.get("score") if best_setup else None,
        "score_source_snapshot": {
            "observed_at": context.get("observed_at"),
            "content_locale": locale,
            "report_v2": {
                "version": 2,
                "period": period,
                "period_start": comparison.get("period_start"),
                "period_end": comparison.get("period_end"),
                "sections": report_v2_prose,
                "portfolio": jsonable_encoder(_report_source_times(context.get("report_portfolios") or {})),
                "automation": jsonable_encoder(_report_source_times(context.get("report_bot_status") or {})),
                "comparison": comparison,
                "plans": [{"market_id": item.get("market_id"),
                           "pair": item.get("pair"), "symbol": item.get("symbol"),
                           "setups": item["setups"], "strategies": item["strategies"],
                           "matches": item["matches"]} for item in facts["assets"]],
            },
            "assets": [{
                "symbol": item["symbol"],
                "pair": item.get("pair"),
                "market_id": item.get("market_id"),
                "market_session_at_report": item["market_session_at_report"],
                "score_report_date": item.get("score_report_date"),
                "score_status": item["score_status"],
                "component_source_status": item["component_source_status"],
                "component_source_observed_at": item["component_source_observed_at"],
                "verified_indicator_evidence": item["verified_indicator_evidence"],
                "configured_indicators": item["configured_indicators"],
                "reported_scores": item["scores"],
                "benchmark_score": item["benchmark_score"],
                "market_snapshot": item["market_snapshot"],
            } for item in facts["assets"]],
        },
        "meta": {"source": "finn_shared_context.v1", "report_facts_version": 2,
                 "observed_at": context.get("observed_at")},
    }


def _period_start(period: str, today: date) -> date:
    if period == "weekly":
        return today - timedelta(days=today.weekday())
    if period == "monthly":
        return today.replace(day=1)
    if period == "quarterly":
        return today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)
    raise ValueError("unsupported_report_period")


def generate_unified_period_report_sections(user_id: int, period: str) -> dict[str, Any]:
    """Use Report 2.0's frozen owner facts and six-section FINN writer for every period."""
    if period not in {"weekly", "monthly", "quarterly"}:
        raise ValueError("unsupported_report_period")
    report = generate_unified_daily_report_sections(user_id, period=period)
    snapshot = report["score_source_snapshot"]
    v2_sections = snapshot["report_v2"]["sections"]
    return {
        # Retain the legacy columns for existing readers. The web and PDF use
        # the frozen Report 2.0 snapshot in meta_json instead.
        "executive_summary": report["executive_summary"],
        "market_overview": report["market_analysis"],
        "macro_trends": report["macro_context"],
        "technical_structure": report["technical_analysis"],
        "setup_performance": report["setup_validation"],
        "bot_performance": report["bot_strategy"],
        "strategic_lessons": report["strategy_implication"],
        "outlook": v2_sections["outlook_v2"],
        "macro_score": None, "technical_score": None, "setup_score": None,
        "score_source_snapshot": snapshot,
        "meta": {"source": "finn_shared_context.v2", "period": period,
                 "period_start": snapshot["report_v2"]["period_start"],
                 "period_end": snapshot["report_v2"]["period_end"]},
    }


def generate_weekly_report_sections(user_id: int) -> dict[str, Any]:
    return generate_unified_period_report_sections(user_id, "weekly")


def generate_monthly_report_sections(user_id: int) -> dict[str, Any]:
    return generate_unified_period_report_sections(user_id, "monthly")


def generate_quarterly_report_sections(user_id: int) -> dict[str, Any]:
    return generate_unified_period_report_sections(user_id, "quarterly")
