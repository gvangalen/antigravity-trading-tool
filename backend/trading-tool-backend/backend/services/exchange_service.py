import ccxt.async_support as ccxt
import logging
import asyncio
from typing import Dict, Any, Optional, List
from backend.utils.encryption_utils import EncryptionUtils

logger = logging.getLogger(__name__)

class ExchangeService:
    @staticmethod
    async def get_client(exchange_name: str, api_key: str, api_secret: str, api_passphrase: str = None) -> Any:
        """
        Initializes an async CCXT client for the given exchange.
        """
        try:
            exchange_class = getattr(ccxt, exchange_name.lower())
        except AttributeError:
            raise ValueError(f"❌ Exchange '{exchange_name}' not supported by CCXT")

        config = {
            'apiKey': EncryptionUtils.decrypt(api_key),
            'secret': EncryptionUtils.decrypt(api_secret),
            'enableRateLimit': True,
        }
        
        if api_passphrase:
            config['password'] = EncryptionUtils.decrypt(api_passphrase)

        # Bybit settings
        if exchange_name.lower() == 'bybit':
            config['options'] = {'defaultType': 'spot'}

        client = exchange_class(config)
        return client

    @staticmethod
    async def fetch_balance(client: Any) -> Dict[str, Any]:
        """
        Fetches the total account balance.
        """
        try:
            balance = await client.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"❌ Error fetching balance from {client.id}: {e}")
            raise e
        finally:
            await client.close()

    @staticmethod
    async def fetch_positions(client: Any) -> List[Dict[str, Any]]:
        """
        Fetches active positions.
        """
        try:
            if hasattr(client, 'fetch_positions'):
                return await client.fetch_positions()
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching positions from {client.id}: {e}")
            return []
        finally:
            await client.close()
