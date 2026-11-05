import asyncio
import json

from backend.services.admin_user_service import AdminUserService


def test_user_usage_returns_only_aggregate_categories():
    secret = "private FINN conversation about my savings"
    statements = []

    class Result:
        def __init__(self, rows=None, value=None):
            self.rows = rows or []
            self.value = value

        def scalar(self):
            return self.value

        def mappings(self):
            return self

        def all(self):
            return self.rows

    class Session:
        async def execute(self, statement, params):
            statements.append((str(statement), params))
            if "FROM users" in str(statement):
                return Result(value=42)
            return Result(rows=[{
                "feature": "finn_chat", "source": "live_user", "today": True,
                "requests": 2, "input_tokens": 120, "output_tokens": 80,
                "cost_eur": "0.003500", "prompt_text": secret,
            }])

    result = asyncio.run(AdminUserService(Session()).get_user_usage(42))

    assert result["requests_month"] == 2
    assert result["requests_today"] == 2
    assert result["input_tokens_month"] == 120
    assert result["cost_month_eur"] == 0.0035
    assert result["by_feature"] == [{
        "category": "finn_chat", "requests": 2, "input_tokens": 120,
        "output_tokens": 80, "cost_eur": 0.0035,
    }]
    assert secret not in json.dumps(result)
    assert all("message" not in sql and "prompt_text" not in sql for sql, _ in statements)
    assert all(params == {"user_id": 42} for _, params in statements)


def test_user_usage_missing_user():
    class Result:
        def scalar(self):
            return None

    class Session:
        async def execute(self, statement, params):
            return Result()

    assert asyncio.run(AdminUserService(Session()).get_user_usage(999)) is None
