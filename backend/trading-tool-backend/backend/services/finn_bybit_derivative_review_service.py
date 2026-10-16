"""User-attested Bybit derivative episodes from exact private execution evidence."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.services.finn_bybit_derivative_service import (
    DERIVATIVE_CATEGORIES, closed_episodes,
)
from backend.services.finn_trade_review_rollout import require_trade_review_access


MAX_STREAM_EXECUTIONS = 10_000
MAX_EVIDENCE_WINDOW = 2 * MAX_STREAM_EXECUTIONS
MAX_FALLBACK_STARTS = 250
CONFIRMATION_TEXT = (
    "Ik bevestig dat de gekozen Bybit-uitvoeringen samen één volledig afgesloten "
    "derivatentrade vormen. Ontbrekende historie, financiering en andere kosten "
    "kunnen het accountresultaat beïnvloeden."
)


def _episode_key(source_id: int, episode: dict) -> str:
    payload = {"version": 1, "source_id": source_id,
               "category": episode["category"], "symbol": episode["symbol"],
               "position_idx": episode["position_idx"],
               "slices": [(part["execution_id"], part["role"], str(part["qty"]))
                          for part in episode["slices"]]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FinnBybitDerivativeReviewService:
    def __init__(self, session):
        self.session = session

    async def _candidates(self, user_id: int, source_id: int, category: str,
                          *, symbol: str | None = None, position_idx: int | None = None,
                          before_at=None, before_id: int | None = None) -> tuple[list[dict], dict]:
        require_trade_review_access(user_id)
        if category not in DERIVATIVE_CATEGORIES or (position_idx is not None and position_idx not in {0, 1, 2}):
            raise HTTPException(422, "Ongeldige Bybit-positie")
        owner = await self.session.execute(text("""
            SELECT 1 FROM finn_bybit_derivative_cursors c
            JOIN finn_exchange_import_sources s
              ON s.id=c.source_id AND s.user_id=c.user_id
            WHERE c.user_id=:user_id AND c.source_id=:source_id
              AND c.category=:category AND s.exchange_name='bybit'
              AND s.identity_kind='provider_uid'
        """), {"user_id": user_id, "source_id": source_id, "category": category})
        if owner.fetchone() is None:
            raise HTTPException(404, "Bybit-derivatenimport niet gevonden")
        if symbol is not None and (not symbol.isascii() or not symbol.isalnum() or len(symbol) > 40):
            raise HTTPException(422, "Ongeldig Bybit-contract")
        if (before_at is None) != (before_id is None) or (
                before_at is not None and (before_at.tzinfo is None or before_id <= 0)):
            raise HTTPException(422, "Ongeldige oudere bewijspositie")
        rows = await self.session.execute(text("""
            SELECT id, category, symbol, base_currency, quote_currency, settle_currency,
                   contract_size, exec_id, order_id, exec_type, side, qty, price,
                   execution_value, fee_amount, fee_currency, closed_size, seq,
                   traded_at, evidence_status, position_idx
            FROM finn_bybit_derivative_executions
            WHERE user_id=:user_id AND source_id=:source_id AND category=:category
              AND (CAST(:symbol AS TEXT) IS NULL OR symbol=:symbol)
              AND (CAST(:position_idx AS INTEGER) IS NULL OR position_idx=:position_idx
                   OR evidence_status<>'trade_order_resolved')
              AND (CAST(:before_at AS TIMESTAMPTZ) IS NULL
                   OR (traded_at,id)<(CAST(:before_at AS TIMESTAMPTZ),CAST(:before_id AS BIGINT)))
            ORDER BY traded_at DESC, id DESC LIMIT :row_limit
        """), {"user_id": user_id, "source_id": source_id, "category": category,
               "symbol": symbol, "position_idx": position_idx,
               "before_at": before_at, "before_id": before_id,
               "row_limit": MAX_EVIDENCE_WINDOW + 1})
        evidence = [dict(row._mapping) for row in rows.fetchall()]
        history_truncated = len(evidence) > MAX_EVIDENCE_WINDOW
        if history_truncated:
            evidence = evidence[:MAX_EVIDENCE_WINDOW]
        # Advance by half a window. The next page repeats the older half, so
        # an episode spanning one boundary and at most half a window of fills
        # can still be reconstructed as a complete user-attestable episode.
        boundary = evidence[MAX_STREAM_EXECUTIONS - 1] if history_truncated else None
        next_evidence_before = ({"before_at": boundary["traded_at"],
                                 "before_id": int(boundary["id"])}
                                if boundary else None)
        evidence.reverse()
        gaps = [row for row in evidence if row["evidence_status"] != "trade_order_resolved"]
        grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for row in evidence:
            if row["evidence_status"] == "trade_order_resolved":
                grouped[(row["symbol"], row["position_idx"])].append(row)
        candidates: list[dict] = []
        for (contract, idx), stream in grouped.items():
            by_execution = {int(row["id"]): row for row in stream}
            try:
                episodes, _ = closed_episodes(stream)
            except ValueError:
                # A leading pre-window position or later corrupt row must not
                # erase a valid *user-attestable* suffix. Never call it
                # provider-proven; bound the search to avoid quadratic abuse.
                episodes = []
                seen_slices = set()
                starts = [i for i, row in enumerate(stream)
                          if row.get("closed_size") in (None, 0)][-MAX_FALLBACK_STARTS:]
                for start in starts:
                    try:
                        found, _ = closed_episodes(stream[start:], stop_after_first=True)
                    except ValueError:
                        continue
                    if found:
                        signature = tuple((part["execution_id"], part["role"], str(part["qty"]))
                                          for part in found[0]["slices"])
                        if signature not in seen_slices:
                            episodes.append(found[0])
                            seen_slices.add(signature)
            for episode in episodes:
                if any(row["symbol"] == contract and
                       episode["entry_at"] <= row["traded_at"] <= episode["exit_at"]
                       for row in gaps):
                    continue
                key = _episode_key(source_id, episode)
                preview = []
                for part in episode["slices"]:
                    execution = by_execution[int(part["execution_id"])]
                    preview.append({"execution_id": int(execution["id"]),
                                    "exec_id": execution["exec_id"],
                                    "order_id": execution["order_id"],
                                    "role": part["role"], "side": execution["side"],
                                    "allocated_qty": str(part["qty"]),
                                    "raw_exec_qty": str(execution["qty"]),
                                    "price_quote": str(execution["price"]),
                                    "quote_currency": execution["quote_currency"],
                                    "settle_currency": execution["settle_currency"],
                                    "fee_amount_raw_execution": (
                                        str(execution["fee_amount"])
                                        if execution["fee_amount"] is not None else None),
                                    "fee_currency": execution["fee_currency"],
                                    "position_idx": idx,
                                    "evidence_status": execution["evidence_status"],
                                    "at": execution["traded_at"]})
                candidates.append({**episode, "episode_key": key,
                                   "source_id": source_id,
                                   "execution_preview": preview,
                                   "evidence_status": "user_attestation_required",
                                   "native_pnl_status": "unavailable",
                                   "evidence_page_before": ({"before_at": before_at,
                                                            "before_id": before_id}
                                                            if before_at is not None else None),
                                   "history_truncated": history_truncated,
                                   "coverage_note": (
                                       "Dit bewijsvenster overlapt met de volgende pagina; episodes met meer dan 10.000 uitvoeringen kunnen ontbreken. Controleer en bevestig de volledige afsluiting"
                                       if history_truncated else
                                       "Afsluiting en nulbasis vereisen gebruikersbevestiging")})
        return (sorted(candidates, key=lambda item: (item["exit_at"], item["episode_key"]), reverse=True),
                {"has_older_evidence": history_truncated,
                 "next_evidence_before": next_evidence_before})

    async def candidates(self, user_id: int, source_id: int, category: str,
                         *, symbol: str | None = None, position_idx: int | None = None,
                         limit: int = 50, offset: int = 0,
                         before_at=None, before_id: int | None = None) -> dict:
        if not 1 <= limit <= 50 or not 0 <= offset <= 10_000:
            raise HTTPException(422, "Ongeldige paginering")
        items, page = await self._candidates(user_id, source_id, category,
                                             symbol=symbol, position_idx=position_idx,
                                             before_at=before_at, before_id=before_id)
        review_rows = await self.session.execute(text("""
            SELECT episode_digest,review_id FROM finn_bybit_derivative_review_attestations
            WHERE user_id=:user_id AND source_id=:source_id AND category=:category
        """), {"user_id": user_id, "source_id": source_id, "category": category})
        reviewed = {row.episode_digest: int(row.review_id) for row in review_rows.fetchall()}
        for item in items:
            item["review_id"] = reviewed.get(item["episode_key"])
        return {"items": items[offset:offset + limit], "total": len(items),
                "source_id": source_id, "category": category,
                "status": ("user_attestation_required" if items else
                           "older_evidence_available" if page["has_older_evidence"] else
                           "no_reconstructable_episode"), **page}

    async def create(self, user_id: int, *, source_id: int, category: str, symbol: str,
                     position_idx: int, episode_key: str, closure_confirmed: bool,
                     idempotency_key: UUID, before_at=None,
                     before_id: int | None = None) -> dict:
        require_trade_review_access(user_id)
        if not closure_confirmed:
            raise HTTPException(422, "Bevestig eerst dat de volledige derivatentrade gesloten is")
        if len(episode_key) != 64 or any(ch not in "0123456789abcdef" for ch in episode_key):
            raise HTTPException(422, "Ongeldige episode")
        try:
            await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id,741076)"),
                                       {"user_id": user_id})
            replay = await self.session.execute(text("""
                SELECT review_id,episode_digest FROM finn_bybit_derivative_review_attestations
                WHERE user_id=:user_id AND idempotency_key=:idempotency_key
            """), {"user_id": user_id, "idempotency_key": str(idempotency_key)})
            prior = replay.fetchone()
            if prior is not None:
                if prior.episode_digest != episode_key:
                    raise HTTPException(409, "Idempotentiesleutel hoort bij een andere episode")
                await self.session.commit()
                return {"review_id": int(prior.review_id), "created": False,
                        "origin": "bybit_derivative_user_attested"}
            candidates, _ = await self._candidates(user_id, source_id, category,
                                                    symbol=symbol, position_idx=position_idx,
                                                    before_at=before_at, before_id=before_id)
            episode = next((item for item in candidates if item["episode_key"] == episode_key), None)
            if episode is None:
                raise HTTPException(404, "Gesloten Bybit-episode niet gevonden")
            allocation_by_execution: dict[int, Decimal] = defaultdict(Decimal)
            for part in episode["slices"]:
                allocation_by_execution[int(part["execution_id"])] += Decimal(part["qty"])
            existing = await self.session.execute(text("""
                SELECT execution_id,COALESCE(SUM(qty),0) AS used_qty
                FROM finn_bybit_derivative_review_allocations
                WHERE user_id=:user_id AND execution_id=ANY(CAST(:execution_ids AS BIGINT[]))
                GROUP BY execution_id
            """), {"user_id": user_id, "execution_ids": list(allocation_by_execution)})
            reserved = {int(row.execution_id): Decimal(row.used_qty) for row in existing.fetchall()}
            raw = await self.session.execute(text("""
                SELECT e.id,e.qty,e.price,e.side,e.exec_id,e.order_id,e.fee_amount,
                       e.fee_currency,e.settle_currency,e.base_currency,e.quote_currency,e.traded_at,
                       e.contract_size
                FROM finn_bybit_derivative_executions e
                WHERE e.user_id=:user_id AND e.source_id=:source_id AND e.category=:category
                  AND e.id=ANY(CAST(:execution_ids AS BIGINT[]))
            """), {"user_id": user_id, "source_id": source_id, "category": category,
                   "execution_ids": list(allocation_by_execution)})
            executions = {int(row.id): dict(row._mapping) for row in raw.fetchall()}
            if len(executions) != len(allocation_by_execution) or any(
                    reserved.get(eid, Decimal(0)) + qty > Decimal(executions[eid]["qty"])
                    for eid, qty in allocation_by_execution.items()):
                raise HTTPException(409, "Een Bybit-uitvoering is al volledig aan een review gekoppeld")
            bot_overlap = await self.session.execute(text("""
                SELECT 1 FROM bot_orders o
                WHERE o.user_id=:user_id AND LOWER(o.exchange_name)='bybit'
                  AND o.exchange_order_id=ANY(CAST(:order_ids AS TEXT[]))
                LIMIT 1
            """), {"user_id": user_id,
                   "order_ids": sorted({str(row["order_id"]) for row in executions.values()})})
            if bot_overlap.fetchone() is not None:
                raise HTTPException(409, "Bybit-uitvoering hoort mogelijk bij een Tradamind-order")
            fills = []
            for part in episode["slices"]:
                row = executions[int(part["execution_id"])]
                fills.append({"derivative_execution_id": int(row["id"]),
                              "exec_id": row["exec_id"], "order_id": row["order_id"],
                              "role": part["role"], "qty": str(part["qty"]),
                              "raw_exec_qty": str(row["qty"]), "side": row["side"],
                              "price_quote": str(row["price"]),
                              "quote_currency": row["quote_currency"],
                              "settle_currency": row["settle_currency"],
                              "fee_amount_raw_execution": str(row["fee_amount"]) if row["fee_amount"] is not None else None,
                              "fee_currency": row["fee_currency"],
                              "at": row["traded_at"].isoformat(),
                              "position_idx": position_idx, "category": category})
            fees_complete = all(allocation_by_execution[eid] == Decimal(row["qty"])
                                and row["fee_amount"] is not None and row["fee_currency"]
                                for eid, row in executions.items())
            fee_legs = defaultdict(Decimal)
            if fees_complete:
                for row in executions.values():
                    fee_legs[row["fee_currency"]] += Decimal(row["fee_amount"])
            fee_legs_json = [{"currency": currency, "amount": str(value)}
                             for currency, value in sorted(fee_legs.items())]
            first = executions[int(episode["slices"][0]["execution_id"])]
            entry_qty = sum((Decimal(part["qty"]) for part in episode["slices"]
                             if part["role"] == "open"), Decimal(0))
            inserted = await self.session.execute(text("""
                INSERT INTO finn_trade_reviews
                    (user_id,bot_id,symbol,execution_environment,execution_sources,
                     opening_ledger_id,closing_ledger_id,entry_at,exit_at,entry_qty,
                     entry_value_eur,exit_value_eur,entry_price_eur,exit_price_eur,
                     pnl_eur_before_fees,plan_snapshot,fills,origin,closure_basis,
                     base_currency,pnl_status,cash_legs_by_currency,exchange_name,
                     attested_at,attestation_source_ids,candles_status,candles_reason,
                     derivative_category,position_idx,direction,settle_currency,
                     native_pnl,native_pnl_status,fee_legs_by_currency)
                VALUES (:user_id,NULL,:symbol,'live','["direct_exchange_derivative"]'::jsonb,
                        NULL,NULL,:entry_at,:exit_at,:entry_qty,
                        NULL,NULL,NULL,NULL,NULL,NULL,CAST(:fills AS JSONB),
                        'bybit_derivative_user_attested','user_confirmed',:base_currency,
                        'not_comparable','[]'::jsonb,'bybit',NOW(),CAST(:source_ids AS JSONB),
                        'unavailable','Derivatenuitvoeringen zijn geen marktprijs-candles',
                        :category,:position_idx,:direction,:settle_currency,
                        NULL,'unavailable',CAST(:fee_legs AS JSONB)) RETURNING id
            """), {"user_id": user_id, "symbol": symbol,
                   "entry_at": episode["entry_at"], "exit_at": episode["exit_at"],
                   "entry_qty": entry_qty, "fills": json.dumps(fills),
                   "base_currency": first["base_currency"] or symbol,
                   "source_ids": json.dumps([source_id]),
                   "category": category, "position_idx": position_idx,
                   "direction": episode["direction"],
                   "settle_currency": first["settle_currency"],
                   "fee_legs": json.dumps(fee_legs_json)})
            review_id = int(inserted.scalar_one())
            for part in episode["slices"]:
                await self.session.execute(text("""
                    INSERT INTO finn_bybit_derivative_review_allocations
                        (user_id,execution_id,review_id,role,qty)
                    VALUES (:user_id,:execution_id,:review_id,:role,:qty)
                """), {"user_id": user_id, "execution_id": part["execution_id"],
                       "review_id": review_id, "role": part["role"], "qty": part["qty"]})
            await self.session.execute(text("""
                INSERT INTO finn_bybit_derivative_review_attestations
                    (user_id,idempotency_key,episode_digest,review_id,source_id,category,
                     symbol,position_idx,closure_confirmed,confirmation_text)
                VALUES (:user_id,:idempotency_key,:episode_key,:review_id,:source_id,
                        :category,:symbol,:position_idx,TRUE,:confirmation_text)
            """), {"user_id": user_id, "idempotency_key": str(idempotency_key),
                   "episode_key": episode_key, "review_id": review_id,
                   "source_id": source_id, "category": category, "symbol": symbol,
                   "position_idx": position_idx, "confirmation_text": CONFIRMATION_TEXT})
            await self.session.commit()
            return {"review_id": review_id, "created": True,
                    "origin": "bybit_derivative_user_attested",
                    "native_pnl_status": "unavailable", "fee_status": (
                        "complete_raw_execution" if fees_complete else "partial_or_unallocated")}
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, "Bybit-episode is al gekoppeld") from None
        except Exception:
            await self.session.rollback()
            raise
