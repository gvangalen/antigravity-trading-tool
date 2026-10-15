import ccxt.async_support as ccxt
import logging
import asyncio
import math
import time
from typing import Dict, Any, Optional, List
from backend.utils.encryption_utils import EncryptionUtils

logger = logging.getLogger(__name__)

class ExchangeService:
    @staticmethod
    def verified_eur_ticker_price(ticker: Dict[str, Any], asset: str, max_age_seconds: int = 300) -> float:
        if not isinstance(ticker, dict):
            raise ValueError("Missing exchange ticker")
        pair = str(ticker.get("symbol") or "").strip().upper().replace("-", "/")
        if pair != f"{str(asset or '').strip().upper()}/EUR":
            raise ValueError("Exchange ticker is not the expected spot EUR pair")
        last = float(ticker.get("last") or 0)
        bid = float(ticker.get("bid") or 0)
        ask = float(ticker.get("ask") or 0)
        if not all(math.isfinite(value) and value > 0 for value in (last, bid, ask)):
            raise ValueError("Invalid exchange quote")
        midpoint = (bid + ask) / 2
        if bid > ask or (ask - bid) / midpoint > 0.05 or abs(last - midpoint) / midpoint > 0.05:
            raise ValueError("Exchange quote is too wide or inconsistent")
        timestamp = ticker.get("timestamp")
        if timestamp is not None:
            age_seconds = time.time() - float(timestamp) / 1000
            if not math.isfinite(age_seconds) or age_seconds < -60 or age_seconds > max_age_seconds:
                raise ValueError("Exchange quote is stale")
        return last

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
        except Exception:
            logger.error("Exchange balance fetch failed on %s", client.id)
            raise
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
        except Exception:
            logger.error("Exchange trading fee fetch failed on %s", client.id)
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
        except Exception:
            logger.error("Exchange ticker fetch failed on %s", client.id)
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
        except Exception:
            logger.error("Exchange positions fetch failed on %s", client.id)
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
        except Exception:
            logger.error("Exchange order submission failed on %s", client.id)
            raise
        finally:
            await client.close()

    @staticmethod
    async def fetch_order(client: Any, order_id: str, symbol: str) -> Dict[str, Any]:
        try:
            ccxt_symbol = symbol if '-' in symbol or '/' in symbol else f"{symbol}/EUR"
            return await client.fetch_order(order_id, ccxt_symbol)
        finally:
            await client.close()
