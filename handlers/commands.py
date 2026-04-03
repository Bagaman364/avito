"""
General bot commands: /start, /help, /avanscheck
"""

from __future__ import annotations

import logging

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from avito_api import AvitoClient, AvitoAPIError
from avito_poller import get_client
from config import ADMIN_TELEGRAM_ID

log = logging.getLogger(__name__)
router = Router()


def _format_rub(amount: float) -> str:
    return f"{amount:,.0f} ₽".replace(",", " ")


async def _check_access(message: Message) -> bool:
    uid = message.from_user.id
    if uid == ADMIN_TELEGRAM_ID:
        return True
    if await db.is_member(uid):
        return True
    await message.answer("⛔ У вас нет доступа к этому боту.")
    return False


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = message.from_user
    uid = user.id
    username = user.username or ""

    # Auto-register pre-added members (added by username, id=0)
    pending = await db.get_member_by_username(username)
    if pending and pending["telegram_id"] == 0:
        await db.add_member(uid, username, pending.get("added_by", 0))

    is_admin = uid == ADMIN_TELEGRAM_ID
    is_member_ = await db.is_member(uid)

    if not is_admin and not is_member_:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return

    role = "Администратор" if is_admin else "Участник"
    await message.answer(
        f"👋 Привет, <b>{user.full_name}</b>!\n\n"
        f"Роль: {role}\n\n"
        "Доступные команды:\n"
        "/help — список команд",
        parse_mode="HTML",
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not await _check_access(message):
        return

    is_admin = message.from_user.id == ADMIN_TELEGRAM_ID

    common = (
        "📋 <b>Команды:</b>\n\n"
        "/avanscheck — баланс аванса по всем аккаунтам\n"
        "/members — список участников\n"
        "/accounts — список аккаунтов Авито\n"
    )
    admin_only = (
        "\n<b>Только для администратора:</b>\n"
        "/addmember @username — добавить участника\n"
        "/removemember @username — удалить участника\n"
        "/addaccount — добавить аккаунт Авито\n"
        "/deleteaccount — удалить аккаунт Авито\n"
        "/renameaccount — переименовать аккаунт\n"
    )

    text = common + (admin_only if is_admin else "")
    await message.answer(text, parse_mode="HTML")


# ── /avanscheck ───────────────────────────────────────────────────────────────

@router.message(Command("avanscheck"))
async def cmd_avanscheck(message: Message) -> None:
    if not await _check_access(message):
        return

    accounts = await db.get_all_avito_accounts()
    if not accounts:
        await message.answer("Нет подключённых аккаунтов Авито.")
        return

    status_msg = await message.answer("⏳ Получаю данные по балансам...")

    lines = ["💰 <b>Авансы по аккаунтам:</b>\n"]
    async with aiohttp.ClientSession() as session:
        for acc in accounts:
            client = get_client(acc["id"], acc["client_id"], acc["client_secret"])
            phone = acc.get("avito_phone", "")
            label = f"{acc['name']} ({phone})" if phone else acc["name"]
            try:
                user_id = acc.get("avito_user_id", "")
                balance = await client.get_balance(session, user_id)
                real = balance.get("real", 0)
                bonus = balance.get("bonus", 0)
                bal_text = _format_rub(real)
                if bonus:
                    bal_text += f" + {_format_rub(bonus)} бонусов"
                lines.append(f"• {label}: {bal_text}")
            except AvitoAPIError as e:
                log.warning("Balance error for account %s: %s", acc["id"], e)
                lines.append(f"• {label}: ❌ ошибка")

    await status_msg.edit_text("\n".join(lines), parse_mode="HTML")
