from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from fastapi import HTTPException

from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
from backend.services.bot_service import BotService
from backend.schemas.finn_v2_evidence_schema import ReviewHistoryData
from backend.services.finn_closed_trade_reflection_service import FinnClosedTradeReflectionService


class ReviewToolAdapter:
    def __init__(self, session):
        self.bot_service = BotService(session)
        self.sources = FinnV2InformationSourceRegistry()
        self.closed_trades = FinnClosedTradeReflectionService(session)

    @staticmethod
    def requested_review_id(message: str) -> int | None:
        match = re.search(r"\b(?:trade[ -]?review|trade[ -]?reflectie|review)\s*#\s*(\d{1,12})\b", str(message or ""), re.I)
        return int(match.group(1)) if match else None

    @staticmethod
    def _utc_instant(value: datetime | str) -> datetime:
        instant = datetime.fromisoformat(value) if isinstance(value, str) else value
        # Legacy bot_decisions.decision_ts is TIMESTAMP WITHOUT TIME ZONE and
        # is written in UTC. Review exits are TIMESTAMPTZ. Normalize before
        # combining them; max(naive, aware) otherwise fails the whole read.
        return instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc)

    async def execute(self, *, user_id: int, asset: str | None = None, selector: dict | None = None,
                      review_id: int | None = None, **_kwargs):
        self.sources.get("review_history").validate_request(user_id=user_id)
        rows = [] if review_id is not None else await self.bot_service.get_bot_history(user_id, 30)
        if asset:
            rows = [row for row in rows if str(row.get("symbol") or "").upper() == asset.upper()]
        decision_items = [
            f"Botbeslissing, geen bevestigde gesloten trade: {row['decision_ts']}: "
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
                quote_context = ""
            items.append(
                f"{'Nieuwste: ' if index == 0 else ''}Bevestigde gesloten trade #{review['review_id']} "
                f"(instap {review['entry_at']}, uitstap {review['exit_at']}; {review['symbol']}, "
                f"{review['environment']}, bot: {json.dumps(bot_label, ensure_ascii=False)}, "
                f"bronnen: {', '.join(review['execution_sources'])}): "
                f"{closure}; {result}{quote_context}; "
                f"FINN-analyse {review['analysis_status']}; thema's "
                f"{', '.join(review['themes']) if review['themes'] else 'geen'} "
                f"(modelobservatie, geen bewezen oorzaak); bewijs {', '.join(review['evidence_ids'])}; "
                f"review {review['review_url']}{lesson_context}"
            )
        items.extend(decision_items)
        items.append(
            f"Gesloten-tradedekking: {closed['status']}; {closed['coverage']['trades']} "
            f"bevestigde trades {'voor review #' + str(review_id) if review_id else 'in 30 dagen'}. "
            "Exchange-uitvoeringen tellen alleen na bewezen sluiting of expliciete gebruikersbevestiging als gesloten trade; oudere trades kunnen ontbreken; "
            "botbeslissingen hierboven zijn geen trade-uitkomsten."
        )
        return {
            "data": ReviewHistoryData(
                items=[item for item in items if item],
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
                + [self._utc_instant(review["exit_at"]) for review in closed_reviews],
                default=None,
            ),
            "source": "bot_decisions_and_finn_trade_reviews",
            "schema_name": "ReviewHistoryData",
            "entity_type": "review_history",
        }
