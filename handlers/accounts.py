"""
Handlers for Avito account management.

/addaccount     — step-by-step dialog: client_id → client_secret → name
/accounts       — list connected accounts
/deleteaccount  — choose and delete an account
/renameaccount  — rename an account
"""

from __future__ import annotations

import logging

import aiohttp
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import database as db
from avito_api import AvitoClient, AvitoAPIError
from avito_poller import invalidate_client
from config import ADMIN_TELEGRAM_ID

log = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_TELEGRAM_ID


# ── FSM states ────────────────────────────────────────────────────────────────

class AddAccount(StatesGroup):
    waiting_client_id = State()
    waiting_client_secret = State()
    waiting_name = State()


class DeleteAccount(StatesGroup):
    waiting_choice = State()


class RenameAccount(StatesGroup):
    waiting_choice = State()
    waiting_new_name = State()


# ── /addaccount ───────────────────────────────────────────────────────────────

@router.message(Command("addaccount"))
async def cmd_addaccount(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может добавлять аккаунты.")
        return

    await state.set_state(AddAccount.waiting_client_id)
    await message.answer(
        "🔑 <b>Добавление аккаунта Авито</b>\n\n"
        "Шаг 1/3: Введите <b>Client ID</b> из кабинета разработчика Авито:",
        parse_mode="HTML",
    )


@router.message(AddAccount.waiting_client_id)
async def process_client_id(message: Message, state: FSMContext) -> None:
    cid = message.text.strip()
    if not cid:
        await message.answer("Client ID не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(client_id=cid)
    await state.set_state(AddAccount.waiting_client_secret)
    await message.answer("Шаг 2/3: Введите <b>Client Secret</b>:", parse_mode="HTML")


@router.message(AddAccount.waiting_client_secret)
async def process_client_secret(message: Message, state: FSMContext) -> None:
    secret = message.text.strip()
    if not secret:
        await message.answer("Client Secret не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(client_secret=secret)
    await state.set_state(AddAccount.waiting_name)
    await message.answer(
        "Шаг 3/3: Введите <b>имя аккаунта</b> (например: Богдан, Магазин Электро):",
        parse_mode="HTML",
    )


@router.message(AddAccount.waiting_name)
async def process_account_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    await state.clear()

    processing_msg = await message.answer("⏳ Проверяю ключи, подождите...")

    client_id = data["client_id"]
    client_secret = data["client_secret"]

    client = AvitoClient(client_id, client_secret)
    try:
        async with aiohttp.ClientSession() as session:
            self_info = await client.authenticate_and_get_self(session)
    except AvitoAPIError as e:
        await processing_msg.edit_text(
            f"❌ Ошибка авторизации:\n<code>{e}</code>\n\nПроверьте ключи и попробуйте /addaccount снова.",
            parse_mode="HTML",
        )
        return
    except Exception as e:
        log.exception("Unexpected error while adding account")
        await processing_msg.edit_text(f"❌ Неожиданная ошибка: {e}")
        return

    avito_user_id = str(self_info.get("id", ""))
    avito_phone = self_info.get("phone", "")

    account_id = await db.add_avito_account(
        name=name,
        client_id=client_id,
        client_secret=client_secret,
        added_by=message.from_user.id,
    )
    await db.update_account_token(
        account_id,
        client.access_token or "",
        client.expires_at,
        avito_user_id,
        avito_phone,
    )

    label = f"{name}({avito_phone})" if avito_phone else name
    await processing_msg.edit_text(
        f"✅ Аккаунт <b>{label}</b> успешно добавлен!\n"
        f"Авито ID: <code>{avito_user_id}</code>",
        parse_mode="HTML",
    )


# ── /accounts ─────────────────────────────────────────────────────────────────

@router.message(Command("accounts"))
async def cmd_accounts(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может просматривать аккаунты.")
        return

    accounts = await db.get_all_avito_accounts()
    if not accounts:
        await message.answer("Нет подключённых аккаунтов Авито.")
        return

    lines = ["📋 <b>Подключённые аккаунты Авито:</b>\n"]
    for acc in accounts:
        phone = acc.get("avito_phone", "")
        label = f"{acc['name']}({phone})" if phone else acc["name"]
        lines.append(f"• [#{acc['id']}] {label}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /deleteaccount ────────────────────────────────────────────────────────────

@router.message(Command("deleteaccount"))
async def cmd_deleteaccount(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может удалять аккаунты.")
        return

    accounts = await db.get_all_avito_accounts()
    if not accounts:
        await message.answer("Нет подключённых аккаунтов для удаления.")
        return

    buttons = []
    for acc in accounts:
        phone = acc.get("avito_phone", "")
        label = f"{acc['name']}({phone})" if phone else acc["name"]
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {label}",
                callback_data=f"del_acc:{acc['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="del_acc:cancel")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await state.set_state(DeleteAccount.waiting_choice)
    await message.answer("Выберите аккаунт для удаления:", reply_markup=kb)


@router.callback_query(DeleteAccount.waiting_choice, F.data.startswith("del_acc:"))
async def process_delete_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    value = callback.data.split(":", 1)[1]

    if value == "cancel":
        await callback.message.edit_text("Удаление отменено.")
        await callback.answer()
        return

    account_id = int(value)
    account = await db.get_avito_account(account_id)
    if not account:
        await callback.message.edit_text("Аккаунт не найден.")
        await callback.answer()
        return

    await db.delete_avito_account(account_id)
    invalidate_client(account_id)

    phone = account.get("avito_phone", "")
    label = f"{account['name']}({phone})" if phone else account["name"]
    await callback.message.edit_text(f"✅ Аккаунт <b>{label}</b> удалён.", parse_mode="HTML")
    await callback.answer()


# ── /renameaccount ────────────────────────────────────────────────────────────

@router.message(Command("renameaccount"))
async def cmd_renameaccount(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может переименовывать аккаунты.")
        return

    accounts = await db.get_all_avito_accounts()
    if not accounts:
        await message.answer("Нет подключённых аккаунтов.")
        return

    buttons = []
    for acc in accounts:
        phone = acc.get("avito_phone", "")
        label = f"{acc['name']}({phone})" if phone else acc["name"]
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"ren_acc:{acc['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="ren_acc:cancel")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await state.set_state(RenameAccount.waiting_choice)
    await message.answer("Выберите аккаунт для переименования:", reply_markup=kb)


@router.callback_query(RenameAccount.waiting_choice, F.data.startswith("ren_acc:"))
async def process_rename_choice(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]

    if value == "cancel":
        await state.clear()
        await callback.message.edit_text("Переименование отменено.")
        await callback.answer()
        return

    account_id = int(value)
    await state.update_data(account_id=account_id)
    await state.set_state(RenameAccount.waiting_new_name)
    await callback.message.edit_text("Введите новое имя аккаунта:")
    await callback.answer()


@router.message(RenameAccount.waiting_new_name)
async def process_new_name(message: Message, state: FSMContext) -> None:
    new_name = message.text.strip()
    if not new_name:
        await message.answer("Имя не может быть пустым. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    await state.clear()

    await db.update_account_name(data["account_id"], new_name)
    await message.answer(f"✅ Аккаунт переименован в <b>{new_name}</b>.", parse_mode="HTML")
