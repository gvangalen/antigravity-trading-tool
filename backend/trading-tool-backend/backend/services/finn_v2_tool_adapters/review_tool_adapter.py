from __future__ import annotations

from datetime import date, datetime, timedelta
import re

from fastapi import HTTPException

from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.schemas.finn_v2_evidence_schema import ReviewHistoryData
from backend.services.finn_closed_trade_reflection_service import FinnClosedTradeReflectionService


class ReviewToolAdapter:
    def __init__(self, session):
        self.repository = BotRepository(session)
        self.sources = FinnV2InformationSourceRegistry()
        self.closed_trades = FinnClosedTradeReflectionService(session)

    @staticmethod
    def requested_review_id(message: str) -> int | None:
        match = re.search(r"\b(?:trade[ -]?review|trade[ -]?reflectie|review)\s*#\s*(\d{1,12})\b", str(message or ""), re.I)
        return int(match.group(1)) if match else None

    async def execute(self, *, user_id: int, asset: str | None = None, selector: dict | None = None,
                      review_id: int | None = None, **_kwargs):
        self.sources.get("review_history").validate_request(user_id=user_id)
        rows = [] if review_id is not None else await self.repository.get_bot_history(
            user_id, date.today() - timedelta(days=30), date.today()
        )
        if asset:
            rows = [row for row in rows if str(row.get("symbol") or "").upper() == asset.upper()]
        items = [
            f"Botbeslissing, geen bevestigde gesloten trade: {row['decision_ts']}: "
            f"bot {row['bot_name']} ({row['symbol']}) {row['action']} (status: {row['status']})"
            for row in rows[:20]
        ]
        if review_id is None:
            closed = await self.closed_trades.recent(user_id, days=30, limit=5)
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
        for review in closed_reviews:
            if review.get("origin") == "exchange_user_attested":
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
                result = f"resultaat EUR {review['pnl_eur_before_fees']} vóór kosten"
                closure = "positie bewezen gesloten in Tradamind-ledger"
                quote_context = ""
            items.append(
                f"Bevestigde gesloten trade #{review['review_id']} ({review['symbol']}, "
                f"{review['environment']}, bronnen: {', '.join(review['execution_sources'])}): "
                f"{closure}; {result}{quote_context}; "
                f"FINN-analyse {review['analysis_status']}; thema's "
                f"{', '.join(review['themes']) if review['themes'] else 'geen'} "
                f"(modelobservatie, geen bewezen oorzaak); bewijs {', '.join(review['evidence_ids'])}; "
                f"review {review['review_url']}"
            )
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
            ),
            "summary": {"title": "review_history", "kind": "bot_decisions_and_closed_trades", "asset": asset,
                        "count": len(items), "closed_trade_status": closed["status"],
                        "closed_trade_review_ids": [r["review_id"] for r in closed_reviews],
                        "requested_review_id": review_id},
            "as_of": max(
                [row["decision_ts"] for row in rows if row.get("decision_ts") is not None]
                + [datetime.fromisoformat(review["exit_at"]) for review in closed_reviews],
                default=None,
            ),
            "source": "bot_decisions_and_finn_trade_reviews",
            "schema_name": "ReviewHistoryData",
            "entity_type": "review_history",
        }
