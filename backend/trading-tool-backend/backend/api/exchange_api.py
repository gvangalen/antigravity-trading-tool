import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.exchange_schema import ExchangeKeySchema, ExchangeBalanceResponse, ExchangeStatusResponse
from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.services.exchange_service import ExchangeService
from backend.utils.encryption_utils import EncryptionUtils

router = APIRouter(prefix="/exchange", tags=["Exchange"])
logger = logging.getLogger(__name__)


async def _has_unresolved_live_orders(db: AsyncSession, user_id: int, exchange_name: str) -> bool:
    result = await db.execute(text("""
        SELECT 1 FROM bot_orders
        WHERE user_id=:user_id AND execution_environment='live'
          AND (exchange_name=:exchange_name OR exchange_name IS NULL)
          AND status IN ('ready', 'pending', 'sending', 'sent', 'unknown_exchange_state')
        LIMIT 1
    """), {"user_id": user_id, "exchange_name": exchange_name})
    return result.first() is not None

@router.get("/status", response_model=List[ExchangeStatusResponse])
async def get_exchange_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    keys = await ExchangeRepository(db).get_active_keys(current_user["id"])
    return [
        {"exchange": key.exchange_name, "is_connected": True, "message": None}
        for key in keys
    ]

@router.post("/keys")
async def save_exchange_keys(
    payload: ExchangeKeySchema,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = ExchangeRepository(db)
        await db.execute(text("SELECT pg_advisory_xact_lock(:user_id, 0)"), {"user_id": user_id})
        active_keys = await repo.get_active_keys(user_id)
        if any(key.exchange_name != payload.exchange_name for key in active_keys):
            raise HTTPException(409, "Ontkoppel de huidige exchange voordat je een andere koppelt.")
        if await _has_unresolved_live_orders(db, user_id, payload.exchange_name):
            raise HTTPException(409, "Deze exchange heeft nog een onbevestigde live botorder. Wacht op bevestiging voordat je de sleutels wijzigt.")
        
        # Test connection first before saving
        client = await ExchangeService.get_client(
            payload.exchange_name,
            EncryptionUtils.encrypt(payload.api_key),
            EncryptionUtils.encrypt(payload.api_secret),
            EncryptionUtils.encrypt(payload.api_passphrase) if payload.api_passphrase else None
        )
        
        try:
            await client.fetch_balance()
        except Exception:
            logger.warning("Exchange connection test failed for %s", payload.exchange_name)
            raise HTTPException(status_code=400, detail="Exchange-verbinding mislukt.")
        finally:
            await client.close()

        # Save encrypted keys
        await repo.save_exchange_key(
            user_id,
            payload.exchange_name,
            EncryptionUtils.encrypt(payload.api_key),
            EncryptionUtils.encrypt(payload.api_secret),
            EncryptionUtils.encrypt(payload.api_passphrase) if payload.api_passphrase else None
        )
        
        return {"status": "success", "message": f"✅ {payload.exchange_name} gekoppeld"}
    except HTTPException as he:
        raise he
    except Exception:
        logger.error("Exchange key save failed")
        raise HTTPException(status_code=500, detail="Fout bij opslaan exchange keys")

@router.get("/balances", response_model=List[ExchangeBalanceResponse])
async def get_exchange_balances(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = ExchangeRepository(db)
        keys = await repo.get_active_keys(user_id)
        
        results = []
        for k in keys:
            client = await ExchangeService.get_client(
                k.exchange_name, k.api_key, k.api_secret, k.api_passphrase
            )
            balance = await ExchangeService.fetch_balance(client)
            
            # Simple heuristic for total value (could be expanded)
            total_eur = balance.get('total', {}).get('EUR', 0)
            if total_eur == 0:
                total_eur = balance.get('total', {}).get('USDT', 0) # assume 1:1 for simplicity if no EUR
            
            results.append({
                "exchange": k.exchange_name,
                "total": balance.get('total', {}),
                "free": balance.get('free', {}),
                "used": balance.get('used', {}),
                "total_eur": float(total_eur)
            })
            
        return results
    except Exception:
        logger.error("Exchange balance listing failed")
        raise HTTPException(status_code=500, detail="Fout bij ophalen exchange balans")

@router.delete("/keys/{exchange_name}")
async def delete_exchange_keys(
    exchange_name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        await db.execute(text("SELECT pg_advisory_xact_lock(:user_id, 0)"), {"user_id": user_id})
        if await _has_unresolved_live_orders(db, user_id, exchange_name):
            raise HTTPException(409, "Deze exchange heeft nog een onbevestigde live botorder. Ontkoppelen is nu geblokkeerd.")
        repo = ExchangeRepository(db)
        await repo.delete_exchange_key(user_id, exchange_name)
        return {"status": "success", "message": f"🗑️ {exchange_name} ontkoppeld"}
    except HTTPException:
        raise
    except Exception:
        logger.error("Exchange key deletion failed")
        raise HTTPException(status_code=500, detail="Fout bij verwijderen exchange keys")
