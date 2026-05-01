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
            
        # Bitvavo settings - requires operatorId for orders
        if exchange_name.lower() == 'bitvavo':
            config['options'] = {'operatorId': 1} # Mandatory integer ID for Bitvavo

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
    async def fetch_trading_fees(client: Any, symbol: str) -> Dict[str, Any]:
        """
        Fetches trading fees for a symbol.
        """
        try:
            ccxt_symbol = symbol
            if '-' not in symbol and '/' not in symbol:
                ccxt_symbol = f"{symbol}/EUR"
            
            # Bitvavo/Bybit support fetch_trading_fees
            if hasattr(client, 'fetch_trading_fees'):
                fees = await client.fetch_trading_fees()
                if ccxt_symbol in fees:
                    return fees[ccxt_symbol]
            return {}
        except Exception as e:
            logger.error(f"❌ Error fetching trading fees from {client.id}: {e}")
            return {}
        finally:
            await client.close()

    @staticmethod
    async def fetch_ticker(client: Any, symbol: str) -> Dict[str, Any]:
        """
        Fetches the latest ticker for a symbol.
        """
        try:
            ccxt_symbol = symbol
            if '-' not in symbol and '/' not in symbol:
                ccxt_symbol = f"{symbol}/EUR"
            return await client.fetch_ticker(ccxt_symbol)
        except Exception as e:
            logger.error(f"❌ Error fetching ticker from {client.id}: {e}")
            return {}
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

    @staticmethod
    async def create_order(client: Any, symbol: str, side: str, amount: float, price: float = None, order_type: str = 'market') -> Dict[str, Any]:
        """
        Creates an order on the exchange.
        """
        try:
            # Map symbol if needed (Bitvavo uses BTC-EUR)
            ccxt_symbol = symbol
            if '-' not in symbol and '/' not in symbol:
                ccxt_symbol = f"{symbol}/EUR" # Default to EUR pair

            logger.info(f"🚀 Executing {order_type} {side} order for {amount} {ccxt_symbol} at {price}")
            
            if order_type == 'market':
                order = await client.create_order(ccxt_symbol, 'market', side, amount)
            else:
                order = await client.create_order(ccxt_symbol, 'limit', side, amount, price)
                
            return order
        except Exception as e:
            logger.error(f"❌ Error creating order on {client.id}: {e}")
            raise e
        finally:
            await client.close()
