import sys
import os
from sqlalchemy.schema import CreateTable
from sqlalchemy import create_mock_engine

# Voeg project root toe aan path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "trading-tool-backend")))

from backend.infrastructure.database import Base
import backend.infrastructure.models

def dump(sql, *multiparams, **params):
    print(sql.compile(dialect=engine.dialect))

engine = create_mock_engine("postgresql://", dump)

# We willen alleen de SQL voor de nieuwe/relevante tabellen
targets = ["push_subscriptions", "system_logs", "global_macro_data", "global_market_indicators", "global_market_insights", "global_technical_indicators"]

for table_name, table in Base.metadata.tables.items():
    if table_name in targets:
        print(f"\n-- TABLE: {table_name}")
        print(CreateTable(table).compile(dialect=engine.dialect))
        print(";")
