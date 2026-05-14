import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_, desc, update

from backend.infrastructure.models import AiIntelligenceEvent, User, MobilePushToken
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.push_service import push_service

logger = logging.getLogger(__name__)

class IntelligenceEventService:
    def __init__(
        self,
        session,
        bot_repo: BotRepository,
        market_data_repo: MarketDataRepository,
        score_repo: ScoreRepository
    ):
        self.session = session
        self.bot_repo = bot_repo
        self.market_data_repo = market_data_repo
        self.score_repo = score_repo

    async def get_active_events(self, user_id: int) -> List[AiIntelligenceEvent]:
        """
        Grijp alle actieve, ongearchiveerde events voor de gebruiker.
        """
        stmt = (
            select(AiIntelligenceEvent)
            .where(
                and_(
                    AiIntelligenceEvent.user_id == user_id,
                    AiIntelligenceEvent.status == "active"
                )
            )
            .order_by(desc(AiIntelligenceEvent.created_at))
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def archive_event(self, user_id: int, event_id: int) -> bool:
        """
        Zet de status van een event op 'archived' (grijpt in bij sluiten of wegklikken).
        """
        stmt = (
            update(AiIntelligenceEvent)
            .where(
                and_(
                    AiIntelligenceEvent.id == event_id,
                    AiIntelligenceEvent.user_id == user_id
                )
            )
            .values(status="archived")
        )
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount > 0

    async def is_cooldown_active(self, user_id: int, symbol: Optional[str], event_type: str) -> bool:
        """
        Controleert of er recent (binnen de laatste 1 uur) al een actief event is aangemaakt
        met exact hetzelfde type, user_id, en symbol om herhaaldelijke alerts te dempen.
        """
        cooldown_threshold = datetime.utcnow() - timedelta(hours=1)
        stmt = (
            select(AiIntelligenceEvent)
            .where(
                and_(
                    AiIntelligenceEvent.user_id == user_id,
                    AiIntelligenceEvent.type == event_type,
                    AiIntelligenceEvent.symbol == symbol,
                    AiIntelligenceEvent.created_at >= cooldown_threshold
                )
            )
        )
        res = await self.session.execute(stmt)
        return res.scalars().first() is not None

    async def evaluate_and_generate_events(self, user_id: int) -> List[AiIntelligenceEvent]:
        """
        Centrale realtime engine die deterministische regels toepast op de actieve
        portfolio, bot performance en marktcondities van de gebruiker.
        """
        new_events = []
        
        # 1. Haal de benodigde context en entiteiten op
        portfolio_intel = await self.bot_repo.get_portfolio_intelligence_context(user_id)
        bots = portfolio_intel.get("bots", [])
        
        # Haal gebruikersvoorkeuren (risicoprofiel) op
        user_stmt = select(User).where(User.id == user_id)
        user_res = await self.session.execute(user_stmt)
        user = user_res.scalars().first()
        preferences = getattr(user, "ai_preferences", {}) or {}
        risk_profile = preferences.get("risk_profile", "balanced").lower()

        total_budget = sum(b.get("budget_total", 0.0) for b in bots)

        # ----------------------------------------------------------------------
        # RULE 0: Macro Defensive Override (Contraction Regime < 35)
        # ----------------------------------------------------------------------
        daily_scores = await self.score_repo.fetch_daily_scores(user_id, symbol="BTC")
        if daily_scores and daily_scores.get("macro_score") is not None:
            macro_val = float(daily_scores.get("macro_score"))
            if macro_val < 35.0:
                event_type = "defensive_posture"
                if not await self.is_cooldown_active(user_id, "BTC", event_type):
                    event = AiIntelligenceEvent(
                        user_id=user_id,
                        type=event_type,
                        symbol="BTC",
                        title="Macro Regime Override",
                        description=f"Macro environment entered contraction regime (Score {macro_val:.0f} < 35). Portfolio switched to defensive posture with 0.2x position sizing constraints.",
                        severity="critical",
                        payload={
                            "macro_score": macro_val,
                            "multiplier": 0.2,
                            "affected_bots": len(bots)
                        }
                    )
                    self.session.add(event)
                    new_events.append(event)

        # ----------------------------------------------------------------------
        # RULE 1: Drawdown Alerts (Als een bot >10% verlies heeft op zijn budget)
        # ----------------------------------------------------------------------
        for b in bots:
            symbol = b.get("symbol", "BTC").upper()
            budget = float(b.get("budget_total", 0.0))
            unrealized_pnl = float(b.get("unrealized_pnl", 0.0))
            
            if budget > 0 and unrealized_pnl < 0:
                pnl_pct = (unrealized_pnl / budget) * 100
                if pnl_pct <= -10.0:
                    event_type = "drawdown_alert"
                    if not await self.is_cooldown_active(user_id, symbol, event_type):
                        event = AiIntelligenceEvent(
                            user_id=user_id,
                            type=event_type,
                            symbol=symbol,
                            title=f"Drawdown Alert: {symbol} Bot",
                            description=f"De active trading bot '{b.get('name')}' voor {symbol} noteert momenteel een ongerealiseerd verlies van {pnl_pct:.1f}% (${unrealized_pnl:,.2f}) ten opzichte van het toegewezen budget.",
                            severity="warning",
                            payload={
                                "bot_id": b.get("bot_id"),
                                "unrealized_pnl": unrealized_pnl,
                                "pnl_pct": pnl_pct,
                                "budget": budget
                            }
                        )
                        self.session.add(event)
                        new_events.append(event)

        # ----------------------------------------------------------------------
        # RULE 2: Overconcentration Risk (Regels gebaseerd op risicoprofielen)
        # ----------------------------------------------------------------------
        if total_budget > 0:
            # Bereken allocatie per symbol
            symbol_budgets = {}
            for b in bots:
                sym = b.get("symbol", "BTC").upper()
                symbol_budgets[sym] = symbol_budgets.get(sym, 0.0) + float(b.get("budget_total", 0.0))
            
            # Profiel-drempelwaarden
            thresholds = {
                "conservative": 40.0,
                "balanced": 60.0,
                "aggressive": 80.0
            }
            limit = thresholds.get(risk_profile, 60.0)

            for sym, sym_budget in symbol_budgets.items():
                pct = (sym_budget / total_budget) * 100
                if pct > limit:
                    event_type = "risk_spike"
                    severity = "critical" if pct > (limit + 15.0) else "warning"
                    if not await self.is_cooldown_active(user_id, sym, event_type):
                        event = AiIntelligenceEvent(
                            user_id=user_id,
                            type=event_type,
                            symbol=sym,
                            title=f"Risico Concentratie: {sym}",
                            description=f"Je {sym} blootstelling bedraagt nu {pct:.1f}% van je totale actieve budget. Dit overschrijdt de aanbevolen grens van {limit:.0f}% voor een {risk_profile} risicoprofiel.",
                            severity=severity,
                            payload={
                                "allocation_pct": pct,
                                "threshold_limit": limit,
                                "risk_profile": risk_profile,
                                "symbol_budget": sym_budget,
                                "total_budget": total_budget
                            }
                        )
                        self.session.add(event)
                        new_events.append(event)

        # ----------------------------------------------------------------------
        # RULE 3: Duplicate Strategy Clusters (Meerdere bots op dezelfde setup/strategie)
        # ----------------------------------------------------------------------
        strategy_clusters = {}
        for b in bots:
            sym = b.get("symbol", "BTC").upper()
            # Gebruik risk_profile of sub-strategie als identificatie
            strat_key = b.get("risk_profile", "default")
            cluster_id = f"{sym}-{strat_key}"
            
            if cluster_id not in strategy_clusters:
                strategy_clusters[cluster_id] = []
            strategy_clusters[cluster_id].append(b)

        for cid, cluster_bots in strategy_clusters.items():
            if len(cluster_bots) >= 2:
                sym = cluster_bots[0].get("symbol", "BTC").upper()
                strat_name = cluster_bots[0].get("risk_profile", "Standaard")
                event_type = "duplicate_strategy"
                if not await self.is_cooldown_active(user_id, sym, event_type):
                    event = AiIntelligenceEvent(
                        user_id=user_id,
                        type=event_type,
                        symbol=sym,
                        title=f"Gecorreleerd Risico: Overlap {sym}",
                        description=f"Je hebt momenteel {len(cluster_bots)} actieve bots die exact dezelfde risk-setup '{strat_name}' draaien op {sym}. Dit verhoogt gecorreleerde risico's bij onverwachte marktbewegingen.",
                        severity="info",
                        payload={
                            "bots_count": len(cluster_bots),
                            "strategy": strat_name,
                            "bot_ids": [b.get("bot_id") for b in cluster_bots]
                        }
                    )
                    self.session.add(event)
                    new_events.append(event)

        # ----------------------------------------------------------------------
        # RULE 4: Volatility Expansion (Gebaseerd op 24h market-price wijziging)
        # ----------------------------------------------------------------------
        watchlist_symbols = list(set([b.get("symbol", "BTC").upper() for b in bots] + ["BTC", "ETH", "SOL"]))
        for sym in watchlist_symbols:
            live_data = await self.market_data_repo.get_latest_market_data(sym)
            if live_data and live_data.change_24h is not None:
                change = float(live_data.change_24h)
                if abs(change) >= 10.0:
                    event_type = "volatility_expansion"
                    severity = "warning" if abs(change) >= 15.0 else "info"
                    if not await self.is_cooldown_active(user_id, sym, event_type):
                        direction = "stijging" if change > 0 else "daling"
                        event = AiIntelligenceEvent(
                            user_id=user_id,
                            type=event_type,
                            symbol=sym,
                            title=f"Volatiel Marktgedrag: {sym}",
                            description=f"Sterke volatiliteit waargenomen op {sym}. De 24-uurs koersmutatie bedraagt een {direction} van {change:+.1f}%. Pas eventuele instap- en DCA-zones hierop aan.",
                            severity=severity,
                            payload={
                                "change_24h": change,
                                "price": float(live_data.price) if live_data.price else 0.0
                            }
                        )
                        self.session.add(event)
                        new_events.append(event)

        # ----------------------------------------------------------------------
        # Flush & Commit
        # ----------------------------------------------------------------------
        if new_events:
            await self.session.flush()
            await self.session.commit()
            
            # Verzend Push Notificaties uitsluitend voor Hoge Prioriteit/Kritieke events
            for ev in new_events:
                if ev.severity in ["critical", "warning"]:
                    try:
                        title = f"TM Alert: {ev.title}"
                        message = ev.description
                        # notify_user stuurt notificatie naar zowel web push (PWA) als expo push tokens (Native Mobile)
                        await push_service.notify_user_async(self.session, user_id, title, message)
                        logger.info(f"📱 Proactieve push notification verzonden voor kritiek event: {ev.title} (User: {user_id})")
                    except Exception as ex:
                        logger.error(f"⚠️ Push notification dispatch mislukt: {ex}")
                        await self.session.rollback()

        return new_events
