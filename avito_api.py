"""
Async Avito API client.

Авито использует OAuth2 client_credentials flow:
  POST https://api.avito.ru/token
  →  { access_token, expires_in, token_type }

Основные эндпоинты, которые нам нужны:
  GET  /core/v1/accounts/self          — информация об аккаунте (id, phone, balance)
  GET  /messenger/v3/accounts/{uid}/chats        — список чатов
  GET  /messenger/v3/accounts/{uid}/chats/{cid}/messages — сообщения чата
"""

from __future__ import annotations

import time
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

AVITO_BASE = "https://api.avito.ru"
TOKEN_URL = f"{AVITO_BASE}/token"


class AvitoAPIError(Exception):
    pass


class AvitoClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._expires_at: int = 0

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _ensure_token(self, session: aiohttp.ClientSession) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with session.post(TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AvitoAPIError(f"Token error {resp.status}: {body}")
            js = await resp.json()

        self._access_token = js["access_token"]
        self._expires_at = int(time.time()) + js.get("expires_in", 86400)
        log.debug("Token refreshed for client_id=%s", self.client_id)
        return self._access_token

    async def _get(
        self, session: aiohttp.ClientSession, path: str, **params: Any
    ) -> Any:
        token = await self._ensure_token(session)
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{AVITO_BASE}{path}"
        async with session.get(url, headers=headers, params=params or None) as resp:
            if resp.status == 401:
                # Token might have been revoked — force refresh once
                self._expires_at = 0
                token = await self._ensure_token(session)
                headers["Authorization"] = f"Bearer {token}"
                async with session.get(url, headers=headers, params=params or None) as r2:
                    if r2.status != 200:
                        body = await r2.text()
                        raise AvitoAPIError(f"GET {path} error {r2.status}: {body}")
                    return await r2.json()
            if resp.status != 200:
                body = await resp.text()
                raise AvitoAPIError(f"GET {path} error {resp.status}: {body}")
            return await resp.json()

    # ── Account self ──────────────────────────────────────────────────────────

    async def get_self(self, session: aiohttp.ClientSession) -> dict:
        """Returns account info: id, name, phone, balance (wallet + bonus)."""
        return await self._get(session, "/core/v1/accounts/self")

    # ── Wallet / advance balance ──────────────────────────────────────────────

    async def get_balance(self, session: aiohttp.ClientSession) -> dict:
        """
        Returns wallet balance.
        Response: { "real": <float>, "bonus": <float> }
        """
        data = await self._get(session, "/core/v1/accounts/self")
        return {
            "real": data.get("wallet", 0),
            "bonus": data.get("bonus", 0),
        }

    # ── Chats ─────────────────────────────────────────────────────────────────

    async def get_chats(
        self,
        session: aiohttp.ClientSession,
        user_id: str,
        unread_only: bool = False,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": 100}
        if unread_only:
            params["unread_only"] = 1
        data = await self._get(
            session, f"/messenger/v3/accounts/{user_id}/chats", **params
        )
        return data.get("chats", [])

    # ── Messages ──────────────────────────────────────────────────────────────

    async def get_messages(
        self,
        session: aiohttp.ClientSession,
        user_id: str,
        chat_id: str,
        limit: int = 20,
    ) -> list[dict]:
        data = await self._get(
            session,
            f"/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages",
            limit=limit,
        )
        return data.get("messages", [])

    # ── Convenience: token + self in one call ─────────────────────────────────

    async def authenticate_and_get_self(
        self, session: aiohttp.ClientSession
    ) -> dict:
        """Used when adding a new account — validates keys and gets phone/id."""
        return await self.get_self(session)

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def expires_at(self) -> int:
        return self._expires_at
