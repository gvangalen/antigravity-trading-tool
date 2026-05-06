import asyncio
import httpx
from datetime import datetime, timedelta, timezone

async def test():
    symbol = "SOLUSDT"
    all_prices = []
    
    # We want ~6 years of data (approx 2190 days). 
    # Binance gives max 1000 per request.
    # Let's do 3 requests backwards.
    
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=1000&endTime={end_time}"
            res = await client.get(url)
            if res.status_code != 200:
                print(f"Error: {res.status_code}")
                break
            klines = res.json()
            if not klines:
                break
                
            # kline format:
            # [
            #   [
            #     1499040000000,      // [0] Kline open time
            #     "0.01634790",       // [1] Open price
            #     "0.80000000",       // [2] High price
            #     "0.01575800",       // [3] Low price
            #     "0.01577100",       // [4] Close price
            #     ...
            #   ]
            # ]
            
            # Prepend to all_prices because we are going backwards
            # But klines themselves are chronological (oldest to newest within the chunk)
            chunk_prices = []
            for k in klines:
                ts = k[0]
                close_price = float(k[4])
                chunk_prices.append((ts, close_price))
                
            all_prices = chunk_prices + all_prices
            
            # Next end_time is the open time of the first kline in this chunk minus 1 ms
            first_kline_time = klines[0][0]
            end_time = first_kline_time - 1
            
            # If we got less than 1000, we've hit the beginning of the coin's history
            if len(klines) < 1000:
                break

    print(f"Total days fetched: {len(all_prices)}")
    if all_prices:
        first_date = datetime.fromtimestamp(all_prices[0][0]/1000, timezone.utc).date()
        last_date = datetime.fromtimestamp(all_prices[-1][0]/1000, timezone.utc).date()
        print(f"History from {first_date} to {last_date}")

asyncio.run(test())
