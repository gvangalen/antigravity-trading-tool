import asyncio
import httpx

async def test():
    symbol = "SOL"
    binance_symbol = f"{symbol}USDT"
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={binance_symbol}"
    
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        print(res.status_code)
        data = res.json()
        print(f"Price: {data.get('lastPrice')}")
        print(f"Change: {data.get('priceChangePercent')}")
        print(f"Volume: {data.get('quoteVolume')}")

asyncio.run(test())
