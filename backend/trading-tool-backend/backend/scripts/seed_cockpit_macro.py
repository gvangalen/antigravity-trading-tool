import asyncio
import logging
from sqlalchemy import text
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import Indicator, MacroIndicatorRule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MACRO_INDICATORS = [
    {
        "name": "dxy",
        "display_name": "US Dollar Index (DXY)",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/%5EDXY",
        "category": "macro"
    },
    {
        "name": "sp500",
        "display_name": "S&P 500 Index",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX",
        "category": "macro"
    },
    {
        "name": "vix",
        "display_name": "Volatility Index (VIX)",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
        "category": "macro"
    },
    {
        "name": "gold_price",
        "display_name": "Gold Price",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
        "category": "macro"
    },
    {
        "name": "oil_price",
        "display_name": "Crude Oil Price (WTI)",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/CL=F",
        "category": "macro"
    },
    {
        "name": "us10y",
        "display_name": "US 10-Year Yield",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX",
        "category": "macro"
    },
    {
        "name": "us02y",
        "display_name": "US 2-Year Yield",
        "source": "yahoo",
        "link": "https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX",
        "category": "macro"
    },
    {
        "name": "interest_rate",
        "display_name": "Fed Funds Rate",
        "source": "fred",
        "link": "https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key=4377042838ee591d3319082ce739fa42&file_type=json",
        "category": "macro"
    },
    {
        "name": "inflation_rate",
        "display_name": "US CPI (Inflation)",
        "source": "fred",
        "link": "https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key=4377042838ee591d3319082ce739fa42&file_type=json",
        "category": "macro"
    },
    {
        "name": "google_trends",
        "display_name": "Google Trends (BTC)",
        "source": "custom",
        "link": "https://trends.google.com/trends/api/widgetdata/multiline",
        "category": "macro"
    },
    {
        "name": "etf_bitcoin_inflow",
        "display_name": "BTC Spot ETF Inflow",
        "source": "custom",
        "link": "https://api.farside.co.uk/v1/etf/btc/latest",
        "category": "macro"
    }
]

# Scoring rules (Objective, but biased towards "Risk-On" being high score)
DEFAULT_RULES = {
    "dxy": [
        (0, 20, 100, "Bullish", "USD extremely weak", "Buy Assets"),
        (20, 40, 80, "Bullish", "USD weakening", "Accumulate"),
        (40, 60, 50, "Neutral", "USD stability", "Wait"),
        (60, 80, 25, "Bearish", "USD strengthening", "De-risk"),
        (80, 100, 10, "Bearish", "USD extremely strong", "Sell/Wait")
    ],
    "sp500": [
        (0, 20, 10, "Bearish", "Stocks in crash territory", "Avoid"),
        (20, 40, 30, "Bearish", "Stocks weakening", "Reduce exposure"),
        (40, 60, 50, "Neutral", "Stocks sideways", "Wait"),
        (60, 80, 80, "Bullish", "Stocks trending up", "Risk-on"),
        (80, 100, 100, "Bullish", "Stocks at ATH/Strong rally", "Confidence High")
    ],
    "vix": [
        (0, 20, 100, "Bullish", "Complacency/Calm market", "Buy Dip"),
        (20, 40, 70, "Bullish", "Normal volatility", "Steady"),
        (40, 60, 40, "Neutral", "Rising anxiety", "Cautious"),
        (60, 80, 20, "Bearish", "Panic/High volatility", "Hedge"),
        (80, 100, 10, "Bearish", "Extreme Fear/Black Swan", "Protect Capital")
    ],
    "us10y": [
        (0, 20, 100, "Bullish", "Yields dropping/Low", "Liquidity up"),
        (20, 40, 80, "Bullish", "Stable low yields", "Supportive"),
        (40, 60, 50, "Neutral", "Yields at balance", "Watch"),
        (60, 80, 30, "Bearish", "Yields rising fast", "Tightening"),
        (80, 100, 10, "Bearish", "Yields very high", "Bonds over stocks")
    ],
    "gold_price": [
        (0, 20, 20, "Bearish", "Gold crashing (Risk-on?)", "Avoid"),
        (20, 40, 40, "Bearish", "Gold weakening", "Watch"),
        (40, 60, 60, "Bullish", "Gold acting as hedge", "Balanced"),
        (60, 80, 80, "Bullish", "Strong demand for Gold", "Bullish"),
        (80, 100, 100, "Bullish", "Gold leading flight to safety", "Very Strong")
    ],
    "interest_rate": [
        (0, 20, 100, "Bullish", "Rates near zero", "Easy money"),
        (20, 40, 80, "Bullish", "Moderate rates", "Growth phase"),
        (40, 60, 50, "Neutral", "Equilibrium", "Stabilizing"),
        (60, 80, 30, "Bearish", "Rising rates", "Contraction"),
        (80, 100, 10, "Bearish", "Restrictive rates", "Recession risk")
    ],
    "inflation_rate": [
        (0, 20, 80, "Bullish", "Deflation/Stable low CPI", "Supportive"),
        (20, 40, 100, "Bullish", "Soft landing target CPI", "Optimal"),
        (40, 60, 50, "Neutral", "Sticky inflation", "Caution"),
        (60, 80, 25, "Bearish", "High inflation", "Tightening cycle"),
        (80, 100, 10, "Bearish", "Hyperinflation/Uncontrolled", "Crisis mode")
    ]
}

async def main():
    async with async_session_factory() as s:
        # 1. Register/Update Indicators
        for ind in MACRO_INDICATORS:
            existing = await s.get(Indicator, ind["name"])
            if existing:
                existing.display_name = ind["display_name"]
                existing.source = ind["source"]
                existing.link = ind["link"]
                existing.active = True
                logger.info(f"Updated indicator: {ind['name']}")
            else:
                new_ind = Indicator(**ind, active=True)
                s.add(new_ind)
                logger.info(f"Added indicator: {ind['name']}")

        # 2. Seed/Reset Rules
        for ind_name, rules in DEFAULT_RULES.items():
            # Clear existing rules for this indicator (global rules only)
            await s.execute(
                text("DELETE FROM macro_indicator_rules WHERE indicator = :name AND user_id IS NULL"),
                {"name": ind_name}
            )
            
            for rmin, rmax, score, trend, interp, action in rules:
                rule = MacroIndicatorRule(
                    indicator=ind_name,
                    range_min=rmin,
                    range_max=rmax,
                    score=score,
                    trend=trend,
                    interpretation=interp,
                    action=action,
                    score_mode='standard',
                    weight=1.0,
                    is_active=True,
                    user_id=None # Global template
                )
                s.add(rule)
            logger.info(f"Seeded {len(rules)} rules for {ind_name}")

        await s.commit()
        print("✅ Macro Cockpit seeding complete!")

if __name__ == "__main__":
    asyncio.run(main())
