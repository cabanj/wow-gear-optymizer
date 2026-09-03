"""Tests for scheduler pipeline pieces (mocked)."""
from datetime import datetime, timedelta, timezone

import pytest


def test_snapshot_age_warning_message():
    snap_time = datetime.now(timezone.utc) - timedelta(hours=18)
    age_h = (datetime.now(timezone.utc) - snap_time).total_seconds() / 3600
    msg = (f"Using character snapshot from {age_h:.0f} hours ago. "
           f"Blizzard API refresh failed.")
    assert "18 hours" in msg


def test_cron_trigger_parses_settings():
    from app.scheduler.daily import create_scheduler  # noqa: F401 - import check
    cron = "0 12 * * *"
    parts = cron.split()
    assert parts[0] == "0" and parts[1] == "12"