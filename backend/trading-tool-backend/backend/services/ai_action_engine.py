import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete

from backend.infrastructure.models import AiPendingAction, Watchlist
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.setup_service import SetupService
from backend.services.strategy_service import StrategyService
from backend.services.bot_service import BotService

from backend.schemas.trading_schema import SetupCreateSchema, StrategyCreateSchema
from backend.schemas.bot_schema import BotConfigCreateSchema

logger = logging.getLogger(__name__)

class AiActionEngine:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.user_repo = UserRepository(db_session)
        self.setup_service = SetupService(db_session)
        self.strategy_service = StrategyService(db_session)
        self.bot_service = BotService(db_session)

    async def register_pending_action(
        self, 
        user_id: int, 
        action_type: str, 
        payload: Dict[str, Any], 
        trace_id: Optional[str] = None, 
        ttl_seconds: int = 600
    ) -> str:
        """
        Registers a proposed action in the database with status 'pending' and returns a unique action_id.
        """
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(seconds=ttl_seconds)

        new_action = AiPendingAction(
            id=action_id,
            user_id=user_id,
            type=action_type,
            payload=payload,
            status="pending",
            created_at=created_at,
            expires_at=expires_at,
            trace_id=trace_id
        )

        self.session.add(new_action)
        await self.session.commit()
        logger.info(f"⏳ Registered pending human-in-the-loop action: {action_id} [Type: {action_type}, User: {user_id}]")
        return action_id

    async def execute_pending_action(self, action_id: str, user_id: int) -> Dict[str, Any]:
        """
        Retrieves, validates, and executes a registered pending action.
        Evaluates the Human-in-the-Loop levels before dispatching execution.
        """
        # Fetch pending action
        stmt = select(AiPendingAction).where(
            and_(AiPendingAction.id == action_id, AiPendingAction.user_id == user_id)
        )
        res = await self.session.execute(stmt)
        action_record = res.scalars().first()

        if not action_record:
            logger.warning(f"🚨 Pending action not found or unauthorized: {action_id} for user {user_id}")
            raise HTTPException(status_code=404, detail="Gevraagde actie niet gevonden of niet geautoriseerd.")

        if action_record.status != "pending":
            logger.warning(f"🚨 Attempted to execute action {action_id} with status: {action_record.status}")
            raise HTTPException(status_code=400, detail=f"Deze actie is al verwerkt (status: {action_record.status}).")

        # Check expiration
        if datetime.utcnow() > action_record.expires_at:
            action_record.status = "expired"
            await self.session.commit()
            logger.warning(f"🚨 Action {action_id} has expired.")
            raise HTTPException(status_code=400, detail="Deze goedkeuringstoken is verlopen. Vraag FINN opnieuw om dit in te stellen.")

        action_type = action_record.type
        payload = action_record.payload or {}
        result_data = {}

        try:
            # --------------------------------------------------------
            # LEVEL 1 & 2 & 3: ACTION ROUTING & EXECUTION
            # --------------------------------------------------------
            if action_type in ["watchlist_add", "add_to_watchlist"]:
                symbol = payload.get("symbol", "").upper()
                if not symbol:
                    raise HTTPException(status_code=400, detail="Geen asset symbool opgegeven in payload.")

                # Check if already exists in watchlist
                exists_stmt = select(Watchlist).where(
                    and_(Watchlist.user_id == user_id, Watchlist.symbol == symbol)
                )
                exists_res = await self.session.execute(exists_stmt)
                if exists_res.scalars().first():
                    result_data = {"message": f"{symbol} staat al in je watchlist."}
                else:
                    new_item = Watchlist(user_id=user_id, symbol=symbol)
                    self.session.add(new_item)
                    result_data = {"message": f"{symbol} succesvol toegevoegd aan je watchlist.", "symbol": symbol}

            elif action_type in ["watchlist_remove", "remove_from_watchlist"]:
                symbol = payload.get("symbol", "").upper()
                if not symbol:
                    raise HTTPException(status_code=400, detail="Geen asset symbool opgegeven in payload.")

                del_stmt = delete(Watchlist).where(
                    and_(Watchlist.user_id == user_id, Watchlist.symbol == symbol)
                )
                del_res = await self.session.execute(del_stmt)
                if del_res.rowcount == 0:
                    result_data = {"message": f"{symbol} stond niet in je watchlist."}
                else:
                    result_data = {"message": f"{symbol} succesvol verwijderd uit je watchlist."}

            elif action_type in ["setup_draft", "setup"]:
                # Convert raw payload dict to SetupCreateSchema
                pydantic_payload = SetupCreateSchema(**payload)
                result_data = await self.setup_service.save_setup(pydantic_payload, payload, user_id)

            elif action_type in ["strategy_draft", "strategy"]:
                # Convert raw payload to StrategyCreateSchema
                pydantic_payload = StrategyCreateSchema(**payload)
                result_data = await self.strategy_service.save_strategy(pydantic_payload, payload, user_id)

            elif action_type in ["bot_draft", "bot"]:
                # Convert raw payload to BotConfigCreateSchema
                pydantic_payload = BotConfigCreateSchema(**payload)
                result_data = await self.bot_service.create_bot_config(pydantic_payload, user_id)

            elif action_type in ["delete_bot", "stop_bot"]:
                bot_id = payload.get("bot_id")
                if not bot_id:
                    raise HTTPException(status_code=400, detail="Geen bot_id opgegeven voor delete_bot actie.")
                result_data = await self.bot_service.delete_bot_config(int(bot_id), user_id)

            elif action_type == "risk_profile_change":
                new_profile = payload.get("risk_profile")
                if new_profile not in ["conservative", "balanced", "aggressive"]:
                    raise HTTPException(status_code=400, detail="Ongeldig risicoprofiel opgegeven.")
                await self.user_repo.update_ai_preferences(user_id, {"risk_profile": new_profile})
                result_data = {"message": f"Je risicoprofiel is succesvol aangepast naar {new_profile}."}

            else:
                raise HTTPException(status_code=400, detail=f"Onbekend of niet ondersteund actie-type: {action_type}")

            # Mark action as executed
            action_record.status = "executed"
            await self.session.commit()
            logger.info(f"✅ Successfully executed pending action: {action_id} of type: {action_type} for user: {user_id}")
            return {
                "status": "success",
                "action_id": action_id,
                "type": action_type,
                "result": result_data
            }

        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Error during pending action {action_id} execution: {e}", exc_info=True)
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Interne fout tijdens het uitvoeren van de actie: {str(e)}")
