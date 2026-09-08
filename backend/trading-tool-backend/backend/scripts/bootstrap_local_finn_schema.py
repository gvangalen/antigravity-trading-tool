#!/usr/bin/env python3
"""Create the non-production baseline required by historical FINN migrations."""
from backend.infrastructure.database import Base, sync_engine
from backend.infrastructure import models  # noqa: F401 - register ORM metadata
from sqlalchemy import text


LEGACY_BASELINE = """
ALTER TABLE user_indicator_configs
    ALTER COLUMN config_json TYPE JSONB USING config_json::text::jsonb;
CREATE TABLE IF NOT EXISTS strategies (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), setup_id INTEGER REFERENCES setups(id));
CREATE TABLE IF NOT EXISTS bot_configs (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), strategy_id INTEGER REFERENCES strategies(id), cadence TEXT DEFAULT 'daily', symbol TEXT);
CREATE TABLE IF NOT EXISTS bot_orders (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), decision_id INTEGER, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS bot_executions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), bot_order_id INTEGER REFERENCES bot_orders(id));
CREATE TABLE IF NOT EXISTS bot_ledger (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), order_id INTEGER REFERENCES bot_orders(id), entry_type TEXT);
CREATE TABLE IF NOT EXISTS bot_portfolios (id SERIAL PRIMARY KEY, bot_id INTEGER REFERENCES bot_configs(id), user_id INTEGER REFERENCES users(id), symbol TEXT);
CREATE TABLE IF NOT EXISTS global_market_insights (id SERIAL PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


def main() -> None:
    Base.metadata.create_all(bind=sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(text(LEGACY_BASELINE))


if __name__ == "__main__":
    main()
