SQL = """
ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS request_source VARCHAR(64) DEFAULT 'unclassified';

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS app_env VARCHAR(32);

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS run_kind VARCHAR(32);

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS entry_point VARCHAR(128);

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS user_email_snapshot VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_request_source
ON ai_usage_logs(request_source);

CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_app_env
ON ai_usage_logs(app_env);

CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_run_kind
ON ai_usage_logs(run_kind);

CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_entry_point
ON ai_usage_logs(entry_point);
"""
