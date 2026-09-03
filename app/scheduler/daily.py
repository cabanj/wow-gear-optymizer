"""Daily report scheduler: 12:00 Europe/Warsaw, DST-safe."""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..db.models import BlizzardAccount, Character, CharacterSnapshot, Report

log = logging.getLogger("scheduler")


def create_scheduler(engine) -> AsyncScheduler:
    s = get_settings()
    sched = AsyncScheduler()
    hour, minute = s.cron_report.split()[1], s.cron_report.split()[0]
    sched.add_job(
        daily_reports,
        CronTrigger(hour=int(hour), minute=int(minute),
                    timezone=ZoneInfo(s.cron_tz)),  # DST handled by zoneinfo
        args=[engine],
        id="daily_report",
        misfire_grace_time=3600,
    )
    return sched


async def daily_report(engine) -> None:
    """Full pipeline: snapshot → sim runs for all selected characters."""
    from ..characters.service import snapshot_character
    from ..reports.service import run_full_simulation
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        chars = (await db.execute(
            select(Character).join(BlizzardAccount).where(Character.selected.is_(True))
        )).scalars().all()
        for char in chars:
            try:
                account = (await db.execute(
                    select(BlizzardAccount).where(BlizzardAccount.id == char.blizzard_account_id)
                )).scalar_one()
                try:
                    snap = await snapshot_character(db, char, account)
                except Exception as e:
                    # Blizzard API down: use latest snapshot, mark age
                    snap = (await db.execute(
                        select(CharacterSnapshot).where(
                            CharacterSnapshot.character_id == char.id)
                        .order_by(CharacterSnapshot.timestamp.desc())
                    )).scalars().first()
                    if snap is None:
                        log.error("no snapshot for %s, skipping", char.name)
                        continue
                    age_h = (datetime.now(timezone.utc)
                             - snap.timestamp.replace(tzinfo=timezone.utc)
                             ).total_seconds() / 3600
                    await _make_report(db, char, snap, profile_type="raid",
                                       warning=f"Using character snapshot from {age_h:.0f} hours ago. "
                                               f"Blizzard API refresh failed ({e}).")
                    continue
                for ptype in ("raid", "mplus"):
                    await run_full_simulation(db, char, snap, ptype)
                # report rows created when runs complete (worker side / status check)
            except Exception:
                log.exception("daily report failed for %s", char.name)


async def _make_report(db, char, snap, profile_type, warning=None):
    rep = Report(
        character_id=char.id,
        report_date=datetime.now(timezone.utc).date(),
        snapshot_age_warning=warning,
        status="generating",
    )
    db.add(rep)
    await db.commit()
    return rep