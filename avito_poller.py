"""
Background polling loop.

Every POLL_INTERVAL seconds it:
1. Loads all Avito accounts from DB.
2. For each account fetches recent chats.
3. For each chat fetches messages.
4. Sends new (unprocessed) messages to all Telegram members.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

import database as db
from avito_api import AvitoClient, AvitoAPIError
from config import POLL_INTERVAL
from notifications import build_notification

log = logging.getLogger(__name__)

# Global reference injected by bot.py at startup
_bot = None
_clients: dict[int, AvitoClient] = {}  # account_id → client


def set_bot(bot) -> None:
    global _bot
    _bot = bot


def get_client(account_id: int, client_id: str, client_secret: str) -> AvitoClient:
    """Return cached client or create a new one."""
    if account_id not in _clients:
        _clients[account_id] = AvitoClient(client_id, client_secret)
    return _clients[account_id]


def invalidate_client(account_id: int) -> None:
    _clients.pop(account_id, None)


async def _process_account(
    session: aiohttp.ClientSession,
    account: dict,
) -> None:
    client = get_client(account["id"], account["client_id"], account["client_secret"])

    # Ensure we have user_id (needed for messenger API)
    user_id = account.get("avito_user_id")
    if not user_id:
        try:
            self_info = await client.get_self(session)
            user_id = str(self_info["id"])
            phone = self_info.get("phone", "")
            await db.update_account_token(
                account["id"],
                client.access_token or "",
                client.expires_at,
                user_id,
                phone,
            )
        except AvitoAPIError as e:
            log.warning("Cannot get self for account %s: %s", account["id"], e)
            return

    try:
        chats = await client.get_chats(session, user_id)
    except AvitoAPIError as e:
        log.warning("Cannot fetch chats for account %s: %s", account["id"], e)
        return

    members = await db.get_all_members()
    if not members:
        return

    for chat in chats:
        chat_id = chat.get("id")
        if not chat_id:
            continue

        try:
            messages = await client.get_messages(session, user_id, chat_id, limit=10)
        except AvitoAPIError as e:
            log.debug("Cannot fetch messages for chat %s: %s", chat_id, e)
            continue

        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue

            # Only process messages NOT sent by the account owner
            author = msg.get("author", {})
            if str(author.get("id")) == str(user_id):
                continue

            unique_key = f"{account['id']}_{chat_id}_{msg_id}"
            if await db.is_message_processed(unique_key):
                continue

            await db.mark_message_processed(unique_key)

            # Build and send notification
            text = build_notification(account, chat, msg)
            for member in members:
                try:
                    await _bot.send_message(member["telegram_id"], text, parse_mode="HTML")
                except Exception as e:
                    log.warning(
                        "Failed to send notification to %s: %s",
                        member["telegram_id"],
                        e,
                    )


async def polling_loop() -> None:
    """Main polling coroutine — run as asyncio task."""
    log.info("Avito poller started (interval=%ss)", POLL_INTERVAL)
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            try:
                accounts = await db.get_all_avito_accounts()
                tasks = [_process_account(session, acc) for acc in accounts]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await db.cleanup_old_processed(days=30)
            except Exception as e:
                log.exception("Unexpected error in polling loop: %s", e)
            await asyncio.sleep(POLL_INTERVAL)
