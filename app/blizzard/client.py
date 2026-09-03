"""Blizzard API client. Tokens in headers only (Blizzard requirement since 2024-09)."""
import time

import httpx

from ..auth.blizzard_oauth import BlizzardOAuth, TokenStore
from ..config import get_settings


class BlizzardClient:
    def __init__(self) -> None:
        s = get_settings()
        self.host = s.api_host
        self.locale = s.blizzard_locale
        self.region = s.blizzard_region
        self._oauth = BlizzardOAuth()
        self._store = TokenStore()
        self._app_token: dict | None = None

    # -- token management -------------------------------------------------
    async def _get_user_token(self, tokens: dict) -> str:
        if TokenStore.is_expired(tokens):
            refreshed = await self._oauth.refresh(tokens["refresh_token"])
            refreshed["expires_at"] = time.time() + refreshed["expires_in"]
            tokens.update(refreshed)
        return tokens["access_token"]

    async def _get_app_token(self) -> str:
        if self._app_token is None or TokenStore.is_expired(self._app_token):
            tok = await self._oauth.client_credentials()
            tok["expires_at"] = time.time() + tok["expires_in"]
            self._app_token = tok
        return self._app_token["access_token"]

    # -- low level ---------------------------------------------------------
    async def get(self, path: str, namespace: str, token: str, **params) -> dict:
        params.setdefault("namespace", namespace)
        params.setdefault("locale", self.locale)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://{self.host}{path}",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_game_data(self, path: str, **params) -> dict:
        """Game Data API — client credentials, namespace dynamic-{region} or static-{region}."""
        token = await self._get_app_token()
        ns = params.pop("namespace", f"dynamic-{self.region}")
        return await self.get(path, ns, token, **params)

    async def get_user_profile(self, path: str, tokens: dict, **params) -> dict:
        """Profile API — user token, namespace profile-{region}."""
        token = await self._get_user_token(tokens)
        return await self.get(path, f"profile-{self.region}", token, **params)

    # -- high level ----------------------------------------------------------
    async def user_wow_accounts(self, tokens: dict) -> dict:
        """GET /profile/user/wow — all wow accounts and their characters."""
        return await self.get_user_profile("/profile/user/wow", tokens)

    async def character_summary(self, tokens: dict, realm_slug: str, name: str) -> dict:
        return await self.get_user_profile(
            f"/profile/wow/character/{realm_slug}/{name.lower()}", tokens
        )

    async def character_equipment(self, tokens: dict, realm_slug: str, name: str) -> dict:
        return await self.get_user_profile(
            f"/profile/wow/character/{realm_slug}/{name.lower()}/equipment", tokens
        )

    async def character_specializations(self, tokens: dict, realm_slug: str, name: str) -> dict:
        return await self.get_user_profile(
            f"/profile/wow/character/{realm_slug}/{name.lower()}/specializations", tokens
        )

    async def character_talents(self, tokens: dict, realm_slug: str, name: str) -> dict:
        return await self.get_user_profile(
            f"/profile/wow/character/{realm_slug}/{name.lower()}/talents", tokens
        )

    async def character_status(self, tokens: dict, realm_slug: str, name: str) -> dict:
        return await self.get_user_profile(
            f"/profile/wow/character/{realm_slug}/{name.lower()}/status", tokens
        )

    # -- game data (app token) ------------------------------------------------
    async def journal_instances(self) -> dict:
        # NOTE: Journal API lives in the STATIC namespace since Midnight 12.x
        # (verified 2026-09-03; dynamic-eu returns 404)
        return await self.get_game_data(
            "/data/wow/journal-instance/index", namespace=f"static-{self.region}"
        )

    async def journal_instance(self, instance_id: int) -> dict:
        return await self.get_game_data(
            f"/data/wow/journal-instance/{instance_id}", namespace=f"static-{self.region}"
        )

    async def journal_encounter(self, encounter_id: int) -> dict:
        return await self.get_game_data(
            f"/data/wow/journal-encounter/{encounter_id}", namespace=f"static-{self.region}"
        )

    async def item(self, item_id: int) -> dict:
        return await self.get_game_data(
            f"/data/wow/item/{item_id}", namespace=f"static-{self.region}"
        )

    async def mythic_keystone_seasons(self) -> dict:
        return await self.get_game_data("/data/wow/mythic-keystone/season/index")

    async def mythic_keystone_season(self, season_id: int) -> dict:
        return await self.get_game_data(f"/data/wow/mythic-keystone/season/{season_id}")

    async def mythic_keystone_periods(self) -> dict:
        return await self.get_game_data("/data/wow/mythic-keystone/period/index")

    async def realms(self) -> dict:
        return await self.get_game_data("/data/wow/realm/index")