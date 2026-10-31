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


PERIOD_SECTIONS = (
    "executive_summary", "market_overview", "macro_trends", "technical_structure",
    "setup_performance", "bot_performance", "strategic_lessons", "outlook",
)


async def _load_context(user_id: int) -> dict[str, Any]:
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
                rows = (await session.execute(text("""
                    SELECT report_date, score_source_snapshot
                    FROM daily_reports
                    WHERE user_id = :user_id AND report_date < CURRENT_DATE
                      AND report_date >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY report_date DESC LIMIT 7
                """), {"user_id": user_id})).mappings().all()
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
                        "dca_day": row.get("dca_day"),
                        "dca_month_day": row.get("dca_month_day"),
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
                            "dca_day": (setups_by_id.get(row.get("setup_id")) or {}).get("dca_day"),
                            "dca_month_day": (setups_by_id.get(row.get("setup_id")) or {}).get("dca_month_day"),
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
        return {"status": "no_prior_report", "previous_date": None, "changes": []}
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
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                changes.append({"asset": asset["display_symbol"], "fact": "benchmark_score",
                                "before": before, "after": after})
            elif (before is None) != (after is None):
                changes.append({"asset": asset["display_symbol"], "fact": "benchmark_availability",
                                "before": before is not None, "after": after is not None})
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
            "previous_outlook": previous_outlook(latest),
            "week_earliest_date": earliest.get("report_date") if earliest else None,
            "week_changes": changes_since(earliest) if earliest else [],
            "week_earliest_outlook": previous_outlook(earliest)}


def _report_v2_factual_fallbacks(context: dict[str, Any], facts: dict[str, Any],
                                  comparison: dict[str, Any], locale: str) -> dict[str, str]:
    """Short factual copy for provider failure, with no inferred trade advice."""
    legacy = _fallback_sections(context)
    snapshots = context.get("report_portfolios") or {}
    bots = (context.get("report_bot_status") or {}).get("bots") or []
    paper = snapshots.get("paper") or {}
    live = snapshots.get("live") or {}
    comparisons = comparison.get("changes") or []
    if locale == "en":
        retrospective = (f"Compared with {comparison['previous_date']}: " + "; ".join(
            f"{row['asset']} {row['fact']}: {row['before']} → {row['after']}" for row in comparisons)
            if comparisons else "No comparable change from a saved report in the past seven days.")
        portfolio = f"Paper valuation: {paper.get('valuation_status', 'unknown')}; Live valuation: {live.get('valuation_status', 'unknown')}."
        automation = f"{len(bots)} bot(s) were read at the report time. A prior decision is not a new order."
    elif locale == "de":
        retrospective = (f"Gegenüber {comparison['previous_date']}: " + "; ".join(
            f"{row['asset']} {row['fact']}: {row['before']} → {row['after']}" for row in comparisons)
            if comparisons else "Kein vergleichbarer Unterschied zu einem gespeicherten Bericht der letzten sieben Tage.")
        portfolio = f"Paper-Bewertung: {paper.get('valuation_status', 'unbekannt')}; Live-Bewertung: {live.get('valuation_status', 'unbekannt')}."
        automation = f"{len(bots)} Bot(s) zum Berichtszeitpunkt gelesen. Eine ältere Entscheidung ist keine neue Order."
    else:
        retrospective = (f"Vergeleken met {comparison['previous_date']}: " + "; ".join(
            f"{row['asset']} {row['fact']}: {row['before']} → {row['after']}" for row in comparisons)
            if comparisons else "Er is geen vergelijkbare verandering uit een opgeslagen rapport van de afgelopen zeven dagen.")
        portfolio = f"Paperwaardering: {paper.get('valuation_status', 'onbekend')}; Livewaardering: {live.get('valuation_status', 'onbekend')}."
        automation = f"{len(bots)} bot(s) gelezen op het rapportmoment. Een oudere beslissing is geen nieuwe order."
    return {
        "retrospective": retrospective,
        "portfolio": portfolio,
        "analysis": " ".join((legacy["market_analysis"], legacy["macro_context"], legacy["technical_analysis"])),
        "plan": " ".join((legacy["setup_validation"], legacy["strategy_implication"])),
        "automation": automation,
        "outlook_v2": legacy["outlook"],
    }


def generate_unified_daily_report_sections(user_id: int) -> dict[str, Any]:
    """Generate prose, preserving the report storage shape without old agent snapshots."""
    context = asyncio.run(_load_context(user_id))
    assets = context.get("assets") or []
    facts = _report_facts(context)
    locale = str(context.get("locale") or "nl").lower()
    comparison = _report_v2_comparison(context, facts)
    report_v2_evidence = {
        "portfolio": context.get("report_portfolios") or {},
        "automation": context.get("report_bot_status") or {},
        "comparison": comparison,
    }
    factual_context = {**facts, "assets": [
        {**item, "configured_indicators": {
            category: [_report_indicator_label(name, locale) for name in names]
            for category, names in (item.get("configured_indicators") or {}).items()
        } if item.get("configured_indicators") is not None else None}
        for item in facts["assets"][:30]
    ]}
    result = ask_gpt_json(
        system_role=(
            "You are FINN, the user's trading coach. Write a complete, readable daily report from only the "
            "provided owner-scoped facts. Missing or stale scores are unknown, never zero. "
            "A setup match is not an entry signal; a bot budget is not cash. "
            "Do not claim an order or trade occurred unless the supplied facts prove it. "
            "If market_session_at_report is outside_regular_hours, explain that the "
            "latest stock quote may be from the previous regular session; do not "
            "infer that a market was open from a timestamp alone. "
            "Use the localized indicator display names supplied in the context. "
            "A setup timeframe is the analysis candle, never a DCA buying cadence. Use dca_frequency "
            "and the stored weekday or month day for purchase timing. A step decision_curve changes "
            "the planned amount by benchmark band; do not call such a strategy fixed. "
            "A DCA plan does not require trade entry, stop-loss or target prices; do not advise "
            "adding those merely because they are absent from the DCA strategy. "
            "Only verified_indicator_evidence contains measured indicator values. "
            "Write six Report 2.0 sections as useful narrative, naming relevant assets, "
            "measured scores, missing evidence and plan implications in the appropriate section. "
            "Distinguish no configured indicator from a configured indicator without a usable score. "
            "Do not repeat the same asset inventory in every section. "
            "Never say all measured assets rise or fall unless every supplied 24-hour change has that direction. "
            "Return valid JSON with six Report 2.0 fields: retrospective, portfolio, analysis, plan, "
            "automation and outlook_v2. The retrospective may compare only the supplied "
            "prior observations; never claim a prior forecast was correct without evidence. "
            "Portfolio distinguishes Paper from Live and unknown balances from zero. "
            "Analysis explains the benchmark for each relevant pair, including absent components. "
            "Plan explains saved cadence, conditions and amount rule. Automation describes the "
            "bot state at the report instant, identifies old decisions as old, and never asserts "
            "that configured exit levels are being watched without execution evidence. "
            "The final outlook names concrete checks grounded in these facts, not a trade command."
        ),
        prompt=json.dumps({
            "task": "Write the daily report in the requested locale from this snapshot only.",
            "report_v2_sections": REPORT_V2_SECTIONS,
            "context": factual_context,
            "report_v2_evidence": report_v2_evidence,
        }, ensure_ascii=False, default=str),
        max_tokens=5500,
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
        for change in (*comparison.get("changes", []), *comparison.get("week_changes", []))
        if change.get("fact") == "benchmark_score"
        for value in (change.get("before"), change.get("after"))
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
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
        if any(claim not in valid_scores for claim in claims) or false_strategy_absence or wrong_direction:
            report_v2_prose[section] = v2_fallbacks[section]
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


async def _load_period_context(user_id: int, period: str) -> dict[str, Any]:
    today = date.today()
    start = _period_start(period, today)
    report_engine = create_async_engine(ASYNC_DATABASE_URL, poolclass=NullPool)
    try:
        sessions = async_sessionmaker(report_engine, expire_on_commit=False)
        async with sessions() as session:
            shared = await FinnSharedContextService(session).for_user(user_id)
            params = {"user_id": user_id, "start": start, "end": today}
            scores = (await session.execute(text("""
            SELECT symbol, report_date, market_score, macro_score, technical_score,
                   calculated_at, indicator_evidence
            FROM daily_scores
            WHERE user_id = :user_id AND report_date BETWEEN :start AND :end
              AND market_id IS NULL
            ORDER BY report_date ASC, symbol ASC LIMIT 150
            """), params)).mappings().all()
            decisions = (await session.execute(text("""
            SELECT d.decision_date, d.symbol, d.action, d.status, d.amount_eur,
                   b.name AS bot_name
            FROM bot_decisions d
            JOIN bot_configs b ON b.id = d.bot_id AND b.user_id = d.user_id
            WHERE d.user_id = :user_id AND d.decision_date BETWEEN :start AND :end
            ORDER BY d.decision_date ASC, d.id ASC LIMIT 150
            """), params)).mappings().all()
    finally:
        await report_engine.dispose()
    return jsonable_encoder({
        "period": period, "period_start": start, "period_end": today,
        "shared": shared,
        "dated_scores": [dict(row) for row in scores],
        "bot_decisions": [dict(row) for row in decisions],
    })


def generate_unified_period_report_sections(user_id: int, period: str) -> dict[str, Any]:
    """One report writer over dated facts; never infer trades from planned bot actions."""
    context = asyncio.run(_load_period_context(user_id, period))
    shared = context["shared"]
    locale = str(shared.get("locale") or "nl")
    report_context = {**context, "shared": _report_facts(shared)}
    result = ask_gpt_json(
        system_role=(
            "You are FINN, the user's trading coach. Write a factual period report "
            "in the supplied locale. Use only this owner's current plan and dated history. "
            "Missing or stale scores are unknown, not zero. A planned bot decision is "
            "not an executed trade; a bot budget is not cash. Describe a trend only "
            "when at least two dated comparable measurements support it. Return JSON "
            "with exactly the eight requested string fields."
        ),
        prompt=json.dumps({"task": f"Write the {period} FINN report", "locale": locale,
                           "sections": PERIOD_SECTIONS, "context": report_context}, ensure_ascii=False),
        max_tokens=2600,
        model_override=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
        reasoning_effort="none",
    )
    daily_fallback = _fallback_sections(shared)
    fallback = {
        "executive_summary": daily_fallback["executive_summary"],
        "market_overview": daily_fallback["market_analysis"],
        "macro_trends": daily_fallback["macro_context"],
        "technical_structure": daily_fallback["technical_analysis"],
        "setup_performance": daily_fallback["setup_validation"],
        "bot_performance": daily_fallback["bot_strategy"],
        "strategic_lessons": daily_fallback["strategy_implication"],
        "outlook": daily_fallback["outlook"],
    }
    sections = {
        key: str(result.get(key) or "").strip() if isinstance(result, dict)
        and len(str(result.get(key) or "").strip()) >= 20 else fallback[key]
        for key in PERIOD_SECTIONS
    }
    return {
        **sections,
        "macro_score": None, "technical_score": None, "setup_score": None,
        "meta": {"source": "finn_shared_context.v1", "period": period,
                 "period_start": context["period_start"], "period_end": context["period_end"]},
    }


def generate_weekly_report_sections(user_id: int) -> dict[str, Any]:
    return generate_unified_period_report_sections(user_id, "weekly")


def generate_monthly_report_sections(user_id: int) -> dict[str, Any]:
    return generate_unified_period_report_sections(user_id, "monthly")


def generate_quarterly_report_sections(user_id: int) -> dict[str, Any]:
    return generate_unified_period_report_sections(user_id, "quarterly")
