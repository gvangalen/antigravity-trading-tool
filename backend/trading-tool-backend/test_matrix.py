import asyncio
import httpx
from datetime import datetime
from collections import defaultdict

async def test():
    async with httpx.AsyncClient() as client:
        res2 = await client.get("https://api.coingecko.com/api/v3/coins/solana/market_chart?vs_currency=usd&days=365")
        chart = res2.json()
        prices = chart.get("prices", [])
        
        # 1. Map to daily prices
        daily_prices = {}
        for ts, price in prices:
            # Use fromtimestamp as suggested
            d = datetime.fromtimestamp(ts/1000, datetime.UTC).date()
            daily_prices[d] = price
            
        sorted_dates = sorted(daily_prices.keys())
        
        # We want to group by:
        # Week: ISO week (year, week)
        # Month: (year, month)
        # Quarter: (year, quarter)
        # Year: year
        
        groups = {
            "7d": defaultdict(list),
            "30d": defaultdict(list),
            "90d": defaultdict(list),
            "365d": defaultdict(list)
        }
        
        for d in sorted_dates:
            p = daily_prices[d]
            iso_year, iso_week, _ = d.isocalendar()
            quarter = (d.month - 1) // 3 + 1
            
            groups["7d"][(iso_year, iso_week)].append((d, p))
            groups["30d"][(d.year, d.month)].append((d, p))
            groups["90d"][(d.year, quarter)].append((d, p))
            groups["365d"][(d.year, 1)].append((d, p))
            
        print("Groups built.")
        
        # For each group, calculate change
        returns = []
        for period, group_data in groups.items():
            for key, items in group_data.items():
                items.sort(key=lambda x: x[0]) # sort by date
                start_d, start_p = items[0]
                end_d, end_p = items[-1]
                if start_p > 0:
                    change = (end_p - start_p) / start_p * 100
                else:
                    change = 0
                returns.append({
                    "period": period,
                    "start_date": datetime(start_d.year, start_d.month, start_d.day),
                    "end_date": datetime(end_d.year, end_d.month, end_d.day),
                    "change": change
                })
        print(f"Calculated {len(returns)} forward returns.")
        print(f"Example 30d: {[r for r in returns if r['period'] == '30d'][:3]}")

asyncio.run(test())
