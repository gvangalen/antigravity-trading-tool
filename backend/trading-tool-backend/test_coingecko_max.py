import asyncio
import httpx

async def test():
    async with httpx.AsyncClient() as client:
        res = await client.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=max")
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text[:200]}")

asyncio.run(test())
