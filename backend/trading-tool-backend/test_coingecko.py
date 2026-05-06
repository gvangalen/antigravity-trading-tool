import asyncio
import httpx
from datetime import datetime
from collections import defaultdict

async def test():
    async with httpx.AsyncClient() as client:
        res = await client.get("https://api.coingecko.com/api/v3/coins/solana/ohlc?vs_currency=usd&days=14")
        ohlc = res.json()
        print(f"OHLC 14 days returned {len(ohlc)} rows. First: {ohlc[0]}")
        
        # Test daily grouping
        daily_ohlc = {}
        for row in ohlc:
            ts, o, h, l, c = row
            d = datetime.utcfromtimestamp(ts/1000).date()
            if d not in daily_ohlc:
                daily_ohlc[d] = {"open": o, "high": h, "low": l, "close": c}
            else:
                daily_ohlc[d]["high"] = max(daily_ohlc[d]["high"], h)
                daily_ohlc[d]["low"] = min(daily_ohlc[d]["low"], l)
                daily_ohlc[d]["close"] = c # last close of the day
        print(f"Grouped into {len(daily_ohlc)} days.")
        
        # Test market chart
        res2 = await client.get("https://api.coingecko.com/api/v3/coins/solana/market_chart?vs_currency=usd&days=365")
        chart = res2.json()
        prices = chart.get("prices", [])
        print(f"Market chart returned {len(prices)} prices.")

asyncio.run(test())
