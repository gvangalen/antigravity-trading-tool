from __future__ import annotations

import argparse

from backend.utils.db import get_db_connection


FILL_EMAIL_SQL = """
UPDATE ai_usage_logs AS logs
SET user_email_snapshot = users.email
FROM users
WHERE logs.user_id = users.id
  AND logs.user_id IS NOT NULL
  AND (logs.user_email_snapshot IS NULL OR logs.user_email_snapshot = '');
"""

FILL_APP_ENV_SQL = """
UPDATE ai_usage_logs
SET app_env = %s
WHERE app_env IS NULL OR app_env = '';
"""

FILL_ENTRY_POINT_SQL = """
UPDATE ai_usage_logs
SET entry_point = CASE
    WHEN purpose = 'daily_report_generation' THEN 'daily_report_task'
    WHEN purpose = 'weekly_report_generation' THEN 'weekly_report_task'
    WHEN purpose = 'monthly_report_generation' THEN 'monthly_report_task'
    WHEN purpose = 'quarterly_report_generation' THEN 'quarterly_report_task'
    WHEN purpose = 'daily_report_preview' THEN 'report_service:daily_preview'
    WHEN purpose LIKE 'chat_%%' THEN 'assistant_service:' || REPLACE(purpose, 'chat_', '')
    WHEN purpose IN ('decision_review', 'priority_engine', 'plan_adherence_review') THEN 'assistant_service:' || purpose
    WHEN COALESCE(run_kind, '') = 'scheduled' THEN 'scheduled_job'
    ELSE entry_point
END
WHERE entry_point IS NULL OR entry_point = '';
"""

FILL_RUN_KIND_SQL = """
UPDATE ai_usage_logs
SET run_kind = CASE
    WHEN purpose IN (
        'daily_report_generation',
        'weekly_report_generation',
        'monthly_report_generation',
        'quarterly_report_generation'
    ) OR COALESCE(entry_point, '') IN (
        'daily_report_task',
        'weekly_report_task',
        'monthly_report_task',
        'quarterly_report_task',
        'scheduled_job'
    ) THEN 'scheduled'
    WHEN user_id IS NULL THEN 'system'
    ELSE 'interactive'
END
WHERE run_kind IS NULL OR run_kind = '';
"""

FILL_SOURCE_SQL = """
UPDATE ai_usage_logs
SET request_source = CASE
    WHEN COALESCE(run_kind, '') = 'scheduled'
         OR purpose IN (
            'daily_report_generation',
            'weekly_report_generation',
            'monthly_report_generation',
            'quarterly_report_generation'
         )
         OR COALESCE(entry_point, '') IN (
            'daily_report_task',
            'weekly_report_task',
            'monthly_report_task',
            'quarterly_report_task',
            'scheduled_job'
         ) THEN 'background_job'
    WHEN user_id IS NULL THEN 'system'
    WHEN LOWER(COALESCE(user_email_snapshot, '')) LIKE '%%qa%%'
         OR LOWER(COALESCE(user_email_snapshot, '')) LIKE '%%codex%%'
         OR LOWER(COALESCE(user_email_snapshot, '')) LIKE '%%example.com%%'
         OR LOWER(COALESCE(user_email_snapshot, '')) LIKE '%%staging.operator%%'
         OR LOWER(COALESCE(user_email_snapshot, '')) LIKE '%%telemetry.%%' THEN 'qa_user'
    WHEN LOWER(COALESCE(app_env, '')) = 'staging' THEN 'staging_user'
    WHEN LOWER(COALESCE(app_env, '')) = 'production' THEN 'live_user'
    ELSE 'live_user'
END
WHERE request_source IS NULL
   OR request_source = ''
   OR request_source = 'unclassified';
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill AI usage observability metadata.")
    parser.add_argument("--app-env", default="production", help="Fallback app environment for unlabeled rows.")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without committing updates.")
    args = parser.parse_args()

    conn = get_db_connection()
    if conn is None:
        raise SystemExit("Database connection unavailable")

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ai_usage_logs WHERE COALESCE(request_source, 'unclassified') = 'unclassified'")
                before_unclassified = cur.fetchone()[0]

                cur.execute(FILL_EMAIL_SQL)
                email_updates = cur.rowcount

                cur.execute(FILL_APP_ENV_SQL, (args.app_env,))
                app_env_updates = cur.rowcount

                cur.execute(FILL_ENTRY_POINT_SQL)
                entry_updates = cur.rowcount

                cur.execute(FILL_RUN_KIND_SQL)
                run_kind_updates = cur.rowcount

                cur.execute(FILL_SOURCE_SQL)
                source_updates = cur.rowcount

                cur.execute("SELECT COUNT(*) FROM ai_usage_logs WHERE COALESCE(request_source, 'unclassified') = 'unclassified'")
                after_unclassified = cur.fetchone()[0]

                print({
                    "before_unclassified": before_unclassified,
                    "after_unclassified": after_unclassified,
                    "email_updates": email_updates,
                    "app_env_updates": app_env_updates,
                    "entry_point_updates": entry_updates,
                    "run_kind_updates": run_kind_updates,
                    "source_updates": source_updates,
                    "dry_run": args.dry_run,
                })

                if args.dry_run:
                    conn.rollback()
                else:
                    conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
