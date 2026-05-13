from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import date
import json

class BotRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_table_exists(self, table_name: str) -> bool:
        query = text("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:table_name
        """)
        result = await self.session.execute(query, {"table_name": table_name})
        return result.fetchone() is not None

    async def get_daily_scores_row(self, user_id: int, report_date: date) -> Optional[dict]:
        if not await self.check_table_exists("daily_scores"):
            return None
        query = text("""
            SELECT macro_score, technical_score, market_score, setup_score
            FROM daily_scores
            WHERE user_id=:user_id AND report_date=:report_date
            LIMIT 1
        """)
        result = await self.session.execute(query, {"user_id": user_id, "report_date": report_date})
        row = result.fetchone()
        if not row:
            return None
        return {
            "macro": float(row[0] or 10),
            "technical": float(row[1] or 10),
            "market": float(row[2] or 10),
            "setup": float(row[3] or 10),
        }

    async def get_bot_configs(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT
              b.id, b.name, b.is_active, b.is_live, b.mode, b.cadence, b.risk_profile,
              b.budget_total_eur, b.budget_daily_limit_eur, b.budget_min_order_eur,
              b.budget_max_order_eur, b.max_asset_exposure_pct, b.base_currency, b.last_run,
              COALESCE(st.symbol, 'BTC') AS symbol, b.created_at, b.updated_at,
              s.id AS strategy_id, s.name AS strategy_name, s.setup_type AS setup_type,
              st.id AS setup_id, st.name AS setup_name, st.symbol AS setup_symbol, st.timeframe AS timeframe
            FROM bot_configs b
            LEFT JOIN strategies s ON s.id = b.strategy_id
            LEFT JOIN setups st    ON st.id = s.setup_id
            WHERE b.user_id = :user_id
            ORDER BY b.id ASC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_bot_config(self, user_id: int, bot_id: int) -> Optional[dict]:
        query = text("""
            SELECT
              b.id, b.name, b.is_active, b.is_live, b.mode, b.cadence, b.risk_profile,
              b.budget_total_eur, b.budget_daily_limit_eur, b.budget_min_order_eur,
              b.budget_max_order_eur, b.max_asset_exposure_pct, b.base_currency, b.last_run,
              COALESCE(st.symbol, 'BTC') AS symbol, b.created_at, b.updated_at,
              s.id AS strategy_id, s.name AS strategy_name, s.setup_type AS setup_type,
              st.id AS setup_id, st.name AS setup_name, st.symbol AS setup_symbol, st.timeframe AS timeframe
            FROM bot_configs b
            LEFT JOIN strategies s ON s.id = b.strategy_id
            LEFT JOIN setups st    ON st.id = s.setup_id
            WHERE b.user_id = :user_id AND b.id = :bot_id
            LIMIT 1
        """)
        result = await self.session.execute(query, {"user_id": user_id, "bot_id": bot_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_active_bots_with_setups(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT b.id, b.name,
              COALESCE(st.symbol,'BTC') AS symbol,
              COALESCE(st.timeframe,'—') AS timeframe,
              s.setup_type,
              st.name AS setup_name
            FROM bot_configs b
            LEFT JOIN strategies s ON s.id = b.strategy_id
            LEFT JOIN setups st    ON st.id = s.setup_id
            WHERE b.user_id=:user_id AND b.is_active=TRUE
            ORDER BY b.id ASC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_bot_decisions_by_date(self, user_id: int, decision_date: date) -> List[dict]:
        query = text("""
            SELECT
              id, bot_id, symbol, decision_ts, action, confidence,
              scores_json, reason_json, setup_id, strategy_id, status,
              created_at, updated_at
            FROM bot_decisions
            WHERE user_id=:user_id AND decision_date=:decision_date
            ORDER BY bot_id ASC, id DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id, "decision_date": decision_date})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_bot_trade_plan(self, user_id: int, decision_id: int) -> Optional[dict]:
        if not await self.check_table_exists("bot_trade_plans"):
            return None
        query = text("""
            SELECT entry_plan, stop_loss, targets, risk_json
            FROM bot_trade_plans
            WHERE decision_id=:decision_id AND user_id=:user_id
        """)
        result = await self.session.execute(query, {"decision_id": decision_id, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_bot_history(self, user_id: int, start_date: date, end_date: date) -> List[dict]:
        if not await self.check_table_exists("bot_decisions"):
            return []
        query = text("""
            SELECT
              d.id, d.bot_id, b.name AS bot_name, d.symbol, d.decision_ts, d.decision_date,
              d.action, d.confidence, d.scores_json, d.reason_json, d.status
            FROM bot_decisions d
            JOIN bot_configs b ON b.id = d.bot_id
            WHERE d.user_id=:user_id AND d.decision_date BETWEEN :start AND :end
            ORDER BY d.decision_date DESC, d.bot_id ASC, d.id DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id, "start": start_date, "end": end_date})
        return [dict(r._mapping) for r in result.fetchall()]

    # ==========================
    # MANUAL ORDER / LEDGER
    # ==========================
    async def create_manual_order(self, user_id: int, bot_id: int, symbol: str, side: str, quantity: float, price: float) -> int:
        query = text("""
            INSERT INTO bot_orders (
                user_id, bot_id, decision_id, symbol, side, order_type,
                quantity, limit_price, status, source, created_at, updated_at
            )
            VALUES (:user_id,:bot_id,NULL,:symbol,:side,'market',:quantity,:price,'filled','manual',NOW(),NOW())
            RETURNING id
        """)
        result = await self.session.execute(query, {
            "user_id": user_id, "bot_id": bot_id, "symbol": symbol, "side": side, "quantity": quantity, "price": price
        })
        return result.fetchone()[0]

    async def create_bot_execution(self, user_id: int, order_id: int, quantity: float, price: float) -> int:
        query = text("""
            INSERT INTO bot_executions (
                user_id, bot_order_id, filled_qty, avg_fill_price, status, created_at
            )
            VALUES (:user_id,:order_id,:quantity,:price,'filled',NOW())
            RETURNING id
        """)
        result = await self.session.execute(query, {"user_id": user_id, "order_id": order_id, "quantity": quantity, "price": price})
        return result.fetchone()[0]

    async def insert_bot_ledger(self, user_id: int, bot_id: int, order_id: int, symbol: str, cash_delta: float, qty_delta: float, price_eur: Optional[float] = None):
        # 1. Insert into ledger (record everything)
        query_ledger = text("""
            INSERT INTO bot_ledger (
                user_id, bot_id, order_id, symbol, entry_type,
                cash_delta_eur, qty_delta, price_eur, ts
            )
            VALUES (:user_id,:bot_id,:order_id,:symbol,'execute',:cash_delta,:qty_delta,:price_eur,NOW())
        """)
        await self.session.execute(query_ledger, {
            "user_id": user_id, "bot_id": bot_id, "order_id": order_id, "symbol": symbol, 
            "cash_delta": cash_delta, "qty_delta": qty_delta, "price_eur": price_eur
        })

        # 2. Atomic Portfolio Update (WAC Logic)
        # We gebruiken een UPSERT om de staat bij te werken.
        # Bij een BUY (qty_delta > 0): invested_eur stijgt, avg_entry wordt herberekend.
        # Bij een SELL (qty_delta < 0): realized_pnl wordt geboekt, invested_eur daalt proportioneel.
        query_portfolio = text("""
            INSERT INTO bot_portfolios (user_id, bot_id, symbol, cash_eur, position_qty, invested_eur, avg_entry, realized_pnl_eur, updated_at)
            SELECT 
                :user_id, :bot_id, :symbol, CAST(:cash_delta AS NUMERIC), CAST(:qty_delta AS NUMERIC),
                CASE WHEN CAST(:qty_delta AS NUMERIC) > 0 THEN ABS(CAST(:cash_delta AS NUMERIC)) ELSE 0 END,
                CASE WHEN CAST(:qty_delta AS NUMERIC) > 0 THEN ABS(CAST(:cash_delta AS NUMERIC)) / CAST(:qty_delta AS NUMERIC) ELSE 0 END,
                0, NOW()
            ON CONFLICT (bot_id) DO UPDATE SET
                cash_eur = bot_portfolios.cash_eur + EXCLUDED.cash_eur,
                realized_pnl_eur = bot_portfolios.realized_pnl_eur + (
                    CASE 
                        WHEN EXCLUDED.position_qty < 0 AND bot_portfolios.position_qty > 0 THEN
                            ABS(EXCLUDED.cash_eur) - (ABS(EXCLUDED.position_qty) / bot_portfolios.position_qty * bot_portfolios.invested_eur)
                        ELSE 0 
                    END
                ),
                invested_eur = (
                    CASE 
                        WHEN EXCLUDED.position_qty > 0 THEN bot_portfolios.invested_eur + ABS(EXCLUDED.cash_eur)
                        WHEN EXCLUDED.position_qty < 0 AND bot_portfolios.position_qty > 0 THEN
                            bot_portfolios.invested_eur - (ABS(EXCLUDED.position_qty) / bot_portfolios.position_qty * bot_portfolios.invested_eur)
                        ELSE bot_portfolios.invested_eur
                    END
                ),
                position_qty = bot_portfolios.position_qty + EXCLUDED.position_qty,
                avg_entry = (
                    CASE 
                        WHEN (bot_portfolios.position_qty + EXCLUDED.position_qty) > 0 THEN
                            (
                                CASE 
                                    WHEN EXCLUDED.position_qty > 0 THEN bot_portfolios.invested_eur + ABS(EXCLUDED.cash_eur)
                                    ELSE bot_portfolios.invested_eur - (ABS(EXCLUDED.position_qty) / bot_portfolios.position_qty * bot_portfolios.invested_eur)
                                END
                            ) / (bot_portfolios.position_qty + EXCLUDED.position_qty)
                        ELSE 0
                    END
                ),
                updated_at = NOW();
        """)
        
        await self.session.execute(query_portfolio, {
            "user_id": user_id, "bot_id": bot_id, "symbol": symbol,
            "cash_delta": cash_delta, "qty_delta": qty_delta
        })

    # ==========================
    # BOT CONFIG CRUD
    # ==========================
    async def create_bot_config(self, payload: dict) -> int:
        query = text("""
            INSERT INTO bot_configs (
                user_id, name, strategy_id, mode, risk_profile, cadence,
                budget_total_eur, budget_daily_limit_eur, budget_min_order_eur,
                budget_max_order_eur, max_asset_exposure_pct, base_currency, symbol, created_at, updated_at
            )
            VALUES (:user_id, :name, :strategy_id, :mode, :risk_profile, :cadence,
                    :budget_total_eur, :budget_daily_limit_eur, :budget_min_order_eur,
                    :budget_max_order_eur, :max_asset_exposure_pct, :base_currency, :symbol, NOW(), NOW())
            RETURNING id
        """)
        result = await self.session.execute(query, payload)
        return result.fetchone()[0]

    async def update_bot_config(self, user_id: int, bot_id: int, updates: dict) -> Optional[int]:
        if not updates:
            return None
            
        set_clauses = []
        for key in updates.keys():
            set_clauses.append(f"{key} = COALESCE(:{key}, {key})")
            
        set_clauses.append("updated_at = NOW()")
        query_str = f"UPDATE bot_configs SET {', '.join(set_clauses)} WHERE id = :_id AND user_id = :_uid RETURNING id"
        
        params = updates.copy()
        params["_id"] = bot_id
        params["_uid"] = user_id
        
        query = text(query_str)
        result = await self.session.execute(query, params)
        row = result.fetchone()
        return row[0] if row else None

    async def delete_bot_config(self, user_id: int, bot_id: int) -> int:
        query = text("DELETE FROM bot_configs WHERE id = :id AND user_id = :user_id RETURNING id")
        result = await self.session.execute(query, {"id": bot_id, "user_id": user_id})
        row = result.fetchone()
        return row[0] if row else None

    # ==========================
    # DECISION SKIPPING
    # ==========================
    async def mark_decision_skipped(self, user_id: int, bot_id: int, report_date: date) -> Optional[int]:
        query = text("""
            UPDATE bot_decisions
            SET status='skipped', updated_at=NOW()
            WHERE user_id=:user_id AND bot_id=:bot_id AND decision_date=:report_date AND status='planned'
            RETURNING id
        """)
        result = await self.session.execute(query, {"user_id": user_id, "bot_id": bot_id, "report_date": report_date})
        row = result.fetchone()
        return row[0] if row else None

    async def cancel_orders_for_decision(self, user_id: int, bot_id: int, decision_id: int):
        if not await self.check_table_exists("bot_orders"):
            return
        query = text("""
            UPDATE bot_orders
            SET status='cancelled', updated_at=NOW()
            WHERE user_id=:user_id AND bot_id=:bot_id AND decision_id=:decision_id
        """)
        await self.session.execute(query, {"user_id": user_id, "bot_id": bot_id, "decision_id": decision_id})

    # ==========================
    # BOT PORTFOLIOS
    # ==========================
    async def get_bot_portfolios_base(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT
              id, name, is_active, is_live, mode, COALESCE(risk_profile,'balanced') as risk_profile,
              COALESCE(budget_total_eur,0) as budget_total_eur, COALESCE(budget_daily_limit_eur,0) as budget_daily_limit_eur,
              COALESCE(budget_min_order_eur,0) as budget_min_order_eur, COALESCE(budget_max_order_eur,0) as budget_max_order_eur,
              COALESCE(base_currency, 'EUR') as base_currency
            FROM bot_configs
            WHERE user_id=:user_id
            ORDER BY id ASC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_bot_ledger_stats(self, user_id: int, bot_id: int, today: date) -> dict:
        # 1. Total stats (Invested)
        query1 = text("""
            SELECT
              COALESCE(SUM(cash_delta_eur),0) as net_cash,
              COALESCE(SUM(qty_delta),0) as net_qty
            FROM bot_ledger
            WHERE user_id=:user_id AND bot_id=:bot_id
        """)
        res1 = await self.session.execute(query1, {"user_id": user_id, "bot_id": bot_id})
        row1 = res1.fetchone()

        # 2. Executed cash (Invested cost basis)
        query2 = text("""
            SELECT COALESCE(SUM(cash_delta_eur),0)
            FROM bot_ledger
            WHERE user_id=:user_id AND bot_id=:bot_id AND entry_type='execute'
        """)
        res2 = await self.session.execute(query2, {"user_id": user_id, "bot_id": bot_id})
        row2 = res2.fetchone()

        # 3. Today spent (Daily consumption)
        query3 = text("""
            SELECT COALESCE(SUM(ABS(cash_delta_eur)), 0)
            FROM bot_ledger
            WHERE user_id=:user_id AND bot_id=:bot_id
              AND DATE(ts) = :today
              AND entry_type = 'execute'
              AND cash_delta_eur < 0
        """)
        res3 = await self.session.execute(query3, {"user_id": user_id, "bot_id": bot_id, "today": today})
        row3 = res3.fetchone()

        # 4. Today reserved (Pending consumption)
        query4 = text("""
            SELECT COALESCE(SUM(ABS(cash_delta_eur)), 0)
            FROM bot_ledger
            WHERE user_id=:user_id AND bot_id=:bot_id
              AND DATE(ts) = :today
              AND entry_type = 'reserve'
              AND cash_delta_eur < 0
        """)
        res4 = await self.session.execute(query4, {"user_id": user_id, "bot_id": bot_id, "today": today})
        row4 = res4.fetchone()

        return {
            "net_cash": float(row1[0] or 0),
            "net_qty": float(row1[1] or 0),
            "executed_cash": float(row2[0] or 0),
            "today_spent": float(row3[0] or 0),
            "today_reserved": float(row4[0] or 0)
        }

    async def get_market_price(self, symbol: str) -> Optional[float]:
        query = text("""
            SELECT price FROM market_data WHERE symbol=:symbol ORDER BY timestamp DESC LIMIT 1
        """)
        result = await self.session.execute(query, {"symbol": symbol})
        row = result.fetchone()
        return float(row[0]) if row and row[0] else None

    # ==========================
    # BOT TRADES
    # ==========================
    async def get_bot_trades(self, user_id: int, bot_id: int, limit: int) -> List[dict]:
        if not await self.check_table_exists("bot_executions") or not await self.check_table_exists("bot_orders"):
            return []
        query = text("""
            SELECT
              e.id AS execution_id, o.id AS order_id, o.symbol, o.side,
              e.filled_qty, e.avg_fill_price, o.quote_amount_eur, e.status, e.created_at
            FROM bot_executions e
            JOIN bot_orders o ON o.id = e.bot_order_id
            WHERE e.user_id = :user_id AND o.bot_id = :bot_id AND e.status IN ('filled', 'partial')
            ORDER BY e.created_at DESC
            LIMIT :limit
        """)
        result = await self.session.execute(query, {"user_id": user_id, "bot_id": bot_id, "limit": limit})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_bot_decision(self, user_id: int, decision_id: int) -> bool:
        query = text("""
            SELECT 1 FROM bot_decisions WHERE id=:id AND user_id=:user_id
        """)
        result = await self.session.execute(query, {"id": decision_id, "user_id": user_id})
        return result.fetchone() is not None

    async def upsert_bot_trade_plan(self, user_id: int, decision_id: int, entry_plan: list, stop_loss: dict, targets: list, risk: dict):
        query = text("""
            INSERT INTO bot_trade_plans (
                user_id, decision_id, entry_plan, stop_loss, targets, risk_json, created_at, updated_at
            )
            VALUES (:user_id,:decision_id,:entry_plan,:stop_loss,:targets,:risk,NOW(),NOW())
            ON CONFLICT (decision_id) DO UPDATE SET
                entry_plan = EXCLUDED.entry_plan,
                stop_loss  = EXCLUDED.stop_loss,
                targets    = EXCLUDED.targets,
                risk_json  = EXCLUDED.risk_json,
                updated_at = NOW()
            RETURNING decision_id
        """)
        await self.session.execute(query, {
            "user_id": user_id, "decision_id": decision_id,
            "entry_plan": json.dumps(entry_plan), "stop_loss": json.dumps(stop_loss),
            "targets": json.dumps(targets), "risk": json.dumps(risk)
        })

    # ==========================
    # BOT BALANCE HISTORY
    # ==========================
    async def get_portfolio_balance_history(self, user_id: int, bucket: str, limit: int) -> List[dict]:
        if not await self.check_table_exists("portfolio_balance_snapshots"):
            return []
        query = text("""
            SELECT ts, equity_eur, cash_eur, btc_qty, btc_value_eur, invested_eur, unrealized_pnl_eur
            FROM portfolio_balance_snapshots
            WHERE user_id = :user_id AND bucket = :bucket
            ORDER BY ts ASC LIMIT :limit
        """)
        result = await self.session.execute(query, {"user_id": user_id, "bucket": bucket, "limit": limit})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_bot_balance_history(self, user_id: int, bot_id: int, bucket: str, limit: int) -> List[dict]:
        if not await self.check_table_exists("bot_portfolio_snapshots"):
            return []
        query = text("""
            SELECT ts, equity_eur, cash_eur, net_qty, price_eur, invested_eur
            FROM bot_portfolio_snapshots
            WHERE user_id = :user_id AND bot_id = :bot_id AND bucket = :bucket
            ORDER BY ts ASC LIMIT :limit
        """)
        result = await self.session.execute(query, {"user_id": user_id, "bot_id": bot_id, "bucket": bucket, "limit": limit})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_filtered_portfolio_balance_history(self, user_id: int, is_live: bool, bucket: str, limit: int) -> List[dict]:
        if not await self.check_table_exists("bot_portfolio_snapshots"):
            return []
        
        # We aggregate all snapshots for bots matching the is_live filter
        query = text("""
            SELECT 
                s.ts,
                SUM(s.equity_eur) as equity_eur,
                SUM(s.cash_eur) as cash_eur,
                SUM(s.net_qty) as btc_qty,
                AVG(s.price_eur) as price_eur, -- price should be similar across bots at same ts
                SUM(s.invested_eur) as invested_eur
            FROM bot_portfolio_snapshots s
            JOIN bot_configs b ON b.id = s.bot_id
            WHERE s.user_id = :user_id AND b.is_live = :is_live AND s.bucket = :bucket
            GROUP BY s.ts
            ORDER BY s.ts ASC
            LIMIT :limit
        """)
        result = await self.session.execute(query, {"user_id": user_id, "is_live": is_live, "bucket": bucket, "limit": limit})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_portfolio_intelligence_context(self, user_id: int) -> Dict[str, Any]:
        """
        Calculates and returns real-time cash, equity, asset allocations, 
        and detailed performance metrics for all bot portfolios.
        """
        query = text("""
            SELECT 
                c.id AS bot_id, 
                c.name, 
                COALESCE(p.symbol, st.symbol, 'BTC') AS symbol, 
                COALESCE(p.cash_eur, 0) AS cash_eur, 
                COALESCE(p.position_qty, 0) AS position_qty, 
                COALESCE(p.invested_eur, 0) AS invested_eur, 
                COALESCE(p.avg_entry, 0) AS avg_entry, 
                COALESCE(p.realized_pnl_eur, 0) AS realized_pnl_eur,
                c.is_active, 
                c.is_live,
                COALESCE(c.budget_total_eur, 0) AS budget_total_eur,
                COALESCE(c.budget_daily_limit_eur, 0) AS budget_daily_limit_eur,
                COALESCE(c.risk_profile, 'balanced') AS risk_profile
            FROM bot_configs c
            LEFT JOIN bot_portfolios p ON p.bot_id = c.id
            LEFT JOIN strategies s     ON s.id = c.strategy_id
            LEFT JOIN setups st        ON st.id = s.setup_id
            WHERE c.user_id = :user_id
            ORDER BY c.id ASC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        rows = result.fetchall()
        
        # Get unique symbols and retrieve their live market prices
        symbols = list(set(row._mapping["symbol"] for row in rows))
        prices = {}
        for sym in symbols:
            prices[sym] = await self.get_market_price(sym) or 0.0
            
        bot_states = []
        global_cash = 0.0
        global_invested = 0.0
        global_realized = 0.0
        global_position_value = 0.0
        global_budget = 0.0
        asset_values = {}
        
        for r in rows:
            mapping = r._mapping
            bot_id = mapping["bot_id"]
            name = mapping["name"]
            sym = mapping["symbol"]
            cash = float(mapping["cash_eur"])
            qty = float(mapping["position_qty"])
            invested = float(mapping["invested_eur"])
            avg_entry = float(mapping["avg_entry"])
            realized = float(mapping["realized_pnl_eur"])
            budget = float(mapping["budget_total_eur"])
            is_active = bool(mapping["is_active"])
            is_live = bool(mapping["is_live"])
            risk = mapping["risk_profile"]
            
            price = prices.get(sym, 0.0)
            pos_val = qty * price
            unrealized = pos_val - invested
            bot_equity = cash + pos_val
            
            global_cash += cash
            global_invested += invested
            global_realized += realized
            global_position_value += pos_val
            global_budget += budget
            
            asset_values[sym] = asset_values.get(sym, 0.0) + pos_val
            
            bot_states.append({
                "bot_id": bot_id,
                "name": name,
                "symbol": sym,
                "cash": cash,
                "qty": qty,
                "invested": invested,
                "avg_entry": avg_entry,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
                "position_value": pos_val,
                "equity": bot_equity,
                "budget_total": budget,
                "is_active": is_active,
                "is_live": is_live,
                "risk_profile": risk
            })
            
        global_equity = global_cash + global_position_value
        global_unrealized = global_position_value - global_invested
        
        allocations = {}
        if global_equity > 0:
            allocations["Cash"] = round((global_cash / global_equity) * 100, 2)
            for sym, val in asset_values.items():
                allocations[sym] = round((val / global_equity) * 100, 2)
        else:
            allocations["Cash"] = 100.0
            
        return {
            "global": {
                "total_equity": global_equity,
                "cash_balance": global_cash,
                "invested_value": global_invested,
                "current_position_value": global_position_value,
                "realized_pnl": global_realized,
                "unrealized_pnl": global_unrealized,
                "total_budget_limit": global_budget,
                "allocations_pct": allocations
            },
            "bots": bot_states
        }

    async def get_user_behavioral_signals(self, user_id: int) -> Dict[str, Any]:
        """
        Calculates user's real-time custom configuration metrics in a single query
        to measure their trading experience level behaviorally.
        """
        query = text("""
            SELECT 
                (SELECT COUNT(*) FROM setups WHERE user_id = :user_id) as setups_count,
                (SELECT COUNT(*) FROM strategies WHERE user_id = :user_id) as strategies_count,
                (SELECT COUNT(*) FROM bot_configs WHERE user_id = :user_id) as bots_count
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        row = result.fetchone()
        
        setups = int(row[0] or 0)
        strategies = int(row[1] or 0)
        bots = int(row[2] or 0)
        total_actions = setups + strategies + bots
        
        # Determine behavioral level based on custom configurations
        if total_actions == 0:
            behavioral_level = "Novice (Uses default templates exclusively)"
        elif 1 <= total_actions <= 3:
            behavioral_level = "Intermediate (Has configured some custom setups, strategies or bots)"
        else:
            behavioral_level = "Experienced (Active usage of custom configurations and trading bots)"
            
        return {
            "setups_count": setups,
            "strategies_count": strategies,
            "bots_count": bots,
            "total_custom_configs": total_actions,
            "behavioral_level": behavioral_level
        }


