"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from .auth.blizzard_oauth import BlizzardOAuth, TokenStore, new_state
from .characters.service import discover_characters, snapshot_character
from .config import get_settings
from .db.models import BlizzardAccount, Character, CharacterSnapshot, User
from .db.session import make_engine, make_sessionmaker
from .scheduler.daily import create_scheduler

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    app.state.engine = engine
    app.state.SessionLocal = make_sessionmaker(engine)
    scheduler = create_scheduler(engine)
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(title="WoW Gear Upgrade Analyzer", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


async def get_db(request: Request) -> AsyncSession:
    async with request.app.state.SessionLocal() as session:
        yield session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


# ---------------- auth ----------------
@app.get("/auth/blizzard")
async def auth_blizzard(request: Request):
    oauth = BlizzardOAuth()
    state = new_state()
    request.session["oauth_state"] = state
    return RedirectResponse(oauth.authorize_url(state))


@app.get("/auth/blizzard/callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db),
                        code: str | None = None, state: str | None = None,
                        error: str | None = None,
                        error_description: str | None = None):
    if error or not code or not state:
        detail = error or "missing_code_or_state"
        desc = error_description or (
            "Blizzard did not return an authorization code. "
            "Most often the redirect URI is not whitelisted exactly, "
            "or access was denied on the consent screen."
        )
        return HTMLResponse(
            f"<h1>Blizzard login failed: {detail}</h1><p>{desc}</p>"
            f"<p><a href='/'>Back</a></p>", status_code=400)
    expected = request.session.pop("oauth_state", None)
    if not expected or expected != state:
        raise HTTPException(400, "OAuth state mismatch (session lost or reused link)")
    oauth = BlizzardOAuth()
    tokens = await oauth.exchange_code(code)
    tokens["expires_at"] = __import__("time").time() + tokens.get("expires_in", 0)

    # fetch identity to link to user
    async with __import__("httpx").AsyncClient(timeout=30) as client:
        ident = (await client.get(
            "https://oauth.battle.net/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )).json()

    user = (await db.execute(
        select(User).where(User.bnet_id == str(ident["id"]))
    )).scalar_one_or_none()
    if user is None:
        user = User(bnet_id=str(ident["id"]), battletag=ident.get("battletag", ""))
        db.add(user)
        await db.flush()
    user.last_login = func_now()

    blob = TokenStore().encrypt(tokens).decode()
    account = (await db.execute(
        select(BlizzardAccount).where(
            BlizzardAccount.user_id == user.id,
            BlizzardAccount.region == get_settings().blizzard_region,
        )
    )).scalar_one_or_none()
    if account is None:
        account = BlizzardAccount(user_id=user.id, region=get_settings().blizzard_region)
        db.add(account)
        await db.flush()
    account.tokens_encrypted = blob
    account.token_expires_at = tokens["expires_at"]
    await db.commit()
    request.session["user_id"] = str(user.id)
    return RedirectResponse("/characters")


def func_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


@app.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# ---------------- pages ----------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User | None = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    from .reports.pages import dashboard_cards
    cards = await dashboard_cards(db, user.id) if user else []
    return templates.TemplateResponse(request, "index.html", {"user": user, "cards": cards})


@app.get("/characters", response_class=HTMLResponse)
async def characters_page(request: Request, character_id: str | None = None,
                          user: User | None = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if user is None:
        return RedirectResponse("/")
    chars = (await db.execute(
        select(Character).join(BlizzardAccount).where(BlizzardAccount.user_id == user.id)
        .order_by(Character.name)
    )).scalars().all()
    snap_times = {}
    for c in chars:
        s = (await db.execute(
            select(CharacterSnapshot).where(CharacterSnapshot.character_id == c.id,
                                            CharacterSnapshot.is_current.is_(True))
        )).scalars().first()
        snap_times[str(c.id)] = s.timestamp.strftime("%Y-%m-%d %H:%M") if s else None
    for c in chars:
        c.snapshot_time = snap_times.get(str(c.id))
    current = next((c for c in chars if str(c.id) == character_id),
                   next((c for c in chars if c.selected), chars[0] if chars else None))
    from .reports.pages import character_gear
    gear_list = []
    if current is not None:
        try:
            gear_list = await character_gear(db, current.id)
        except Exception:
            gear_list = []
    return templates.TemplateResponse(request, "characters.html",
                                       {"user": user, "characters": chars,
                                        "current": current, "gear": gear_list,
                                        "all_ids": [str(c.id) for c in chars]})


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, character_id: str | None = None,
                       user: User | None = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if user is None:
        return RedirectResponse("/")
    from .reports.pages import list_runs
    runs = await list_runs(db, user.id, character_id)
    char = None
    if character_id:
        char = (await db.execute(
            select(Character).where(Character.id == character_id))).scalar_one_or_none()
    return templates.TemplateResponse(request, "reports.html",
                                       {"user": user, "runs": runs, "character": char})


@app.get("/reports/{run_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, run_id: str,
                             user: User | None = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    if user is None:
        return RedirectResponse("/")
    from .reports.pages import history, run_report
    from uuid import UUID
    try:
        rep = await run_report(db, UUID(run_id))
    except Exception:
        raise HTTPException(404, "report not found")
    # history for the character of this run
    from .db.models import SimulationRun as _SR
    run = (await db.execute(select(_SR).where(_SR.id == UUID(run_id)))).scalar_one()
    labels, values = await history(db, run.character_id)
    return templates.TemplateResponse(request, "report_detail.html",
                                       {"user": user, **rep,
                                        "hist_labels": labels, "hist_values": values,
                                        "warning": None})


# ---------------- api ----------------
@app.get("/api/characters")
async def api_characters(user: User | None = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if user is None:
        raise HTTPException(401, "not logged in")
    chars = (await db.execute(
        select(Character).join(BlizzardAccount).where(BlizzardAccount.user_id == user.id)
    )).scalars().all()
    return [{
        "id": str(c.id), "name": c.name, "realm": c.realm_slug,
        "class": c.class_name, "spec": c.active_spec_name,
        "level": c.level, "selected": c.selected,
    } for c in chars]


@app.post("/api/characters/select")
async def api_select_characters(request: Request,
                                user: User | None = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if user is None:
        raise HTTPException(401, "not logged in")
    body = await request.json()
    selected_ids = set(body.get("character_ids", []))
    chars = (await db.execute(
        select(Character).join(BlizzardAccount).where(BlizzardAccount.user_id == user.id)
    )).scalars().all()
    for c in chars:
        c.selected = str(c.id) in selected_ids
    await db.commit()
    return {"selected": len(selected_ids)}


@app.post("/api/characters/refresh")
async def api_refresh_characters(user: User | None = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """Re-discover characters from /profile/user/wow."""
    if user is None:
        raise HTTPException(401, "not logged in")
    account = (await db.execute(
        select(BlizzardAccount).where(BlizzardAccount.user_id == user.id)
    )).scalar_one_or_none()
    if account is None or account.tokens_encrypted is None:
        raise HTTPException(400, "no blizzard account linked")
    chars = await discover_characters(db, account)
    return {"count": len(chars), "characters": chars}


@app.post("/api/characters/{character_id}/snapshot")
async def api_snapshot(character_id: str,
                       user: User | None = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if user is None:
        raise HTTPException(401, "not logged in")
    char = (await db.execute(
        select(Character).join(BlizzardAccount).where(
            Character.id == character_id, BlizzardAccount.user_id == user.id)
    )).scalar_one_or_none()
    if char is None:
        raise HTTPException(404, "character not found")
    account = (await db.execute(
        select(BlizzardAccount).where(BlizzardAccount.id == char.blizzard_account_id)
    )).scalar_one()
    snap = await snapshot_character(db, char, account)
    return {"snapshot_id": str(snap.id), "timestamp": str(snap.timestamp),
            "item_level": float(snap.item_level) if snap.item_level else None}


@app.post("/api/simulate/{character_id}")
async def api_simulate(character_id: str, request: Request,
                       user: User | None = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Kick off a full simulation for a character (uses latest snapshot)."""
    if user is None:
        raise HTTPException(401, "not logged in")
    body = await request.json()
    profile_type = body.get("profile_type", "raid")
    if profile_type not in ("raid", "mplus"):
        raise HTTPException(400, "profile_type must be raid or mplus")
    char = (await db.execute(
        select(Character).join(BlizzardAccount).where(
            Character.id == character_id, BlizzardAccount.user_id == user.id)
    )).scalar_one_or_none()
    if char is None:
        raise HTTPException(404, "character not found")
    snap = (await db.execute(
        select(CharacterSnapshot).where(
            CharacterSnapshot.character_id == character_id,
            CharacterSnapshot.is_current.is_(True))
        .order_by(CharacterSnapshot.timestamp.desc())
    )).scalars().first()
    if snap is None:
        raise HTTPException(400, "no snapshot; import character first")
    from .reports.service import run_full_simulation
    run_id = await run_full_simulation(db, char, snap, profile_type)
    return {"run_id": str(run_id), "status": "pending"}


@app.get("/api/runs/{run_id}")
async def api_run_status(run_id: str,
                         user: User | None = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select as _sel
    from .db.models import SimulationRun as _SR
    run = (await db.execute(_sel(_SR).where(_SR.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "run not found")
    data = {"run_id": str(run.id), "status": run.status, "error": run.error,
            "simc_version": run.simc_version, "wow_build": run.wow_build}
    if run.status == "completed":
        from .reports.service import build_report_data
        data["report"] = await build_report_data(db, run.id)
    return data


@app.post("/api/import/simc")
async def api_import_simc(request: Request,
                          user: User | None = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Manual /simc addon import: parse text, validate, save as precise snapshot."""
    if user is None:
        raise HTTPException(401, "not logged in")
    body = await request.json()
    simc_text = body.get("simc_text", "")
    character_id = body.get("character_id")
    if not simc_text or not character_id:
        raise HTTPException(400, "simc_text and character_id required")
    from .simc.importer import parse_simc_addon
    parsed = parse_simc_addon(simc_text)
    if parsed is None:
        raise HTTPException(400, "invalid /simc output")
    char = (await db.execute(
        select(Character).join(BlizzardAccount).where(
            Character.id == character_id, BlizzardAccount.user_id == user.id)
    )).scalar_one_or_none()
    if char is None:
        raise HTTPException(404, "character not found")
    old = (await db.execute(
        select(CharacterSnapshot).where(
            CharacterSnapshot.character_id == character_id,
            CharacterSnapshot.is_current.is_(True))
    )).scalars().all()
    for s in old:
        s.is_current = False
    from datetime import datetime, timezone
    snap = CharacterSnapshot(
        character_id=character_id, source="simc_addon_import",
        timestamp=datetime.now(timezone.utc),
        raw={"parsed": parsed}, simc_text=simc_text,
        item_level=parsed.get("item_level"), is_current=True,
    )
    db.add(snap)
    await db.commit()
    return {"snapshot_id": str(snap.id), "item_level": parsed.get("item_level")}


@app.get("/api/reports")
async def api_reports(user: User | None = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if user is None:
        raise HTTPException(401, "not logged in")
    from .db.models import Report as _R
    reports = (await db.execute(
        select(_R).join(Character).join(BlizzardAccount)
        .where(BlizzardAccount.user_id == user.id).order_by(_R.report_date.desc())
    )).scalars().all()
    return [{"id": str(r.id), "character_id": str(r.character_id),
             "date": str(r.report_date), "status": r.status,
             "baseline_raid": float(r.baseline_dps_raid) if r.baseline_dps_raid else None,
             "baseline_mplus": float(r.baseline_dps_mplus) if r.baseline_dps_mplus else None}
            for r in reports]


@app.get("/api/reports/{report_id}")
async def api_report(report_id: str,
                     user: User | None = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if user is None:
        raise HTTPException(401, "not logged in")
    from .db.models import Report as _R
    rep = (await db.execute(select(_R).where(_R.id == report_id))).scalar_one_or_none()
    if rep is None:
        raise HTTPException(404, "report not found")
    data = {"id": str(rep.id), "date": str(rep.report_date), "status": rep.status,
            "snapshot_age_warning": rep.snapshot_age_warning}
    if rep.simulation_run_raid:
        from .reports.service import build_report_data
        data["raid"] = await build_report_data(db, rep.simulation_run_raid)
    if rep.simulation_run_mplus:
        from .reports.service import build_report_data
        data["mplus"] = await build_report_data(db, rep.simulation_run_mplus)
    return data


@app.post("/api/characters/add")
async def api_add_character(request: Request,
                            user: User | None = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Manual add by realm+name (fallback when /profile/user/wow is empty)."""
    if user is None:
        raise HTTPException(401, "not logged in")
    body = await request.json()
    realm, name = body.get("realm", ""), body.get("name", "")
    if not realm or not name:
        raise HTTPException(400, "realm and name required")
    account = (await db.execute(
        select(BlizzardAccount).where(BlizzardAccount.user_id == user.id)
    )).scalars().first()
    if account is None:
        raise HTTPException(400, "no blizzard account linked")
    from .reports.pages import add_character_manual
    try:
        return await add_character_manual(db, account, realm, name)
    except Exception as e:
        raise HTTPException(400, f"character not found or not visible: {str(e)[:200]}")


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
