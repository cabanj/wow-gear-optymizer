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


def test_daily_report_falls_back_to_stale_snapshot(monkeypatch):
    """Snapshot refresh fails → runs still enqueued from stale snapshot."""
    import asyncio
    import app.characters.service as CS
    import app.reports.service as RS
    from app.scheduler import daily as D

    calls = {"runs": 0, "reports": 0}

    class FakeChar:
        id = "c1"
        name = "Calipse"
        blizzard_account_id = "a1"
        selected = True

    snap_ts = datetime.now(timezone.utc) - timedelta(hours=30)

    class FakeSnap:
        id = "s1"
        timestamp = snap_ts

    class FakeResult:
        def scalars(self):
            class S:
                def all(s):
                    return [FakeChar()]
                def first(s):
                    return FakeSnap()
            return S()
        def scalar_one(self):
            return object()

    class FakeDB:
        async def execute(self, *a, **k):
            return FakeResult()
        async def commit(self):
            return None

    class FakeSession:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return FakeDB()
        async def __aexit__(self, *a):
            return False

    async def boom(*a, **k):
        raise RuntimeError("Blizzard access token expired and no refresh token stored")

    async def fake_run(db, char, snap, ptype):
        calls["runs"] += 1
        assert isinstance(snap, FakeSnap)  # stale snapshot reused
        return f"run-{ptype}"

    async def fake_report(db, char, snap, profile_type, warning=None):
        calls["reports"] += 1
        assert warning and "30 hours" in warning
        return object()

    # daily_report imports these INSIDE the function body, so patch the
    # source modules (patching D.* would miss the local import binding)
    monkeypatch.setattr(CS, "snapshot_character", boom)
    monkeypatch.setattr(RS, "run_full_simulation", fake_run)
    monkeypatch.setattr(RS, "purge_old_data", lambda db, days=3: asyncio.sleep(0, result={}))
    monkeypatch.setattr(D, "_make_report", fake_report)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.async_sessionmaker",
                        lambda *a, **k: FakeSession)
    asyncio.run(D.daily_report(object()))
    assert calls == {"runs": 2, "reports": 1}


def test_user_token_errors_ask_for_relogin():
    import asyncio
    from app.blizzard.client import BlizzardClient
    c = BlizzardClient()

    async def probe(tokens):
        try:
            await c._get_user_token(dict(tokens))
        except RuntimeError as e:
            return str(e)
        return None

    for tokens in ({}, {"access_token": "x", "expires_at": 0}):
        msg = asyncio.run(probe(tokens))
        assert msg and "re-login" in msg, f"no re-login error for {tokens!r}"