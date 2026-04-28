"""Move Mono statement sync from 30-minute interval to daily crontab.

The Mono statement sync was originally scheduled every 30 minutes via the
``scheduled_tasks`` table (``interval_seconds=1800``). Each sweep calls
``trigger_data_refresh`` which is rate-limited by Mono to one per account
per 5 minutes — so 30-minute polling was already producing many more
upstream-bank scrapes than finance actually consumes.

The companion fresh-install change in ``app/services/settings_seed.py``
flipped the seed to a crontab at 05:00 UTC (06:00 WAT). This migration
brings already-deployed databases in line by updating the existing row
in place. Idempotent: only matches rows that still have the old
interval-based config.

Webhook-driven ingest (``sync_mono_account.delay`` from
``account_updated``) and the per-account "Sync Now" button are
untouched — they remain on-demand paths.

Revision ID: 20260428_mono_sync_daily_schedule
Revises: 20260428_undo_2025_period_close_artifact
Create Date: 2026-04-28
"""

from __future__ import annotations

from alembic import op


revision = "20260428_mono_sync_daily_schedule"
down_revision = "20260428_undo_2025_period_close_artifact"
branch_labels = None
depends_on = None


TASK_NAME = "app.tasks.finance.sync_mono_transactions"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE scheduled_tasks
        SET schedule_type = 'crontab',
            cron_minute = '0',
            cron_hour = '5',
            cron_day_of_week = '*',
            cron_day_of_month = '*',
            cron_month_of_year = '*',
            updated_at = now()
        WHERE task_name = '{TASK_NAME}'
          AND schedule_type = 'interval'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE scheduled_tasks
        SET schedule_type = 'interval',
            interval_seconds = 1800,
            cron_minute = '0',
            cron_hour = '8',
            cron_day_of_week = '*',
            cron_day_of_month = '*',
            cron_month_of_year = '*',
            updated_at = now()
        WHERE task_name = '{TASK_NAME}'
          AND schedule_type = 'crontab'
        """
    )
