"""Handlers for user settings (currency, extended history, etc.)."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback, show_or_edit
from keyboards.main_menu import (
    MENU_SETTINGS,
    SETTINGS_CURRENCY,
    SETTINGS_EXTENDED_HISTORY,
    settings_keyboard,
)
from keyboards.utils import safe_edit_text
from services.formatting import html_escape

router = Router()

CURRENCIES = ["грн", "₴", "USD", "EUR"]


async def _show_settings(target: Message, user_id: int, *, edit: bool = False) -> None:
    """Display the settings screen with current user preferences."""
    settings = await db.ensure_user(user_id)
    active = await db.get_active_car(user_id)
    ext_label = "✅ Увімкнено" if settings.extended_history else "❌ Вимкнено"
    text = (
        "⚙️ <b>Налаштування</b>\n\n"
        f"🚗 Активне авто: <b>{html_escape(active.name)}</b>\n"
        f"💱 Валюта: <b>{settings.currency}</b>\n"
        f"📐 Одиниці: <b>{settings.units}</b>\n"
        f"📊 Розширена історія: <b>{ext_label}</b>"
    )
    await show_or_edit(
        target,
        text,
        edit=edit,
        reply_markup=settings_keyboard(extended_history=settings.extended_history),
    )


@router.callback_query(F.data == MENU_SETTINGS)
@safe_callback
async def callback_settings(callback: CallbackQuery, state: FSMContext) -> None:
    """Show the settings screen from the main menu."""
    await state.clear()
    await callback.answer()
    await _show_settings(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == SETTINGS_EXTENDED_HISTORY)
@safe_callback
async def callback_toggle_extended_history(callback: CallbackQuery, state: FSMContext) -> None:
    settings = await db.ensure_user(callback.from_user.id)
    new_value = not settings.extended_history
    await db.update_user_settings(callback.from_user.id, extended_history=new_value)
    label = "увімкнено" if new_value else "вимкнено"
    await callback.answer(f"Розширена історія {label}")
    await _show_settings(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == SETTINGS_CURRENCY)
@safe_callback
async def callback_settings_currency(callback: CallbackQuery, state: FSMContext) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = [
        [InlineKeyboardButton(text=c, callback_data=f"settings:cur:{c}")]
        for c in CURRENCIES
    ]
    buttons.append([InlineKeyboardButton(text="🏠 Головне меню", callback_data="menu:home")])

    await callback.answer()
    await safe_edit_text(
        callback.message,
        "💱 Обери валюту:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("settings:cur:"))
@safe_callback
async def callback_set_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.split(":")[-1]
    await db.update_user_settings(callback.from_user.id, currency=currency)
    await state.clear()
    await callback.answer(f"Валюта: {currency}")
    await _show_settings(callback.message, callback.from_user.id, edit=True)
