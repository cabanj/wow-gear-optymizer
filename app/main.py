"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from .auth.blizzard_oauth import BlizzardOAuth, TokenStore, new_state
from .characters.service import discover_characters, snapshot_character
from .config import get_settings
from .db.models import BlizzardAccount, Character, User
from .db.session import make_engine, make_sessionmaker

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    app.state.engine = engine
    app.state.SessionLocal = make_sessionmaker(engine)
    yield
    await engine.dispose()


app = FastAPI(title="WoW Gear Upgrade Analyzer", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)


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
async def auth_callback(request: Request, code: str, state: str,
                        db: AsyncSession = Depends(get_db)):
    expected = request.session.pop("oauth_state", None)
    if not expected or expected != state:
        raise HTTPException(400, "OAuth state mismatch")
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

    blob = TokenStore().encrypt(tokens)
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
async def index(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(request, "index.html", {"user": user})


@app.get("/characters", response_class=HTMLResponse)
async def characters_page(request: Request, user: User | None = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if user is None:
        return RedirectResponse("/")
    chars = (await db.execute(
        select(Character).join(BlizzardAccount).where(BlizzardAccount.user_id == user.id)
    )).scalars().all()
    return templates.TemplateResponse(request, "characters.html", {"user": user, "characters": chars})


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


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
