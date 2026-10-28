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


def _regular_session_at(observed_at: Any, asset_class: Any, market_timezone: Any) -> str:
    """Only assert outside hours when the catalog and clock prove it.

    Being inside scheduled hours does not prove the exchange was open: holidays,
    halts and provider delays still need exchange evidence.
    """
    if str(asset_class or "").lower() not in {"stock", "etf"}:
        return "not_applicable"
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
            return context
    finally:
        await report_engine.dispose()


def _fallback_sections(context: dict[str, Any]) -> dict[str, str]:
    assets = context.get("assets") or []
    symbols = ", ".join(item["symbol"] for item in assets)
    missing = [item["symbol"] for item in assets if item["benchmark"].get("source_status") != "available"]
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
            "asset_class": item.get("asset_class"),
            "market_timezone": item.get("market_timezone"),
            "market_session_at_report": _regular_session_at(
                context.get("observed_at"), item.get("asset_class"),
                item.get("market_timezone"),
            ),
            "score_status": benchmark.get("source_status"),
            "score_report_date": benchmark.get("as_of"),
            "component_source_status": source_status,
            "component_source_observed_at": benchmark.get("component_source_observed_at") or {},
            "scores": scores,
            "benchmark_score": benchmark.get("benchmark_score"),
            "market_snapshot": item.get("market_snapshot") or {},
            "configured_indicators": configured,
            "indicator_lookup_status": item.get("indicator_lookup_status"),
            "setups": [{"id": row.get("id"), "name": row.get("name"),
                        "timeframe": row.get("timeframe"), "setup_type": row.get("setup_type")}
                       for row in item.get("setups") or []],
            "strategies": [{"id": row.get("id"), "setup_id": row.get("setup_id"),
                            "name": row.get("name"),
                            "setup_name": (setups_by_id.get(row.get("setup_id")) or {}).get("name")
                                          or row.get("setup_name"),
                            "symbol": item.get("symbol"),
                            "timeframe": row.get("timeframe") or
                                         (setups_by_id.get(row.get("setup_id")) or {}).get("timeframe"),
                            "execution_mode": row.get("execution_mode"),
                            "base_amount": row.get("base_amount"),
                            "entry": row.get("entry"), "stop_loss": row.get("stop_loss"),
                            "targets": row.get("targets")}
                           for row in item.get("strategies") or []],
            "bots": [{"id": row.get("id"), "name": row.get("name"),
                      "is_live": row.get("is_live"), "is_active": row.get("is_active")}
                     for row in item.get("bots") or []],
            "matches": [{"setup_id": row.get("setup_id"), "name": row.get("name"),
                         "symbol": row.get("symbol"), "timeframe": row.get("timeframe"),
                         "status": row.get("status"), "score": row.get("score"),
                         "is_active": row.get("is_active")}
                        for row in benchmark.get("matches") or []],
        })
    return {"locale": context.get("locale"), "profile": context.get("profile"),
            "trader_context": context.get("trader_context"), "assets": assets}


def _configured_highlights(facts: dict[str, Any], category: str, locale: str) -> list[dict[str, Any]]:
    return [{"indicator": _report_indicator_label(name, locale), "symbol": item["symbol"]}
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
        parts.append(f"{name} {status.get(locale, status['en'])}.")
    budget_note = {
        "nl": "Beschikbaar kassaldo is in dit rapport niet vastgesteld; een botbudget is alleen een limiet.",
        "en": "Available cash has not been established in this report; a bot budget is only a limit.",
        "de": "Verfügbares Guthaben wurde in diesem Bericht nicht festgestellt; ein Bot-Budget ist nur ein Limit.",
    }
    return " ".join([*parts, budget_note.get(locale, budget_note["en"])])


def generate_unified_daily_report_sections(user_id: int) -> dict[str, Any]:
    """Generate prose, preserving the report storage shape without old agent snapshots."""
    context = asyncio.run(_load_context(user_id))
    assets = context.get("assets") or []
    facts = _report_facts(context)
    locale = str(context.get("locale") or "nl").lower()
    factual_context = {**facts, "assets": [
        {**item, "configured_indicators": {
            category: [_report_indicator_label(name, locale) for name in names]
            for category, names in (item.get("configured_indicators") or {}).items()
        } if item.get("configured_indicators") is not None else None}
        for item in facts["assets"][:30]
    ]}
    result = ask_gpt_json(
        system_role=(
            "You are FINN, the user's trading coach. Write a careful daily report from only the "
            "provided owner-scoped facts. Missing or stale scores are unknown, never zero. "
            "A setup match is not an entry signal; a bot budget is not cash. "
            "Do not claim an order or trade occurred unless the supplied facts prove it. "
            "If market_session_at_report is outside_regular_hours, explain that the "
            "latest stock quote may be from the previous regular session; do not "
            "infer that a market was open from a timestamp alone. "
            "Use the localized indicator display names supplied in the context. "
            "Return valid JSON with the eight requested string fields."
        ),
        prompt=json.dumps({
            "task": "Write the daily report in the requested locale from this snapshot only.",
            "sections": REPORT_SECTIONS,
            "context": factual_context,
        }, ensure_ascii=False, default=str),
        max_tokens=2400,
        model_override=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
        reasoning_effort="none",
    )
    fallbacks = _fallback_sections(context)
    prose = {
        key: str(result.get(key) or "").strip() if isinstance(result, dict)
        and len(str(result.get(key) or "").strip()) >= 20 else fallbacks[key]
        for key in REPORT_SECTIONS
    }
    # Model prose is useful for a coaching outlook. Factual report sections are
    # assembled from typed source status and owner-scoped configuration. A
    # prompt alone cannot prevent a persisted report from calling a stale score
    # current or claiming a saved strategy does not exist.
    labels = {
        "nl": {"missing": "Geen bruikbare actuele score", "configured": "Ingesteld",
               "not_configured": "Geen indicatoren ingesteld", "unknown": "Indicatorconfiguratie niet beschikbaar",
               "strategies": "Opgeslagen strategieën", "no_strategies": "Geen opgeslagen strategie"},
        "en": {"missing": "No usable current score", "configured": "Configured",
               "not_configured": "No indicators configured", "unknown": "Indicator configuration unavailable",
               "strategies": "Saved strategies", "no_strategies": "No saved strategy"},
        "de": {"missing": "Kein brauchbarer aktueller Wert", "configured": "Eingerichtet",
               "not_configured": "Keine Indikatoren eingerichtet", "unknown": "Indikatorkonfiguration nicht verfügbar",
               "strategies": "Gespeicherte Strategien", "no_strategies": "Keine gespeicherte Strategie"},
    }.get(locale, None)
    labels = labels or {"missing": "No usable current score", "configured": "Configured",
                         "not_configured": "No indicators configured", "unknown": "Indicator configuration unavailable",
                         "strategies": "Saved strategies", "no_strategies": "No saved strategy"}
    def score_section(category: str) -> str:
        parts = []
        for item in facts["assets"]:
            names = (item.get("configured_indicators") or {}).get(category)
            configuration = (f"{labels['configured']}: {', '.join(_report_indicator_label(name, locale) for name in names)}" if names
                             else labels["not_configured"] if names is not None
                             else labels["unknown"])
            value = item["scores"].get(f"{category}_score")
            score = f"{value:g}/100" if isinstance(value, (int, float)) else labels["missing"]
            parts.append(f"{item['symbol']}: {configuration}; {score}.")
        return " ".join(parts) if parts else fallbacks[{
            "market": "market_analysis", "macro": "macro_context",
            "technical": "technical_analysis"}[category]]
    prose["market_analysis"] = score_section("market")
    prose["macro_context"] = score_section("macro")
    prose["technical_analysis"] = score_section("technical")
    strategy_names = [f"{item['symbol']}: {row['name']}"
                      for item in facts["assets"] for row in item["strategies"] if row.get("name")]
    prose["strategy_implication"] = (
        f"{labels['strategies']}: {', '.join(strategy_names)}. "
        + fallbacks["strategy_implication"] if strategy_names else labels["no_strategies"] + "."
    )
    # Match status is a computed fact shared with Analyse and FINN. Do not let
    # generated prose or a fallback imply missing data when the benchmark is
    # complete and a saved boundary is simply not met.
    prose["setup_validation"] = fallbacks["setup_validation"]
    # Bot activity must come from stored state, not model guesses about why a
    # score match did or did not become an order.
    prose["bot_strategy"] = _bot_status_section(facts, locale)
    if any(item["score_status"] != "available" for item in facts["assets"]):
        prose["outlook"] = fallbacks["outlook"]
    elif facts["assets"] and all(
        all(value is not None for value in item["scores"].values())
        for item in facts["assets"]
    ) and re.search(r"\b(?:ontbre\w*|zonder|miss\w*|without|fehl\w*|ohne|unavailable)\b", prose["outlook"], re.I):
        # A complete scored snapshot must not end with an unsupported claim
        # that its measurements are missing. Keep the model for interpretation
        # while deriving data availability from typed Score 2.0 facts.
        prose["outlook"] = fallbacks["outlook"]
    # The summary must not turn unavailable scores or saved plans into model
    # assertions. It uses the same owner-scoped names as the fact cards.
    prose["executive_summary"] = fallbacks["executive_summary"]
    all_strategies = [row for item in facts["assets"] for row in item.get("strategies") or []]
    # ReportService deliberately hides historical AI setup scores unless each
    # stored match declares the measured Score 2.0 semantics. Preserve that
    # provenance when projecting the shared match into the report row.
    matches = [
        {**match, "score_semantics": "benchmark_setup_match_v1"}
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
        "watchlist": [{"symbol": item["symbol"], "benchmark": {
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
            "timeframe": all_strategies[0].get("timeframe"),
            "entry": all_strategies[0].get("entry"),
            "targets": all_strategies[0].get("targets"),
            "stop_loss": all_strategies[0].get("stop_loss"),
            "confidence_score": None,
        } if len(all_strategies) == 1 else {
            "strategies": [{"strategy_name": row.get("name"),
                            "setup_name": row.get("setup_name"),
                            "symbol": row.get("symbol"),
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
            "assets": [{
                "symbol": item["symbol"],
                "market_session_at_report": item["market_session_at_report"],
                "score_report_date": item.get("score_report_date"),
                "score_status": item["score_status"],
                "component_source_status": item["component_source_status"],
                "component_source_observed_at": item["component_source_observed_at"],
                "reported_scores": item["scores"],
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
