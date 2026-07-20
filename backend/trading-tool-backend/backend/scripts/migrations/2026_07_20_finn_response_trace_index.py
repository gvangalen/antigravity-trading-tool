"""Index privacy-safe FINN response traces for per-response diagnostics."""

SQL = """
CREATE INDEX IF NOT EXISTS idx_finn_product_events_user_trace
ON finn_product_events (user_id, trace_id, created_at DESC)
WHERE event_name = 'finn_response_trace' AND trace_id IS NOT NULL;
"""
