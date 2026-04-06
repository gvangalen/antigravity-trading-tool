from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Date, ForeignKey, text, JSON
from datetime import datetime

from backend.infrastructure.database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    first_name = Column(String)
    last_name = Column(String)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class OnboardingStep(Base):
    __tablename__ = 'onboarding_steps'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    flow = Column(String, nullable=False)
    step_key = Column(String, nullable=False)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    pipeline_started = Column(Boolean, default=False)
    step_metadata = Column("metadata", JSON) # metadata is reserved word sometimes, map column to metadata



class Indicator(Base):
    __tablename__ = 'indicators'

    name = Column(String, primary_key=True)
    display_name = Column(String)
    category = Column(String)
    source = Column(String)
    link = Column(String)
    active = Column(Boolean, default=True)

class MarketData(Base):
    __tablename__ = 'market_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    price = Column(Numeric)
    open = Column(Numeric)
    high = Column(Numeric)
    low = Column(Numeric)
    change_24h = Column(Numeric)
    volume = Column(Numeric)
    is_updated = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class MarketDataIndicator(Base):
    __tablename__ = 'market_data_indicators'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    value = Column(Numeric)
    trend = Column(String)
    interpretation = Column(String)
    action = Column(String)
    score = Column(Numeric)
    user_id = Column(Integer, nullable=True) # UUID via clerk/nextauth o.i.d.
    timestamp = Column(DateTime, default=datetime.utcnow)

class MarketIndicatorRule(Base):
    """Regels voor het scoren van market indicators (zowel GLOBAAL als per USER)"""
    __tablename__ = 'market_indicator_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(String, nullable=False)
    range_min = Column(Numeric)
    range_max = Column(Numeric)
    score = Column(Numeric)
    trend = Column(String)
    interpretation = Column(String)
    action = Column(String)
    score_mode = Column(String, default='standard')
    weight = Column(Numeric, default=1.0)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, nullable=True)

class MacroData(Base):
    __tablename__ = 'macro_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    value = Column(Numeric)
    trend = Column(String)
    interpretation = Column(String)
    action = Column(String)
    score = Column(Numeric)
    user_id = Column(Integer, nullable=True) # UUID via clerk/nextauth o.i.d.
    timestamp = Column(DateTime, default=datetime.utcnow)

class MacroIndicatorRule(Base):
    """Regels voor het scoren van macro indicators"""
    __tablename__ = 'macro_indicator_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(String, nullable=False)
    range_min = Column(Numeric)
    range_max = Column(Numeric)
    score = Column(Numeric)
    trend = Column(String)
    interpretation = Column(String)
    action = Column(String)
    score_mode = Column(String, default='standard')
    weight = Column(Numeric, default=1.0)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, nullable=True)

class TechnicalDataIndicator(Base):
    __tablename__ = 'technical_indicators'

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(String, nullable=False)
    value = Column(Numeric)
    score = Column(Numeric)
    advies = Column(String)
    uitleg = Column(String)
    user_id = Column(Integer, nullable=True) # UUID via clerk/nextauth o.i.d.
    timestamp = Column(DateTime, default=datetime.utcnow)

class TechnicalIndicatorRule(Base):
    """Regels voor het scoren van technical indicators"""
    __tablename__ = 'technical_indicator_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(String, nullable=False)
    range_min = Column(Numeric)
    range_max = Column(Numeric)
    score = Column(Numeric)
    trend = Column(String)
    interpretation = Column(String)
    action = Column(String)
    score_mode = Column(String, default='standard')
    weight = Column(Numeric, default=1.0)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, nullable=True)

class MarketData7D(Base):
    __tablename__ = 'market_data_7d'

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Numeric)
    high = Column(Numeric)
    low = Column(Numeric)
    close = Column(Numeric)
    change = Column(Numeric)
    volume = Column(Numeric)
    created_at = Column(DateTime, default=datetime.utcnow)

class MarketForwardReturn(Base):
    __tablename__ = 'market_forward_returns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    period = Column(String, nullable=False)  # e.g., '7d', '30d'
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    change = Column(Numeric)
    avg_daily = Column(Numeric)
    created_at = Column(DateTime, default=datetime.utcnow)

class Setup(Base):
    __tablename__ = 'setups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    name = Column(String, nullable=False)
    symbol = Column(String)
    timeframe = Column(String)
    explanation = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class DailySetupScore(Base):
    __tablename__ = 'daily_setup_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    setup_id = Column(Integer, ForeignKey('setups.id', ondelete='CASCADE'))
    report_date = Column(Date, nullable=False)
    score = Column(Numeric)
    active = Column(Boolean)
    breakdown = Column(JSON)

class DailyScore(Base):
    __tablename__ = 'daily_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    report_date = Column(Date, nullable=False)
    macro_score = Column(Numeric)
    technical_score = Column(Numeric)
    market_score = Column(Numeric)
    setup_score = Column(Numeric)

class AiCategoryInsight(Base):
    __tablename__ = 'ai_category_insights'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    category = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    avg_score = Column(Numeric)
    trend = Column(String)
    bias = Column(String)
    risk = Column(String)
    summary = Column(String)
    top_signals = Column(JSON)
