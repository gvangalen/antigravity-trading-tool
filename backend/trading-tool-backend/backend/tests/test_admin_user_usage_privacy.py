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
                "unpriced_requests": 1,
                "cost_eur": "0.003500", "prompt_text": secret,
            }])

    result = asyncio.run(AdminUserService(Session()).get_user_usage(42))

    assert result["requests_month"] == 2
    assert result["requests_today"] == 2
    assert result["input_tokens_month"] == 120
    assert result["cost_month_eur"] == 0.0035
    assert result["unpriced_requests_month"] == 1
    assert result["by_feature"] == [{
        "category": "finn_chat", "requests": 2, "input_tokens": 120,
        "output_tokens": 80, "cost_eur": 0.0035,
    }]
    assert secret not in json.dumps(result)
    assert all("message" not in sql and "prompt_text" not in sql for sql, _ in statements)
    assert all(params == {"user_id": 42} for _, params in statements)


def test_admin_user_page_separates_login_web_activity_and_background_ai():
    from datetime import datetime, timezone

    stamp = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    row = {
        "id": 7, "email": "example@example.com", "first_name": None,
        "last_name": None, "role": "user", "is_active": True,
        "ai_plan": "basis", "ai_requests_used_day": 0, "ai_requests_limit_day": 25,
        "ai_usage_current": 0, "subscription_status": "active",
        "last_login_at": stamp, "created_at": stamp,
        "usage_month_eur": 0, "usage_today_eur": 0,
        "background_usage_month_eur": 0, "interactive_usage_month_eur": 0,
        "blocked_requests_month": 0, "blocked_estimated_cost_month_eur": 0,
        "unpriced_requests_month": 2, "last_ai_activity_at": stamp,
        "last_interactive_ai_at": None, "last_background_ai_at": stamp,
        "last_other_ai_at": None,
        "last_app_activity_at": None, "active_days_30d": 0,
    }
    statements = []

    class Result:
        def __init__(self, value=None, rows=None):
            self.value = value
            self.rows = rows or []

        def scalar(self):
            return self.value

        def mappings(self):
            return self

        def all(self):
            return self.rows

    class Session:
        async def execute(self, statement, params):
            statements.append(str(statement))
            return Result(value=1) if len(statements) == 1 else Result(rows=[row])

    result = asyncio.run(AdminUserService(Session()).get_users_page(limit=1))

    assert result["items"][0]["last_login_at"] == stamp.isoformat()
    assert result["items"][0]["last_app_activity_at"] is None
    assert result["items"][0]["last_background_ai_at"] == stamp.isoformat()
    assert result["items"][0]["unpriced_requests_month"] == 2
    assert "event_name = 'app_activity'" in statements[1]
    assert "surface = 'web'" in statements[1]


def test_user_usage_missing_user():
    class Result:
        def scalar(self):
            return None

    class Session:
        async def execute(self, statement, params):
            return Result()

    assert asyncio.run(AdminUserService(Session()).get_user_usage(999)) is None
