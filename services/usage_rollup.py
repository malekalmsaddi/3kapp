"""
services/usage_rollup.py — Monthly usage summary rollup task.

Registered as a Celery Beat periodic task. Runs nightly to aggregate
usage_events into monthly_usage_summary for billing and analytics.
"""
from datetime import datetime, timezone
from logati import logger


def rollup_monthly_usage():
    """Aggregate usage_events into monthly_usage_summary for the current month.

    This is designed to be idempotent — it uses INSERT ... ON CONFLICT to
    upsert the totals, so running it multiple times in the same day is safe.
    """
    from db import get_conn

    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO monthly_usage_summary (tenant_id, month, event_type, total_quantity, computed_at)
                    SELECT
                        tenant_id,
                        date_trunc('month', created_at)::date AS month,
                        event_type,
                        SUM(quantity) AS total_quantity,
                        NOW()
                    FROM usage_events
                    WHERE created_at >= %s
                    GROUP BY tenant_id, date_trunc('month', created_at), event_type
                    ON CONFLICT (tenant_id, month, event_type) DO UPDATE
                    SET total_quantity = EXCLUDED.total_quantity,
                        computed_at = NOW()
                    """,
                    (month_start,),
                )
                updated = cur.rowcount
        logger.info(f'[usage_rollup] Rolled up {updated} rows for month starting {month_start.date()}')
    except Exception as e:
        logger.error(f'[usage_rollup] Failed: {e}')
        raise


def register_beat_schedule(celery_app):
    """Register the nightly usage rollup task in Celery Beat."""
    from celery.schedules import crontab

    @celery_app.task(name='tasks.rollup_monthly_usage')
    def _rollup_task():
        rollup_monthly_usage()

    celery_app.conf.beat_schedule = celery_app.conf.get('beat_schedule', {})
    celery_app.conf.beat_schedule['nightly-usage-rollup'] = {
        'task': 'tasks.rollup_monthly_usage',
        'schedule': crontab(hour=2, minute=0),  # 2:00 AM UTC daily
        'args': (),
    }
