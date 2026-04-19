import logging

logger = logging.getLogger(__name__)

# Prices per 1,000,000 tokens (USD)
# Source: https://openai.com/api/pricing/
PRICING = {
    "gpt-4o": {
        "input": 2.50,
        "output": 10.00
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60
    }
}

# Estimated exchange rate USD -> EUR
USD_TO_EUR = 0.93

def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Berekent de geschatte kosten voor een AI call in Euro's.
    """
    # Fallback op mini pricing als model onbekend is
    price_data = PRICING.get(model, PRICING["gpt-4o-mini"])
    
    input_cost = (prompt_tokens / 1_000_000) * price_data["input"]
    output_cost = (completion_tokens / 1_000_000) * price_data["output"]
    
    total_usd = input_cost + output_cost
    total_eur = total_usd * USD_TO_EUR
    
    return round(total_eur, 6)
