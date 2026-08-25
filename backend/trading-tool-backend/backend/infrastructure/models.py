from sqlalchemy import BigInteger, Column, Integer, String, Numeric, Boolean, DateTime, Date, ForeignKey, text, JSON, UniqueConstraint
from datetime import datetime

from backend.infrastructure.database import Base

from sqlalchemy.dialects.postgresql import JSONB

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
    subscription_status = Column(String, default="active") # 'active', 'inactive', 'canceled'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # --- Phase 2: AI Quotas & Usage ---
    ai_plan = Column(String, default="basis") # 'free', 'basis', 'pro'
    ai_requests_limit_day = Column(Integer, default=25)
    ai_requests_used_day = Column(Integer, default=0)
    ai_tokens_used_month = Column(Integer, default=0)
    ai_usage_current = Column(Numeric, default=0.00) # Estimated cost in EUR
    ai_monthly_budget = Column(Numeric, default=10.00)
    last_usage_reset = Column(DateTime)

    ai_preferences = Column(JSONB, default=lambda: {
        "report_style": "professional",
        "tone": "balanced",
        "detail_level": "medium",
        "coaching_style": "constructive",
        "experience_level": "beginner",
        "risk_profile": "balanced"
    })


class AuthRefreshSession(Base):
    __tablename__ = "auth_refresh_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    jti = Column(String, unique=True, nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    rotated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String, nullable=True)
    replaced_by_jti = Column(String, nullable=True)


class AuthPasswordResetToken(Base):
    __tablename__ = "auth_password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    locale = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String, nullable=True)

class AiUsageLog(Base):
    __tablename__ = 'ai_usage_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    model = Column(String)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    cost = Column(Numeric(10, 6))
    purpose = Column(String)
    symbol = Column(String)
    status = Column(String) # 'normal', 'short', 'fallback', 'cache'
    response_time_ms = Column(Integer, default=0)
    similarity_score = Column(Numeric(5, 4))
    cache_age_seconds = Column(Integer)
    rejected_reason = Column(String) # low_similarity, context_mismatch, expired, no_match
    estimated_cost_if_full = Column(Numeric(10, 6), default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # --- Phase 3: Enterprise Observability & AI Hardening ---
    trace_id = Column(String, default=None, nullable=True)
    completion_status = Column(String, default="success")
    parser_recovery_triggered = Column(Boolean, default=False)
    confidence_score = Column(Numeric(5, 2), default=None, nullable=True)
    safety_guardrail_triggered = Column(Boolean, default=False)
    request_source = Column(String, default="unclassified")
    app_env = Column(String, nullable=True)
    run_kind = Column(String, nullable=True)
    entry_point = Column(String, nullable=True)
    user_email_snapshot = Column(String, nullable=True)

class AiResponseCache(Base):
    __tablename__ = 'ai_response_cache'
    __table_args__ = (
        UniqueConstraint("query_hash", "symbol", "timeframe", "category", name="ux_ai_response_cache_context"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_hash = Column(String, nullable=False)
    query_text = Column(String)
    normalized_query = Column(String)
    response_json = Column(JSONB)
    original_cost = Column(Numeric(10, 6), default=0.0)
    embedding = Column(JSONB) # Store the vector as JSON
    symbol = Column(String)
    timeframe = Column(String)
    category = Column(String)
    ttl_minutes = Column(Integer, default=60)
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
    symbol = Column(String, default="BTC")
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

class UserIndicatorConfig(Base):
    """
    🎯 SINGLE SOURCE OF TRUTH voor User Indicator Preferences.
    Every FINN-facing preference is asset-scoped.  Historical NULL-symbol rows
    are retained for migration/audit only and are never selected for FINN V2.
    """
    __tablename__ = 'user_indicator_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    indicator = Column(String, nullable=False) # e.g. 'rsi', 'ma200'
    category = Column(String, default='technical') # 'technical', 'macro', 'market'
    symbol = Column(String, nullable=True)
    asset_class = Column(String, nullable=True)
    priority = Column(Integer, default=100)
    enabled = Column(Boolean, default=True)
    config_json = Column(JSON, default=dict, nullable=False)
    provenance = Column(String, default='product_api', nullable=False)
    source_record_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class MacroData(Base):
    __tablename__ = 'macro_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    value = Column(Numeric)
    trend = Column(String)
    interpretation = Column(String)
    action = Column(String)
    score = Column(Numeric)
    symbol = Column(String, default="BTC")
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
    symbol = Column(String, default="BTC")
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
    symbol = Column(String, default="BTC")

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
    symbol = Column(String, default="BTC")

class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemLog(Base):
    __tablename__ = 'system_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, nullable=False) # 'info', 'warning', 'error', 'critical'
    message = Column(String, nullable=False)
    source = Column(String, nullable=False) # 'backend', 'api', 'auth', 'market_data', 'ai', 'db'
    endpoint = Column(String, nullable=True)
    user_id = Column(Integer, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True) # Context: payloads, stack traces, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

class ExchangeKey(Base):
    __tablename__ = 'exchange_keys'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    exchange_name = Column(String, nullable=False) # 'bybit', 'bitvavo'
    api_key = Column(String, nullable=False) # Encrypted
    api_secret = Column(String, nullable=False) # Encrypted
    api_passphrase = Column(String, nullable=True) # Encrypted, optional
    is_active = Column(Boolean, default=True)
    is_live = Column(Boolean, default=False) # False = Simulated/Paper, True = Real Exchange
    created_at = Column(DateTime, default=datetime.utcnow)

class Watchlist(Base):
    """
    ⭐ Assets die de engine dagelijks moet scannen voor de user.
    """
    __tablename__ = 'watchlists'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    symbol = Column(String, nullable=False) # e.g. 'BTC', 'ETH'
    created_at = Column(DateTime, default=datetime.utcnow)


class AssetCatalog(Base):
    __tablename__ = 'asset_catalog'

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    asset_class = Column(String, nullable=False, default='crypto')  # crypto, stock, etf, fx, commodity, index
    logo_url = Column(String, nullable=True)
    tradingview_symbol = Column(String, nullable=True)
    coingecko_id = Column(String, nullable=True)
    coincap_id = Column(String, nullable=True)
    yahoo_symbol = Column(String, nullable=True)
    provider = Column(String, nullable=True, default='manual')
    primary_provider = Column(String, nullable=True)
    fallback_provider = Column(String, nullable=True)
    provider_symbol = Column(String, nullable=True)
    exchange = Column(String, nullable=True)
    market_region = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    base_currency = Column(String, nullable=True)
    quote_currency = Column(String, nullable=True)
    entitlement_tier = Column(String, nullable=True, default='internal')
    is_delayed = Column(Boolean, default=False)
    refresh_policy = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConversationState(Base):
    """
    🧠 Tijdelijk, compact, workflow-focused geheugen voor de AI assistent.
    """
    __tablename__ = 'conversation_state'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    current_flow = Column(String, nullable=True) # e.g. 'setup_creation', 'strategy_creation', 'bot_creation'
    asset = Column(String, nullable=True) # e.g. 'SOL', 'BTC'
    slots = Column(JSON, default=dict) # JSON dictionary of collected fields
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MobilePushToken(Base):
    __tablename__ = 'mobile_push_tokens'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    push_token = Column(String, nullable=False, unique=True)  # ExponentPushToken[xxxx]
    device_name = Column(String, nullable=True)                # e.g., "iPhone 15"
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    id = Column(String, primary_key=True)  # UUID string
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    intent = Column(String, nullable=True)  # e.g., 'chat', 'decision', etc.
    actions = Column(JSON, nullable=True)   # Custom buttons/forms in JSON format


class FinnV2Conversation(Base):
    __tablename__ = "finn_v2_conversations"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    last_run_id = Column(String, nullable=True)
    context_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class FinnV2Run(Base):
    __tablename__ = "finn_v2_runs"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("finn_v2_conversations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = Column(String, nullable=False)
    trace_id = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    transport = Column(String, nullable=False)
    visibility = Column(String, nullable=False)
    feature_mode = Column(String, nullable=False)
    status = Column(String, nullable=False)
    interaction_mode = Column(String, nullable=True)
    message = Column(String, nullable=False)
    workspace_hints_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    client_context_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    policy_json = Column(JSONB, nullable=True)
    response_json = Column(JSONB, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    retryable = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2RunTrace(Base):
    __tablename__ = "finn_v2_run_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trace_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    event_order = Column(Integer, nullable=False)
    payload_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2RunDispatch(Base):
    __tablename__ = "finn_v2_run_dispatches"

    dispatch_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    task_id = Column(String, nullable=False, unique=True)
    queue = Column(String, nullable=False)
    routing_rule = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    owner = Column(String, nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    last_error_code = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2ToolCall(Base):
    __tablename__ = "finn_v2_tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trace_id = Column(String, nullable=True, index=True)
    tool_name = Column(String, nullable=False, index=True)
    operation_id = Column(String, nullable=True, index=True)
    operation_contract_version = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)
    selector_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    success = Column(Boolean, nullable=True)
    resolution_source = Column(String, nullable=True)
    freshness_status = Column(String, nullable=True)
    result_summary_json = Column(JSONB, nullable=True)
    error_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    redacted_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2EvidenceArtifact(Base):
    __tablename__ = "finn_v2_evidence_artifacts"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_call_id = Column(Integer, ForeignKey("finn_v2_tool_calls.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    tool_name = Column(String, nullable=False)
    information_scope = Column(String, nullable=True, index=True)
    operation_id = Column(String, nullable=True, index=True)
    operation_contract_version = Column(String, nullable=True)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    asset = Column(String, nullable=True)
    source = Column(String, nullable=False)
    resolution_source = Column(String, nullable=False)
    user_scoped = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    source_as_of = Column(DateTime(timezone=True), nullable=True)
    freshness = Column(String, nullable=False)
    availability = Column(String, nullable=False)
    schema_name = Column(String, nullable=False)
    schema_version = Column(String, nullable=False)
    content_hash = Column(String, nullable=False, index=True)
    payload_json = Column(JSONB, nullable=True)
    error_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    redacted_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2StateSnapshot(Base):
    __tablename__ = "finn_v2_state_snapshots"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    schema_version = Column(String, nullable=False)
    assembly_version = Column(String, nullable=False)
    evidence_set_hash = Column(String, nullable=False, index=True)
    snapshot_json = Column(JSONB, nullable=True)
    assembled_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    redacted_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2ValidationResult(Base):
    __tablename__ = "finn_v2_validation_results"

    id = Column(String, primary_key=True)
    snapshot_id = Column(String, ForeignKey("finn_v2_state_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    schema_version = Column(String, nullable=False)
    validator_version = Column(String, nullable=False)
    evidence_set_hash = Column(String, nullable=False)
    integrity_status = Column(String, nullable=False, index=True)
    result_json = Column(JSONB, nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    redacted_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2OrchestratorResult(Base):
    __tablename__ = "finn_v2_orchestrator_results"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    orchestrator_version = Column(String, nullable=False)
    analysis_version = Column(String, nullable=False)
    planning_version = Column(String, nullable=False)
    interaction_mode = Column(String, nullable=False, index=True)
    subject_scopes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    required_domains_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    optional_domains_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    tool_plan_json = Column(JSONB, nullable=False)
    snapshot_id = Column(String, ForeignKey("finn_v2_state_snapshots.id", ondelete="SET NULL"), nullable=True)
    validation_id = Column(String, ForeignKey("finn_v2_validation_results.id", ondelete="SET NULL"), nullable=True)
    outcome = Column(String, nullable=False, index=True)
    selected_clarification_json = Column(JSONB, nullable=True)
    unavailable_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    uncertainty_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2PolicyDecision(Base):
    __tablename__ = "finn_v2_policy_decisions"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    orchestrator_result_id = Column(String, ForeignKey("finn_v2_orchestrator_results.id", ondelete="CASCADE"), nullable=False)
    snapshot_id = Column(String, ForeignKey("finn_v2_state_snapshots.id", ondelete="SET NULL"), nullable=True)
    validation_id = Column(String, ForeignKey("finn_v2_validation_results.id", ondelete="SET NULL"), nullable=True)
    policy_class = Column(String, nullable=False, index=True)
    operation_type = Column(String, nullable=True, index=True)
    allowed = Column(Boolean, nullable=False)
    proposal_allowed = Column(Boolean, nullable=False)
    confirmation_required = Column(Boolean, nullable=False)
    step_up_required = Column(Boolean, nullable=False)
    execution_allowed = Column(Boolean, nullable=False)
    shadow_safe = Column(Boolean, nullable=False)
    evidence_set_hash = Column(String, nullable=True)
    decision_json = Column(JSONB, nullable=False)
    policy_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2Proposal(Base):
    __tablename__ = "finn_v2_proposals"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_decision_id = Column(String, ForeignKey("finn_v2_policy_decisions.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, index=True)
    operation_type = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    asset = Column(String, nullable=True)
    payload_json = Column(JSONB, nullable=False)
    payload_hash = Column(String, nullable=False)
    evidence_set_hash = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    requires_step_up_auth = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    expires_at = Column(DateTime(timezone=True), nullable=False)


class FinnV2Confirmation(Base):
    __tablename__ = "finn_v2_confirmations"

    id = Column(String, primary_key=True)
    proposal_id = Column(String, ForeignKey("finn_v2_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False)
    payload_hash = Column(String, nullable=False)
    confirmed = Column(Boolean, nullable=False)
    already_confirmed = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2EligibilityDecision(Base):
    __tablename__ = "finn_v2_eligibility_decisions"

    id = Column(String, primary_key=True)
    proposal_id = Column(String, ForeignKey("finn_v2_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    eligible = Column(Boolean, nullable=False)
    policy_class = Column(String, nullable=False, index=True)
    decision_json = Column(JSONB, nullable=False)
    eligibility_version = Column(String, nullable=False)
    checked_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2ReasoningResult(Base):
    __tablename__ = "finn_v2_reasoning_results"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    orchestrator_result_id = Column(String, ForeignKey("finn_v2_orchestrator_results.id", ondelete="CASCADE"), nullable=False)
    policy_decision_id = Column(String, ForeignKey("finn_v2_policy_decisions.id", ondelete="CASCADE"), nullable=False)
    snapshot_id = Column(String, ForeignKey("finn_v2_state_snapshots.id", ondelete="CASCADE"), nullable=False)
    validation_id = Column(String, ForeignKey("finn_v2_validation_results.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False, index=True)
    context_version = Column(String, nullable=False)
    evidence_set_hash = Column(String, nullable=False)
    input_hash = Column(String, nullable=False, index=True)
    prompt_version = Column(String, nullable=False)
    schema_version = Column(String, nullable=False)
    reasoning_version = Column(String, nullable=False)
    model = Column(String, nullable=True)
    result_json = Column(JSONB, nullable=True)
    error_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2VerifierResult(Base):
    __tablename__ = "finn_v2_verifier_results"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id = Column(String, nullable=False)
    reasoning_result_id = Column(String, ForeignKey("finn_v2_reasoning_results.id", ondelete="SET NULL"), nullable=True, index=True)
    passed = Column(Boolean, nullable=False)
    action = Column(String, nullable=False)
    result_json = Column(JSONB, nullable=False)
    reason_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    deterministic_version = Column(String, nullable=False)
    semantic_verifier_used = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    semantic_model = Column(String, nullable=True)
    repair_attempt = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2VerifiedResponse(Base):
    __tablename__ = "finn_v2_verified_responses"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    verifier_result_id = Column(String, ForeignKey("finn_v2_verifier_results.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(String, nullable=False)
    verifier_status = Column(String, nullable=False)
    response_json = Column(JSONB, nullable=False)
    evidence_set_hash = Column(String, nullable=False)
    response_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2EvalRun(Base):
    __tablename__ = "finn_v2_eval_runs"

    id = Column(String, primary_key=True)
    dataset_path = Column(String, nullable=False)
    model_mode = Column(String, nullable=False)
    total_cases = Column(Integer, nullable=False)
    passed_cases = Column(Integer, nullable=False)
    failed_cases = Column(Integer, nullable=False)
    result_json = Column(JSONB, nullable=False)
    blocking_gate_results_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    aggregate_scores_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    failure_case_ids_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    real_model_validation_blocked = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    blocker_code = Column(String, nullable=True)
    total_input_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    total_output_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    total_reasoning_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    estimated_cost = Column(Numeric, nullable=False, default=0, server_default=text("0"))
    latency_p50_ms = Column(Numeric, nullable=False, default=0, server_default=text("0"))
    latency_p95_ms = Column(Numeric, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class FinnV2EvalCaseResult(Base):
    __tablename__ = "finn_v2_eval_case_results"

    id = Column(String, primary_key=True)
    eval_run_id = Column(String, ForeignKey("finn_v2_eval_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    fixture_user = Column(String, nullable=False)
    passed = Column(Boolean, nullable=False)
    blocking_passed = Column(Boolean, nullable=False)
    expected_mode = Column(String, nullable=False)
    actual_mode = Column(String, nullable=True)
    expected_outcome = Column(String, nullable=False)
    actual_outcome = Column(String, nullable=True)
    dimension_scores_json = Column(JSONB, nullable=False)
    blocking_gate_results_json = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    reason_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    latency_ms = Column(Integer, nullable=True)
    model = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2ShadowComparison(Base):
    __tablename__ = "finn_v2_shadow_comparisons"

    id = Column(String, primary_key=True)
    run_id = Column(String, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    surface = Column(String, nullable=False)
    outcome = Column(String, nullable=False, index=True)
    result_json = Column(JSONB, nullable=False)
    reason_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2ReleaseGateResult(Base):
    __tablename__ = "finn_v2_release_gate_results"

    id = Column(String, primary_key=True)
    eval_run_id = Column(String, ForeignKey("finn_v2_eval_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    passed = Column(Boolean, nullable=False)
    result_json = Column(JSONB, nullable=False)
    reason_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class FinnV2Execution(Base):
    __tablename__ = "finn_v2_executions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="ux_finn_v2_execution_user_idempotency"),
    )

    id = Column(String, primary_key=True)
    proposal_id = Column(String, ForeignKey("finn_v2_proposals.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    run_id = Column(String, ForeignKey("finn_v2_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    precondition_hash = Column(String, nullable=False)
    postcondition_hash = Column(String, nullable=True)
    result_json = Column(JSONB, nullable=True)
    error_codes_json = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AiPendingAction(Base):
    __tablename__ = 'ai_pending_actions'

    id = Column(String, primary_key=True)  # UUID string
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = Column(String, nullable=False)  # 'setup_draft', 'strategy_draft', 'bot_draft', 'watchlist_add', etc.
    payload = Column(JSON, nullable=False)  # Config payload
    status = Column(String, nullable=False, default='pending')  # 'pending', 'executed', 'expired', 'canceled'
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    trace_id = Column(String, nullable=True)


class AiIntelligenceEvent(Base):
    __tablename__ = 'ai_intelligence_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = Column(String, nullable=False)  # 'macro_shift', 'volatility_expansion', 'risk_spike', 'bot_underperformance', 'drawdown_alert', 'setup_activation'
    symbol = Column(String, nullable=True)  # e.g., 'SOL', 'BTC'
    title = Column(String, nullable=False)  # e.g., "Hoge SOL Concentratie"
    description = Column(String, nullable=False)  # Rich explanation in Dutch
    severity = Column(String, nullable=False, default='info')  # 'info', 'warning', 'critical'
    payload = Column(JSON, nullable=True)  # Contextual parameters/attributes
    status = Column(String, nullable=False, default='active')  # 'active', 'archived'
    created_at = Column(DateTime, default=datetime.utcnow)
