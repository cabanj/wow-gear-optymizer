"""Blizzard OAuth: authorization-code flow (user) + client-credentials (app-only).

Tokens stay server-side; browser only ever sees a signed session cookie.
"""
import base64
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet

from ..config import get_settings

SCOPE_WOW_PROFILE = "wow.profile"


class BlizzardOAuth:
    def __init__(self) -> None:
        s = get_settings()
        self.client_id = s.blizzard_client_id
        self.client_secret = s.blizzard_client_secret
        self.oauth_host = s.oauth_host
        self.redirect_uri = f"{s.base_url}/auth/blizzard/callback"

    def authorize_url(self, state: str) -> str:
        params = urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPE_WOW_PROFILE,
            "state": state,
        })
        return f"https://{self.oauth_host}/authorize?{params}"

    async def exchange_code(self, code: str) -> dict:
        return await self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        })

    async def refresh(self, refresh_token: str) -> dict:
        return await self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })

    async def client_credentials(self) -> dict:
        return await self._token_request({"grant_type": "client_credentials"})

    async def _token_request(self, data: dict) -> dict:
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://{self.oauth_host}/token",
                data=data,
                headers={"Authorization": f"Basic {basic}"},
            )
            resp.raise_for_status()
            return resp.json()


def new_state() -> str:
    return secrets.token_urlsafe(32)


class TokenStore:
    """Encrypts tokens at rest with Fernet. Only ciphertext touches the DB."""

    def __init__(self) -> None:
        self._fernet = Fernet(get_settings().secret_key.encode())

    def encrypt(self, tokens: dict) -> bytes:
        import json
        return self._fernet.encrypt(json.dumps(tokens).encode())

    def decrypt(self, blob: bytes) -> dict:
        import json
        return json.loads(self._fernet.decrypt(blob))

    @staticmethod
    def is_expired(tokens: dict, skew: int = 60) -> bool:
        return time.time() >= tokens.get("expires_at", 0) - skew