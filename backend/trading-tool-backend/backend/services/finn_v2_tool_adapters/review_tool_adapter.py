from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import re

from fastapi import HTTPException
from sqlalchemy import text

from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
from backend.services.bot_service import BotService
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.schemas.finn_v2_evidence_schema import ReviewHistoryData
from backend.services.finn_closed_trade_reflection_service import FinnClosedTradeReflectionService
from backend.services.finn_v2_tool_adapters.display_source_moment import amsterdam_source_moment


class ReviewToolAdapter:
    def __init__(self, session):
        self.session = session
        self.bot_service = BotService(session)
        self.repository = BotRepository(session)
        self.sources = FinnV2InformationSourceRegistry()
        self.closed_trades = FinnClosedTradeReflectionService(session)

    @staticmethod
    def requested_review_id(message: str) -> int | None:
        match = re.search(r"\b(?:trade[ -]?review|trade[ -]?reflectie|review|reflectie|dossier)\s*#\s*(\d{1,12})\b", str(message or ""), re.I)
        return int(match.group(1)) if match else None

    @staticmethod
    def _utc_instant(value: datetime | str) -> datetime:
        instant = datetime.fromisoformat(value) if isinstance(value, str) else value
        # Legacy bot_decisions.decision_ts is TIMESTAMP WITHOUT TIME ZONE and
        # is written in UTC. Review exits are TIMESTAMPTZ. Normalize before
        # combining them; max(naive, aware) otherwise fails the whole read.
        return instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc)

    @staticmethod
    def _paper_exit_summary(raw: dict | None) -> str:
        if (not isinstance(raw, dict) or not isinstance(raw.get("trigger"), str)
                or raw["trigger"] not in {"stop_loss", "first_target"}):
            return ""

        def numeric(key: str) -> str | None:
            value = raw.get(key)
            try:
                amount = float(value)
            except (TypeError, ValueError, OverflowError):
                return None
            return str(amount) if math.isfinite(amount) and amount > 0 else None

        def instant(key: str) -> str | None:
            value = raw.get(key)
            if not isinstance(value, str):
                return None
            try:
                return ReviewToolAdapter._utc_instant(value).isoformat()
            except ValueError:
                return None

        currency = raw.get("source_price_currency")
        currency = currency if isinstance(currency, str) and currency in {"EUR", "USD", "USDT"} else None
        facts = [f"vastgelegd Paper-exitlabel {raw['trigger']} (botbewijs, geen onafhankelijke beursuitvoering)"]
        if currency:
            facts.append(f"opgeslagen stop {numeric('saved_stop_loss') or 'onbekend'} {currency}")
            facts.append(f"eerste doel {numeric('saved_first_target') or 'onbekend'} {currency}")
            facts.append(
                f"beslissingskoers {numeric('source_price') or 'onbekend'} {currency} "
                f"op {instant('source_price_at') or 'onbekend'}")
            facts.append(
                f"uitvoeringskoers {numeric('execution_source_price') or 'onbekend'} {currency} "
                f"op {instant('execution_source_price_at') or 'onbekend'}")
        facts.append(
            f"EUR-factor bij uitvoering {numeric('execution_fx_eur_per_unit') or 'onbekend'} "
            f"op {instant('execution_fx_observed_at') or 'onbekend'}")
        return "; " + "; ".join(facts)

    async def execute(self, *, user_id: int, asset: str | None = None, selector: dict | None = None,
                      review_id: int | None = None,
                      selected_feed_decision_id: int | None = None,
                      include_weekly_reflection: bool = False, **_kwargs):
        self.sources.get("review_history").validate_request(user_id=user_id)
        selected_feed_decision = None
        if type(selected_feed_decision_id) is int and selected_feed_decision_id > 0:
            selected_result = await self.session.execute(text("""
                SELECT d.id, d.bot_id, d.action, d.status, d.decision_ts,
                       d.amount_eur, b.name AS bot_name,
                       COALESCE(d.symbol, s.symbol, s.data->>'symbol', st.symbol, b.symbol) AS symbol,
                       tm.quote_currency,
                       COALESCE(b.is_live,FALSE) AS is_live,
                       o.status AS order_status, o.quote_amount_eur AS filled_amount_eur
                FROM bot_decisions d JOIN bot_configs b
                  ON b.id=d.bot_id AND b.user_id=d.user_id
                LEFT JOIN strategies s ON s.id=b.strategy_id AND s.user_id=b.user_id
                LEFT JOIN setups st ON st.id=s.setup_id AND st.user_id=b.user_id
                LEFT JOIN trading_markets tm ON tm.id=b.market_id
                LEFT JOIN LATERAL (
                  SELECT status, quote_amount_eur FROM bot_orders o
                  WHERE o.user_id=d.user_id AND o.bot_id=d.bot_id
                    AND o.decision_id=d.id AND o.execution_environment='paper'
                  ORDER BY o.id DESC LIMIT 1
                ) o ON TRUE
                WHERE d.user_id=:user_id AND d.id=:decision_id
                  AND COALESCE(b.is_live,FALSE)=FALSE
            """), {"user_id": user_id, "decision_id": selected_feed_decision_id})
            selected = selected_result.mappings().first()
            selected_symbol = str(selected["symbol"] or "").upper() if selected else ""
            selected_pair = (selected_symbol if "/" in selected_symbol else
                             f"{selected_symbol}/{selected['quote_currency']}"
                             if selected and selected["quote_currency"] else None)
            # A legacy Paper bot may save only BTC while the active chart uses
            # BTC/USDT. Keep that selected event, but do not let a persisted
            # BTC feed selection contaminate a later AAPL question.
            selected_base = selected_symbol.split("/", 1)[0]
            requested_base = str(asset or "").upper().split("/", 1)[0]
            if selected and (not asset or selected_base == requested_base):
                selected_feed_decision = {
                    "bot_name": selected["bot_name"],
                    "symbol": selected["symbol"], "action": selected["action"],
                    "pair": selected_pair,
                    "persistence_status": selected["status"],
                    "decision_at": self._utc_instant(selected["decision_ts"]).isoformat(),
                    "decision_at_amsterdam": amsterdam_source_moment(selected["decision_ts"]),
                    "paper_order_status": selected["order_status"],
                    "paper_executed": selected["status"] == "executed" and selected["order_status"] == "filled",
                    "filled_amount_eur": (selected["filled_amount_eur"]
                                          if selected["order_status"] == "filled" else None),
                }
        # A selected feed card asks about that event. A newer per-bot summary
        # would compete with it and can wrongly replace its historical time.
        latest_rows = ([] if review_id is not None or selected_feed_decision else
                       await self.repository.get_latest_bot_decisions_for_owner(user_id))
        if asset:
            requested = asset.upper()
            latest_rows = [row for row in latest_rows if (
                str(row.get("symbol") or "").upper() == requested
                or ("/" not in requested and str(row.get("symbol") or "").upper().split("/", 1)[0] == requested)
                or (row.get("symbol") and row.get("quote_currency") and
                    f'{row["symbol"]}/{row["quote_currency"]}'.upper() == requested)
            )]
        latest_decisions = []
        for row in latest_rows:
            if row.get("decision_ts") is None:
                continue
            raw_scores = row.get("scores_json")
            try:
                scores = raw_scores if isinstance(raw_scores, dict) else json.loads(raw_scores or "{}")
            except (TypeError, ValueError):
                scores = {}
            if not isinstance(scores, dict):
                scores = {}
            raw_reasons = row.get("reason_json")
            try:
                reasons = raw_reasons if isinstance(raw_reasons, (dict, list)) else json.loads(raw_reasons or "[]")
            except (TypeError, ValueError):
                reasons = []
            guardrails = scores.get("guardrails_result")
            safety = BotService._safety_contract({
                "id": row.get("decision_id"), "bot_id": row.get("bot_id"),
                "status": row.get("status"),
                "created_at": row.get("created_at") or row["decision_ts"],
                "guardrails_result": guardrails if isinstance(guardrails, dict) else None,
                "guardrails_checked_at": scores.get("guardrails_checked_at"),
                "requested_amount_eur": scores.get("requested_amount_eur"),
                "execution_failure": scores.get("execution_failure"),
                "strategy_reason": scores.get("strategy_reason"),
            }, bool(row.get("is_live")))
            decision = {
                "bot_name": str(row.get("bot_name") or "onbekend")[:100],
                "symbol": row.get("symbol"),
                "is_live": bool(row.get("is_live")),
                "action": row.get("action"),
                "persistence_status": row.get("status"),
                "decision_kind": row.get("decision_kind") or "assessment",
                "decision_at": self._utc_instant(row["decision_ts"]).isoformat(),
                "decision_at_amsterdam": amsterdam_source_moment(row["decision_ts"]),
            }
            if isinstance(guardrails, dict) or scores.get("execution_failure"):
                decision["safety_state"] = safety["state"]
                decision["safety_reason_code"] = safety["reason_code"]
            reason = safety.get("reason") or next(iter(BotService._display_reasons(reasons)), None)
            if isinstance(reason, str) and reason.strip():
                decision["safety_reason"] = re.sub(r"[\x00-\x1f\x7f]+", " ", reason).strip()[:300]
            if safety.get("checked_at"):
                decision["safety_checked_at"] = safety["checked_at"]
            if row.get("symbol") and row.get("quote_currency") and "/" not in str(row["symbol"]):
                decision["pair"] = f'{row["symbol"]}/{row["quote_currency"]}'
            latest_decisions.append(decision)
        if selector and selector.get("_latest_bot_decisions_only") and review_id is None and not selected_feed_decision:
            return {
                "data": ReviewHistoryData(latest_bot_decisions=latest_decisions),
                "summary": {"title": "review_history", "kind": "latest_bot_decisions",
                            "asset": asset, "count": len(latest_decisions)},
                "as_of": max(
                    (self._utc_instant(row["decision_ts"]) for row in latest_rows
                     if row.get("decision_ts") is not None), default=None,
                ),
                "source": "bot_decisions", "schema_name": "ReviewHistoryData",
                "entity_type": "review_history",
            }
        rows = [] if review_id is not None else await self.bot_service.get_bot_history(user_id, 30)
        if asset:
            rows = [row for row in rows if str(row.get("symbol") or "").upper() == asset.upper()]
        rows.sort(
            key=lambda row: self._utc_instant(row["decision_ts"])
            if row.get("decision_ts") is not None else datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        decision_items = [
            f"{'Bot-exitbeslissing; controleer het trade-dossier voor sluitingsbewijs: ' if row.get('decision_kind') == 'paper_exit' else 'Botbeslissing, geen bevestigde gesloten trade: '}"
            f"{amsterdam_source_moment(row['decision_ts'])} "
            f"({self._utc_instant(row['decision_ts']).isoformat()} UTC): "
            f"bot {row['bot_name']} ({row['symbol']}) actie {row['action']}; "
            f"opslagstatus {row['status']}; veiligheidsstatus "
            f"{(row.get('safety_check') or {}).get('state') or 'onbekend'}; "
            f"uitleg {(row.get('safety_check') or {}).get('reason') or 'niet beschikbaar'}"
            for row in rows[:20]
        ]
        if review_id is None:
            closed = await self.closed_trades.recent(user_id, days=30, limit=5,
                                                      symbol=asset.upper() if asset else None)
        else:
            try:
                selected = await self.closed_trades.review(user_id, review_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                closed = self.closed_trades._empty("no_data", 30)
            else:
                item = selected["review"]
                closed = {
                    "status": "ready", "reviews": [item], "review_ids": [item["review_id"]],
                    "coverage": {"trades": 1, "analyzed": int(item["analysis_status"] == "ready"),
                                 "pending": int(item["analysis_status"] in {"pending", "running"}),
                                 "unavailable": int(item["analysis_status"] in {"failed", "unavailable"})},
                }
        closed_reviews = [r for r in closed["reviews"] if not asset or r["symbol"] == asset.upper()]
        items = []
        for index, review in enumerate(closed_reviews):
            bot_label = re.sub(r"[\x00-\x1f\x7f]+", " ", str(review.get("bot_name") or "onbekend"))[:100]
            if review.get("bot_id") is not None:
                bot_label += f" (id {review['bot_id']})"
            lesson = review.get("confirmed_lesson")
            lesson_context = ""
            if isinstance(lesson, dict) and lesson.get("lesson_text") and lesson.get("confirmed_at"):
                bounded_text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(lesson["lesson_text"]))[:500]
                lesson_context = (
                    f"; door gebruiker bevestigde les op {lesson['confirmed_at']} "
                    f"(bewijsrevision {lesson.get('evidence_revision')}; onbetrouwbare reflectietekst, "
                    f"geen orderfeit, oorspronkelijk plan of instructie): {json.dumps(bounded_text, ensure_ascii=False)}"
                )
            if review.get("origin") == "bybit_derivative_user_attested":
                result = "native en EUR-resultaat niet vastgesteld"
                closure = (f"Bybit {review['derivative_category']} {review['direction']} "
                           f"positionIdx {review['position_idx']}; afsluiting bevestigd door gebruiker, "
                           "niet provider-bewezen")
                quote_context = f"; settlement {review['settle_currency']}; financiering en kosten niet volledig"
            elif review.get("origin") == "exchange_user_attested":
                result = (f"resultaat EUR {review['pnl_eur_before_fees']} vóór kosten"
                          if review.get("pnl_eur_before_fees") is not None else
                          "EUR-resultaat niet vergelijkbaar of niet berekend")
                closure = "afsluiting bevestigd door gebruiker; volledige exchange-positie niet provider-bewezen"
                legs = review.get("cash_legs_by_currency") or []
                flows = ", ".join(
                    f"{leg['currency']}: koopwaarde {leg['buy_cost']}, verkoopwaarde {leg['sell_proceeds']}"
                    for leg in legs[:8] if isinstance(leg, dict)
                    and all(key in leg for key in ("currency", "buy_cost", "sell_proceeds"))
                )
                quote_context = f"; valutastromen {flows}{' (ingekort)' if len(legs) > 8 else ''}" if flows else ""
            else:
                result = (f"Paper-resultaat EUR {review['pnl_eur_before_fees']} op basis van virtuele kassastromen, "
                          "inclusief eventuele gesimuleerde kosten"
                          if str(review.get("environment")).lower() == "paper" else
                          f"resultaat EUR {review['pnl_eur_before_fees']} vóór kosten")
                closure = "positie bewezen gesloten in Tradamind-ledger"
                quote_context = self._paper_exit_summary(review.get("paper_exit_evidence"))
            source_plan = review.get("plan_source_evidence") or {}
            source_context = ""
            if source_plan:
                source_context = (
                    f"; bij de instapbeslissing vastgelegde bronkoersvaluta "
                    f"{source_plan['source_price_currency']}; bronniveaus "
                    f"{json.dumps(source_plan['source_levels'], ensure_ascii=False)}; "
                    f"beslissingsmoment {source_plan['source_decision_at']}; "
                    f"EUR-factor bij die beslissing {source_plan.get('fx_eur_per_unit') or 'onbekend'} "
                    f"met bronmoment {source_plan.get('fx_as_of') or 'onbekend'}; "
                    "oorspronkelijke orderplansnapshot en beslissingsbron zijn afzonderlijk bewijs"
                )
            order_plan = review.get("order_plan_evidence") or {}
            order_context = ""
            if order_plan:
                plan_label = ("afzonderlijk opgeslagen orderplandoel"
                              if order_plan["provenance"] == "bot_order_context"
                              else "afzonderlijk vastgelegd plandoel")
                order_context = (
                    f"; {plan_label} {order_plan['first_target']} "
                    f"{order_plan['price_currency']} (bewijs plan:snapshot; "
                    f"herkomst {order_plan['provenance']})"
                )
                if order_plan.get("fx_eur_per_unit"):
                    order_context += (
                        f"; EUR-factor bij dat opgeslagen plan {order_plan['fx_eur_per_unit']} "
                        f"op {order_plan.get('fx_as_of') or 'onbekend'}"
                    )
            items.append(
                f"{'Nieuwste: ' if index == 0 else ''}Bevestigde gesloten trade #{review['review_id']} "
                f"(instap {review['entry_at']}, uitstap {review['exit_at']}; {review['symbol']}, "
                f"{review['environment']}, bot: {json.dumps(bot_label, ensure_ascii=False)}, "
                f"bronnen: {', '.join(review['execution_sources'])}): "
                f"{closure}; {result}{quote_context}{source_context}{order_context}; "
                f"FINN-analyse {review['analysis_status']}; thema's "
                f"{', '.join(review['themes']) if review['themes'] else 'geen'} "
                f"(modelobservatie, geen bewezen oorzaak); bewijs {', '.join(review['evidence_ids'])}; "
                f"review {review['review_url']}{lesson_context}"
            )
        items.extend(decision_items)
        if selected_feed_decision:
            items.insert(0, "Geselecteerde historische Paper-feedbeslissing: "
                         + json.dumps(selected_feed_decision, ensure_ascii=False, default=str)
                         + ". Een nieuwere botcontrole vervangt dit besluit niet; "
                         "een bevestigde gesloten trade blijft afzonderlijk dossierbewijs.")
        items.append(
            f"Gesloten-tradedekking: {closed['status']}; {closed['coverage']['trades']} "
            f"bevestigde trades {'voor review #' + str(review_id) if review_id else 'in 30 dagen'}. "
            "Exchange-uitvoeringen tellen alleen na bewezen sluiting of expliciete gebruikersbevestiging als gesloten trade; oudere trades kunnen ontbreken; "
            "botbeslissingen hierboven zijn geen trade-uitkomsten."
        )
        weekly_reflection = None
        weekly_as_of = None
        if include_weekly_reflection and review_id is None:
            saved = await self.session.execute(text("""
                SELECT week_start, week_end, summary, generated_at
                FROM finn_weekly_trade_reflections
                WHERE user_id=:user_id
                ORDER BY week_start DESC LIMIT 1
            """), {"user_id": user_id})
            row = saved.mappings().first()
            if row:
                summary = row["summary"]
                if isinstance(summary, str):
                    try:
                        summary = json.loads(summary)
                    except ValueError:
                        summary = None
                if isinstance(summary, dict):
                    weekly_reflection = {
                        "week_start": row["week_start"].isoformat(),
                        "week_end": (row["week_end"] - timedelta(days=1)).isoformat(),
                        "week_end_exclusive": row["week_end"].isoformat(),
                        "generated_at": self._utc_instant(row["generated_at"]).isoformat(),
                        **{key: summary[key] for key in
                           ("trades", "plans", "notes", "analyzed", "pending", "unavailable")
                           if type(summary.get(key)) is int and 0 <= summary[key] <= 100000},
                        "observed_patterns": [
                            {"theme": pattern["theme"], "count": pattern["count"]}
                            for pattern in (summary.get("patterns") or [])[:7]
                            if isinstance(pattern, dict)
                            and pattern.get("theme") in {"plan_followed", "risk", "timing",
                                "exit_process", "evidence_gap", "missing_plan", "plan_not_recorded"}
                            and type(pattern.get("count")) is int and 1 <= pattern["count"] <= 500
                        ],
                    }
                    weekly_as_of = self._utc_instant(row["generated_at"])
                    items.append(
                        f"Opgeslagen weekreflectie {weekly_reflection['week_start']} tot "
                        f"{weekly_reflection['week_end']}: {weekly_reflection.get('trades', 0)} "
                        f"gesloten trades; {weekly_reflection.get('plans', 0)} met plan; "
                        f"{weekly_reflection.get('analyzed', 0)} geanalyseerd. "
                        "De thematelling is een observatie, geen bewezen terugkerend gedrag."
                    )
        return {
            "data": ReviewHistoryData(
                items=[item for item in items if item],
                weekly_reflection=weekly_reflection,
                latest_bot_decisions=latest_decisions,
                selected_feed_decision=selected_feed_decision,
                closed_trade_status=closed["status"],
                closed_trade_coverage=closed["coverage"],
                closed_trade_review_ids=[r["review_id"] for r in closed_reviews],
                closed_trades=[{
                    "review_id": review["review_id"],
                    "symbol": review["symbol"],
                    "environment": review["environment"],
                    "bot_id": review.get("bot_id"),
                    "bot_name": review.get("bot_name"),
                    "entry_at": review["entry_at"],
                    "exit_at": review["exit_at"],
                    "pnl_eur": review.get("pnl_eur_before_fees"),
                    "pnl_basis": review["pnl_status"],
                    "has_original_plan": review["has_plan"],
                    "plan_source_evidence": review.get("plan_source_evidence"),
                    "order_plan_evidence": review.get("order_plan_evidence"),
                    "evidence_ids": review["evidence_ids"][:20],
                    "confirmed_lesson": (
                        {
                            "lesson_text": re.sub(
                                r"[\x00-\x1f\x7f]+", " ",
                                str(review["confirmed_lesson"]["lesson_text"]),
                            )[:500],
                            "confirmed_at": review["confirmed_lesson"]["confirmed_at"],
                            "evidence_revision": review["confirmed_lesson"].get("evidence_revision"),
                            "source": "user_confirmed_reflection_not_trade_fact_or_original_plan",
                        }
                        if isinstance(review.get("confirmed_lesson"), dict)
                        and review["confirmed_lesson"].get("lesson_text")
                        and review["confirmed_lesson"].get("confirmed_at")
                        else None
                    ),
                } for review in closed_reviews],
            ),
            "summary": {"title": "review_history", "kind": "bot_decisions_and_closed_trades", "asset": asset,
                        "count": len(items), "closed_trade_status": closed["status"],
                        "closed_trade_review_ids": [r["review_id"] for r in closed_reviews],
                        "requested_review_id": review_id},
            "as_of": max(
                [self._utc_instant(row["decision_ts"]) for row in rows if row.get("decision_ts") is not None]
                + [self._utc_instant(row["decision_ts"]) for row in latest_rows if row.get("decision_ts") is not None]
                + [self._utc_instant(review["exit_at"]) for review in closed_reviews]
                + ([weekly_as_of] if weekly_as_of else []),
                default=None,
            ),
            "source": "bot_decisions_and_finn_trade_reviews",
            "schema_name": "ReviewHistoryData",
            "entity_type": "review_history",
        }
