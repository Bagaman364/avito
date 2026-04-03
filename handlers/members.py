"""
Handlers for member management.

/addmember @username   — add a Telegram user by username
/removemember @username — remove a member
/members               — list all members
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from config import ADMIN_TELEGRAM_ID

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_TELEGRAM_ID


async def _check_access(message: Message) -> bool:
    uid = message.from_user.id
    if _is_admin(uid):
        return True
    if await db.is_member(uid):
        return True
    await message.answer("⛔ У вас нет доступа к этому боту.")
    return False


@router.message(Command("addmember"))
async def cmd_addmember(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может добавлять участников.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /addmember @username")
        return

    raw = args[1].strip().lstrip("@")
    if not raw:
        await message.answer("Укажите корректный username.")
        return

    # We store username; telegram_id is unknown until user writes to bot.
    # For now store username with id=0 as placeholder — will be updated on /start.
    existing = await db.get_member_by_username(raw)
    if existing:
        await message.answer(f"Пользователь @{raw} уже добавлен.")
        return

    # We need telegram_id; ask admin to have the user /start the bot first.
    # As a shortcut we store username with id placeholder 0 — the user must /start.
    await db.add_member(0, raw, message.from_user.id)
    await message.answer(
        f"✅ Пользователь @{raw} добавлен.\n"
        "Попросите его написать /start боту, чтобы активировать доступ."
    )


@router.message(Command("removemember"))
async def cmd_removemember(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может удалять участников.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /removemember @username")
        return

    raw = args[1].strip().lstrip("@")
    member = await db.get_member_by_username(raw)
    if not member:
        await message.answer(f"Участник @{raw} не найден.")
        return

    await db.remove_member(member["telegram_id"])
    await message.answer(f"✅ Участник @{raw} удалён.")


@router.message(Command("members"))
async def cmd_members(message: Message) -> None:
    if not await _check_access(message):
        return

    members = await db.get_all_members()
    if not members:
        await message.answer("Список участников пуст.")
        return

    lines = ["👥 <b>Участники:</b>\n"]
    for m in members:
        uname = f"@{m['username']}" if m.get("username") else "—"
        tid = m["telegram_id"] if m["telegram_id"] else "не активирован"
        lines.append(f"• {uname} (id: {tid})")

    await message.answer("\n".join(lines), parse_mode="HTML")
