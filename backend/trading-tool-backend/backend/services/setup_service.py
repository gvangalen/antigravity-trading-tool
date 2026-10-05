from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException
from datetime import datetime

from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.onboarding_repository import OnboardingRepository
from backend.schemas.trading_schema import SetupCreateSchema

WEEKDAY_TO_NUMBER = {
    "1": 1,
    "monday": 1,
    "maandag": 1,
    "2": 2,
    "tuesday": 2,
    "dinsdag": 2,
    "3": 3,
    "wednesday": 3,
    "woensdag": 3,
    "4": 4,
    "thursday": 4,
    "donderdag": 4,
    "5": 5,
    "friday": 5,
    "vrijdag": 5,
    "6": 6,
    "saturday": 6,
    "zaterdag": 6,
    "7": 7,
    "sunday": 7,
    "zondag": 7,
}

class SetupService:
    # These are product defaults for a setup created without explicit score
    # ranges (for example the compact onboarding form).  The backend owns
    # them so different frontend surfaces cannot silently diverge.
    SETUP_SCORE_DEFAULTS = {
        "min_macro_score": 30,
        "max_macro_score": 70,
        "min_technical_score": 40,
        "max_technical_score": 80,
        "min_market_score": 20,
        "max_market_score": 60,
    }
    # The domain service, not FINN, owns which persisted setup fields can be
    # changed. V2 adapters pass a typed proposal through this same boundary.
    UPDATE_ALLOWED_FIELDS = frozenset({
        "name", "symbol", "timeframe", "setup_type", "dca_frequency",
        "dca_day", "dca_month_day", "account_type", "min_investment",
        "trend", "score_logic", "favorite", "description", "action",
        "category", "min_macro_score", "max_macro_score",
        "min_technical_score", "max_technical_score", "min_market_score",
        "max_market_score", "explanation", "tags",
    })
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = SetupRepository(db_session)

    def _default_timeframe_for_setup_type(self, setup_type: Any) -> str:
        normalized_type = str(setup_type or "").strip().lower()
        return "1W" if normalized_type == "dca" else "4H"

    def _normalize_dca_day(self, value: Any) -> str:
        if value is None or value == "":
            raise ValueError()
        key = str(value).strip().lower()
        day = WEEKDAY_TO_NUMBER.get(key)
        if day is None:
            day = int(value)
        if day < 1 or day > 7:
            raise ValueError()
        return str(day)

    def _normalize_dca_month_day(self, value: Any) -> int:
        if value is None or value == "":
            raise ValueError()
        month_day = int(value)
        if month_day < 1 or month_day > 31:
            raise ValueError()
        return month_day

    def normalize_dca_fields(self, raw_payload: dict) -> None:
        setup_type = str(raw_payload.get("setup_type") or "").lower()
        dca_freq = str(raw_payload.get("dca_frequency") or "").lower()

        if setup_type != "dca":
            raw_payload["dca_frequency"] = None
            raw_payload["dca_day"] = None
            raw_payload["dca_month_day"] = None
            return

        if "dca_frequency" in raw_payload and raw_payload.get("dca_frequency") is not None:
            raw_payload["dca_frequency"] = dca_freq

        if dca_freq == "weekly":
            dca_day = raw_payload.get("dca_day")
            if dca_day is not None:
                try:
                    raw_payload["dca_day"] = self._normalize_dca_day(dca_day)
                except (ValueError, TypeError):
                    raise HTTPException(400, "dca_day moet een getal tussen 1 (maandag) en 7 (zondag) zijn voor wekelijkse DCA.")
            raw_payload["dca_month_day"] = None
        elif dca_freq == "monthly":
            dca_month_day = raw_payload.get("dca_month_day")
            if dca_month_day is not None:
                try:
                    raw_payload["dca_month_day"] = self._normalize_dca_month_day(dca_month_day)
                except (ValueError, TypeError):
                    raise HTTPException(400, "dca_month_day moet een getal tussen 1 en 31 zijn voor maandelijkse DCA.")
            raw_payload["dca_day"] = None
        elif dca_freq == "daily":
            raw_payload["dca_day"] = None
            raw_payload["dca_month_day"] = None

    def _format_setup(self, item: dict) -> dict:
        if not item:
            return None
            
        created_at = item.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        return {
            "id": item.get("id"),
            # `setup_id` is the public cross-surface identifier. Keep `id`
            # during the compatibility period for list and detail consumers.
            "setup_id": item.get("id"),
            "name": item.get("name"),
            "symbol": item.get("symbol"),
            "timeframe": item.get("timeframe"),
            "setup_type": item.get("setup_type"),
            
            "dca_frequency": item.get("dca_frequency"),
            "dca_day": item.get("dca_day"),
            "dca_month_day": item.get("dca_month_day"),
            
            "account_type": item.get("account_type"),
            "min_investment": item.get("min_investment"),
            "tags": item.get("tags") or [],
            "trend": item.get("trend"),
            "score_logic": item.get("score_logic"),
            "favorite": bool(item.get("favorite")),
            "explanation": item.get("explanation"),
            "description": item.get("description"),
            "action": item.get("action"),
            "category": item.get("category"),
            
            "min_macro_score": item.get("min_macro_score"),
            "max_macro_score": item.get("max_macro_score"),
            "min_technical_score": item.get("min_technical_score"),
            "max_technical_score": item.get("max_technical_score"),
            "min_market_score": item.get("min_market_score"),
            "max_market_score": item.get("max_market_score"),
            
            "created_at": created_at,
            "user_id": item.get("user_id"),
        }

    async def _mark_setup_step_completed_best_effort(self, user_id: int) -> None:
        """
        Setup saves should never wait on the full onboarding status recomputation.
        We only mark the setup step as completed and swallow any non-critical issue.
        """
        try:
            repo = OnboardingRepository(self.session)
            await repo.mark_step_completed(user_id, "default", "setup")
        except Exception:
            # Best-effort only: the user-facing save response must not fail on onboarding bookkeeping.
            return

    def validate_setup_payload(self, raw_payload: dict, is_update: bool = False):
        """
        Validates a setup payload meticulously for logical consistency, correct ranges,
        and missing fields. Raises an HTTPException(400) with descriptive messages.
        """
        self.normalize_dca_fields(raw_payload)

        if "description" in raw_payload:
            description = raw_payload["description"]
            if description is not None and not isinstance(description, str):
                raise HTTPException(400, "Setup-toelichting moet tekst zijn.")
            if isinstance(description, str):
                description = description.strip()
                if len(description) > 1000:
                    raise HTTPException(400, "Setup-toelichting mag maximaal 1000 tekens bevatten.")
                raw_payload["description"] = description or None

        # 1. Non-empty string validations for name and symbol
        if not is_update or "name" in raw_payload:
            name = raw_payload.get("name")
            if not name or not isinstance(name, str) or not name.strip():
                raise HTTPException(400, "Naam is verplicht en mag niet leeg zijn.")
            if len(name) > 80:
                raise HTTPException(400, "Naam mag maximaal 80 karakters lang zijn.")

        if not is_update or "symbol" in raw_payload:
            symbol = raw_payload.get("symbol")
            if not symbol or not isinstance(symbol, str) or not symbol.strip():
                raise HTTPException(400, "Symbool is verplicht.")
            if len(symbol) < 2 or len(symbol) > 10:
                raise HTTPException(400, "Symbool moet tussen 2 en 10 karakters lang zijn.")
            if not symbol.strip().replace("-", "").isalnum():
                raise HTTPException(400, "Symbool mag alleen letters, cijfers of '-' bevatten.")

        if not is_update or "timeframe" in raw_payload:
            timeframe = raw_payload.get("timeframe")
            if timeframe is not None:
                allowed_timeframes = {
                    "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M",
                    "1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W",
                }
                if not isinstance(timeframe, str) or timeframe.strip() not in allowed_timeframes:
                    raise HTTPException(400, "Ongeldige timeframe.")

        # 2. Setup type validation
        setup_type = raw_payload.get("setup_type")
        if not is_update or "setup_type" in raw_payload:
            if not setup_type or not isinstance(setup_type, str) or setup_type.lower() not in ["dca", "trade", "position"]:
                raise HTTPException(400, "Ongeldig setup_type. Moet 'dca', 'trade' of 'position' zijn.")
            setup_type = setup_type.lower()

        # 3. DCA validations
        if setup_type == "dca":
            dca_freq = raw_payload.get("dca_frequency")
            if not dca_freq or not isinstance(dca_freq, str) or dca_freq.lower() not in ["daily", "weekly", "monthly"]:
                raise HTTPException(400, "dca_frequency is verplicht voor DCA setup en moet 'daily', 'weekly' of 'monthly' zijn.")
            
            # Check weekly day
            if dca_freq.lower() == "weekly":
                dca_day = raw_payload.get("dca_day")
                if dca_day is not None:
                    try:
                        dca_day_int = int(dca_day)
                        if dca_day_int < 1 or dca_day_int > 7:
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise HTTPException(400, "dca_day moet een getal tussen 1 (maandag) en 7 (zondag) zijn voor wekelijkse DCA.")

            # Check monthly day
            if dca_freq.lower() == "monthly":
                dca_m_day = raw_payload.get("dca_month_day")
                if dca_m_day is not None:
                    try:
                        dca_m_day_int = int(dca_m_day)
                        if dca_m_day_int < 1 or dca_m_day_int > 31:
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise HTTPException(400, "dca_month_day moet een getal tussen 1 en 31 zijn voor maandelijkse DCA.")

        # 4. Score Limit range validations
        for cat in ["macro", "technical", "market"]:
            mn = raw_payload.get(f"min_{cat}_score")
            mx = raw_payload.get(f"max_{cat}_score")
            
            if mn is not None:
                try:
                    mn_val = float(mn)
                    if mn_val < 0 or mn_val > 100:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise HTTPException(400, f"min_{cat}_score moet een getal tussen 0 en 100 zijn.")
            
            if mx is not None:
                try:
                    mx_val = float(mx)
                    if mx_val < 0 or mx_val > 100:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise HTTPException(400, f"max_{cat}_score moet een getal tussen 0 en 100 zijn.")

            if mn is not None and mx is not None:
                if float(mn) > float(mx):
                    raise HTTPException(400, f"min_{cat}_score mag niet hoger zijn dan max_{cat}_score.")

        # 5. Min investment validation
        min_invest = raw_payload.get("min_investment")
        if min_invest is not None:
            try:
                min_invest_val = float(min_invest)
                if min_invest_val < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400, "min_investment mag niet negatief zijn.")

    async def save_setup(self, payload: SetupCreateSchema, raw_payload: dict, user_id: int,
                         *, commit: bool = True) -> dict:
        defaulted_score_fields = []
        for field, value in self.SETUP_SCORE_DEFAULTS.items():
            if raw_payload.get(field) is None:
                raw_payload[field] = value
                defaulted_score_fields.append(field)
        if not raw_payload.get("timeframe"):
            raw_payload["timeframe"] = self._default_timeframe_for_setup_type(raw_payload.get("setup_type"))

        # Validate utilizing our robust payload validator
        self.validate_setup_payload(raw_payload, is_update=False)

        # Normalize uppercase symbol
        raw_payload["symbol"] = str(raw_payload.get("symbol", "")).strip().upper()
        payload.symbol = raw_payload["symbol"]

        setup_type = payload.setup_type.lower()

        exists = await self.repository.check_name_exists(payload.name, user_id)
        if exists:
            raise HTTPException(409, "Setup met deze naam bestaat al")

        tags = raw_payload.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        raw_payload["name"] = payload.name
        raw_payload["setup_type"] = setup_type

        # Use the raw dict directly because of the hybrid strategy
        setup_id = await self.repository.create_setup(raw_payload, user_id, tags)
        if commit:
            await self.session.commit()
            await self._mark_setup_step_completed_best_effort(user_id)

        created = await self.repository.get_setup_by_id(setup_id, user_id)
        return {
            "status": "success",
            "setup_id": setup_id,
            "setup": self._format_setup(created),
            "field_sources": {
                field: "default" if field in defaulted_score_fields else "supplied"
                for field in self.SETUP_SCORE_DEFAULTS
            },
        }

    async def get_last_setup(self, user_id: int, setup_id: Optional[int] = None) -> dict:
        if setup_id:
            row = await self.repository.get_setup_by_id(setup_id, user_id)
        else:
            row = await self.repository.get_last_setup(user_id)
        
        return {"setup": self._format_setup(row) if row else None}

    async def get_setups(self, user_id: int, setup_type: Optional[str] = None) -> List[dict]:
        rows = await self.repository.get_all_setups(user_id, setup_type)
        return [self._format_setup(r) for r in rows]

    async def get_dca_setups(self, user_id: int) -> List[dict]:
        rows = await self.repository.get_dca_setups(user_id)
        return [self._format_setup(r) for r in rows]

    async def get_market_matches(self, user_id: int, symbol: str | None = None) -> List[dict]:
        from backend.services.setup_market_match_service import SetupMarketMatchService

        service = SetupMarketMatchService(self.session)
        if not symbol:
            return (await service.for_all_assets(user_id))["matches"]
        assessment = await service.for_asset(user_id, symbol)
        return [{**match, "as_of": assessment["as_of"],
                 "source_status": assessment["source_status"]} for match in assessment["matches"]]

    async def update_setup(self, setup_id: int, raw_payload: dict, user_id: int) -> dict:
        row = await self.repository.get_setup_by_id(setup_id, user_id)
        if not row:
            raise HTTPException(403, "Geen toegang tot setup")

        unknown_fields = set(raw_payload).difference(self.UPDATE_ALLOWED_FIELDS)
        if unknown_fields:
            raise HTTPException(400, f"Niet-toegestane setupvelden: {', '.join(sorted(unknown_fields))}")

        # Merge raw_payload with existing row to perform cross-field validations (e.g. min/max scores)
        merged_payload = dict(row)
        for k, v in raw_payload.items():
            merged_payload[k] = v

        self.validate_setup_payload(merged_payload, is_update=True)
        if "description" in raw_payload:
            raw_payload["description"] = merged_payload["description"]
        for field in ("setup_type", "dca_frequency", "dca_day", "dca_month_day"):
            if field in raw_payload and field in merged_payload:
                raw_payload[field] = merged_payload[field]

        # Normalize uppercase symbol if being updated
        if "symbol" in raw_payload:
            raw_payload["symbol"] = str(raw_payload["symbol"]).strip().upper()

        updates = {}
        for field in self.UPDATE_ALLOWED_FIELDS.difference({"tags"}):
            if field in raw_payload:
                updates[field] = raw_payload[field]

        if "tags" in raw_payload:
            tags = raw_payload["tags"]
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            updates["tags"] = tags

        # Cleanup DCA fields if setup type is changed to Trade
        if updates.get("setup_type") in {"trade", "position"}:
            updates["dca_frequency"] = None
            updates["dca_day"] = None
            updates["dca_month_day"] = None

        updates["last_validated"] = datetime.utcnow()

        updated_count = await self.repository.update_setup_safe(setup_id, user_id, updates)
        if updated_count == 0:
            raise HTTPException(404, "Kon setup niet updaten")
            
        await self.session.commit()
        await self._mark_setup_step_completed_best_effort(user_id)
        updated = await self.repository.get_setup_by_id(setup_id, user_id)
        return {"message": "Setup bijgewerkt", "setup": self._format_setup(updated)}

    async def delete_setup(self, setup_id: int, user_id: int) -> dict:
        dependents = await self.session.execute(
            text("""
                SELECT s.name
                FROM strategies s
                WHERE s.setup_id = :setup_id AND s.user_id = :user_id
                ORDER BY s.created_at ASC, s.id ASC
            """),
            {"setup_id": setup_id, "user_id": user_id},
        )
        dependent_names = [str(name).strip() for name in dependents.scalars().all() if str(name or "").strip()]
        if dependent_names:
            names = ", ".join(f"‘{name}’" for name in dependent_names)
            raise HTTPException(
                409,
                f"Deze setup is nog gekoppeld aan strategie {names}. Verwijder eerst de gekoppelde strategie.",
            )

        deleted = await self.repository.delete_setup(setup_id, user_id)
        if deleted == 0:
            raise HTTPException(404, "Niet gevonden of geen toegang")
        await self.session.commit()
        await self._mark_setup_step_completed_best_effort(user_id)
        return {"message": "Setup verwijderd"}

    async def check_name(self, name: str, user_id: int) -> dict:
        exists = await self.repository.simple_check_name(name, user_id)
        return {"exists": exists}

    async def get_top_setups(self, user_id: int, limit: int) -> List[dict]:
        rows = await self.repository.get_top_setups(user_id, limit)
        return [self._format_setup(r) for r in rows]

    async def get_setup_by_id(self, setup_id: int, user_id: int) -> dict:
        row = await self.repository.get_setup_by_id(setup_id, user_id)
        if not row:
            raise HTTPException(404, "Setup niet gevonden")
        return self._format_setup(row)

    async def get_active_setup(self, user_id: int, symbol: str = "BTC") -> dict:
        from backend.services.setup_market_match_service import SetupMarketMatchService

        assessment = await SetupMarketMatchService(self.session).for_asset(
            user_id, symbol, setups=await self.repository.get_all_setups(user_id)
        )
        best = next((match for match in assessment["matches"] if match["is_best"]), None)
        if best is None:
            return {"active": None, "source_status": assessment["source_status"], "as_of": assessment["as_of"]}
        return {
            "active": {**best, "ai_explanation": "Berekend uit de opgeslagen scorevoorwaarden."},
            "source_status": assessment["source_status"],
            "as_of": assessment["as_of"],
        }

    async def explain_setup_status(self, setup_id: int, user_id: int) -> dict:
        from backend.services.setup_market_match_service import SetupMarketMatchService

        setup = await self.get_setup_by_id(setup_id, user_id)
        assessment = await SetupMarketMatchService(self.session).for_asset(user_id, setup["symbol"], setups=[setup])
        match = assessment["matches"][0]
        return {
            "status": match["status"],
            "match_percentage": match["score"],
            "reasons": match["reasons"],
            "advice": "Bekijk de instap- en risicovoorwaarden afzonderlijk." if match["is_active"] else "Wacht op passende en actuele gegevens.",
            "current_scores": {key: value["score"] for key, value in match["components"].items()},
            "as_of": assessment["as_of"],
            "source_status": assessment["source_status"],
        }
