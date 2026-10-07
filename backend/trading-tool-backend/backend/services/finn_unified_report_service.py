"""Daily report prose over the same owner-scoped facts FINN uses elsewhere."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from backend.infrastructure.database import async_session_factory, engine, sync_engine
from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.utils.openai_client import ask_gpt_json


REPORT_SECTIONS = (
    "executive_summary", "market_analysis", "macro_context", "technical_analysis",
    "setup_validation", "strategy_implication", "bot_strategy", "outlook",
)
PERIOD_SECTIONS = (
    "executive_summary", "market_overview", "macro_trends", "technical_structure",
    "setup_performance", "bot_performance", "strategic_lessons", "outlook",
)


async def _load_context(user_id: int) -> dict[str, Any]:
    # Background workers and report previews can enter on different event
    # loops. Do not reuse a pooled asyncpg connection from a previous loop.
    await engine.dispose()
    sync_engine.dispose()
    async with async_session_factory() as session:
        return await FinnSharedContextService(session).for_user(user_id)


def _fallback_sections(context: dict[str, Any]) -> dict[str, str]:
    assets = context.get("assets") or []
    symbols = ", ".join(item["symbol"] for item in assets)
    missing = [item["symbol"] for item in assets if item["benchmark"].get("source_status") != "available"]
    matches = [match for item in assets for match in item["benchmark"].get("matches") or []]
    active = [match for match in matches if match.get("is_active")]
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
            "setup_validation": f"There are {len(active)} confirmed current setup matches." if active else "There is no confirmed setup match without a complete current benchmark.",
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
            "setup_validation": f"Es gibt {len(active)} bestätigte aktuelle Setup-Treffer." if active else "Ohne vollständigen aktuellen Benchmark gibt es keinen bestätigten Setup-Treffer.",
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
        "setup_validation": f"Er zijn {len(active)} bevestigde actuele setupmatches." if active
        else "Er is zonder complete actuele benchmark geen bevestigde setupmatch.",
        "strategy_implication": "Vergelijk een opgeslagen strategie pas met de bijbehorende setup en actuele brongegevens; een entryprijs is geen actueel instapsignaal.",
        "bot_strategy": f"Er zijn {len(bots)} gekoppelde bots; hun budget is geen bewijs van beschikbaar kassaldo of een uitgevoerde aankoop.",
        "outlook": "Controleer bij de volgende gegevensverversing welke bronmetingen en setupvoorwaarden daadwerkelijk beschikbaar zijn.",
    }


def generate_unified_daily_report_sections(user_id: int) -> dict[str, Any]:
    """Generate prose, preserving the report storage shape without old agent snapshots."""
    context = asyncio.run(_load_context(user_id))
    assets = context.get("assets") or []
    factual_context = {
        "locale": context.get("locale"),
        "profile": context.get("profile"),
        "trader_context": context.get("trader_context"),
        "assets": assets[:30],
    }
    result = ask_gpt_json(
        system_role=(
            "You are FINN, the user's trading coach. Write a careful daily report from only the "
            "provided owner-scoped facts. Missing or stale scores are unknown, never zero. "
            "A setup match is not an entry signal; a bot budget is not cash. "
            "Do not claim an order or trade occurred unless the supplied facts prove it. "
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
    matches = [match for item in assets for match in item["benchmark"].get("matches") or []]
    matches.sort(key=lambda item: (bool(item.get("is_active")), item.get("score") or -1), reverse=True)
    best = next((match for match in matches if match.get("is_active")), None)
    best_setup = ({
        "id": best.get("setup_id"), "name": best.get("name"), "symbol": best.get("symbol"),
        "timeframe": best.get("timeframe"), "score": best.get("score"), "status": best.get("status"),
    } if best else None)
    # The report table's scalar score columns cannot represent a multi-asset
    # benchmark. Leave them null; the per-asset facts live in the report body.
    return {
        **prose,
        "watchlist": [{"symbol": item["symbol"], "benchmark": item["benchmark"]} for item in assets],
        "best_setup": best_setup,
        "top_setups": matches[:5],
        "active_strategy": None,
        "bot_snapshot": None,
        "market_indicator_highlights": [],
        "macro_indicator_highlights": [],
        "technical_indicator_highlights": [],
        "price": None, "change_24h": None, "volume": None,
        "macro_score": None, "technical_score": None, "market_score": None,
        "setup_score": best_setup.get("score") if best_setup else None,
        "meta": {"source": "finn_shared_context.v1", "observed_at": context.get("observed_at")},
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
    await engine.dispose()
    sync_engine.dispose()
    today = date.today()
    start = _period_start(period, today)
    async with async_session_factory() as session:
        shared = await FinnSharedContextService(session).for_user(user_id)
        params = {"user_id": user_id, "start": start, "end": today}
        scores = (await session.execute(text("""
            SELECT symbol, report_date, market_score, macro_score, technical_score,
                   calculated_at, indicator_evidence
            FROM daily_scores
            WHERE user_id = :user_id AND report_date BETWEEN :start AND :end
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
                           "sections": PERIOD_SECTIONS, "context": context}, ensure_ascii=False),
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
