"""Handlers for statistics, last refuel view, and record deletion."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback, show_or_edit
from keyboards.main_menu import (
    LAST_DELETE,
    LAST_DELETE_CANCEL,
    LAST_DELETE_CONFIRM,
    MENU_LAST,
    MENU_STATS,
    last_delete_confirm_keyboard,
    last_refuel_keyboard,
    main_menu_keyboard,
)
from keyboards.utils import safe_edit_text
from services.calculations import calc_overall_stats
from services.formatting import active_car_banner, fmt_date, fmt_num, html_escape
from services.history_format import format_last_refuel

router = Router()

EMPTY_LAST_TEXT = (
    "⛽ <b>Остання заправка</b>\n\n"
    "Ще немає даних для відображення.\n"
    "Додай першу заправку ➕"
)

DELETE_CONFIRM_TEXT = "⚠️ <b>Видалити останню заправку?</b>"


async def _show_last(target: Message, user_id: int, *, edit: bool = False) -> None:
    """Display the most recent refuel for the active car."""
    car = await db.get_active_car(user_id)
    settings = await db.ensure_user(user_id)
    record = await db.get_last_refuel(user_id, car.id)

    if not record:
        text = active_car_banner(car.name) + "\n" + EMPTY_LAST_TEXT
        await show_or_edit(
            target,
            text,
            edit=edit,
            reply_markup=main_menu_keyboard(),
        )
        return

    all_refuels = await db.get_all_refuels(user_id, car.id)
    previous = all_refuels[-2] if len(all_refuels) >= 2 else None
    text = active_car_banner(car.name) + "\n" + format_last_refuel(record, previous, settings.currency)
    await show_or_edit(target, text, edit=edit, reply_markup=last_refuel_keyboard())


async def _show_stats(target: Message, user_id: int, *, edit: bool = False) -> None:
    """Display aggregate fuel statistics for the active car."""
    car = await db.get_active_car(user_id)
    settings = await db.ensure_user(user_id)
    refuels = await db.get_all_refuels(user_id, car.id)
    stats = calc_overall_stats(refuels)

    if stats.total_refuels == 0:
        text = (
            active_car_banner(car.name)
            + "\n📭 Заправок ще немає.\n\nДодай першу заправку, щоб побачити статистику."
        )
        keyboard = main_menu_keyboard()
    else:
        text = active_car_banner(car.name) + "\n" + _format_stats(stats, settings, car.name)
        from keyboards.main_menu import home_button_keyboard

        keyboard = home_button_keyboard()

    await show_or_edit(target, text, edit=edit, reply_markup=keyboard)


def _format_stats(stats, settings, car_name: str) -> str:
    """Build HTML text for the statistics screen."""
    currency = settings.currency
    lines = [
        f"📊 <b>Статистика — {html_escape(car_name)}</b>\n",
        f"🧾 Заправок: {fmt_num(stats.total_refuels, 0)}",
        f"📏 Пробіг за період: {fmt_num(stats.total_distance_km, 0)} км",
        f"🔢 Всього пального: {fmt_num(stats.total_liters)} л",
        f"💰 Всього витрачено: {fmt_num(stats.total_spent, 0)} {currency}",
        "",
    ]

    if stats.avg_consumption is not None:
        lines.append(f"🔥 Середня витрата: {fmt_num(stats.avg_consumption)} л / 100 км")
    if stats.avg_cost_per_100km is not None:
        lines.append(f"💸 Середня вартість 100 км: {fmt_num(stats.avg_cost_per_100km, 0)} {currency}")
    if stats.avg_cost_per_km is not None:
        lines.append(f"🪙 Середня вартість 1 км: {fmt_num(stats.avg_cost_per_km, 2)} {currency}")

    lines.append(f"💵 Середня ціна за літр: {fmt_num(stats.avg_price_per_liter)} {currency}")

    if stats.most_expensive:
        lines.extend([
            "",
            f"💎 Найдорожча: {fmt_num(stats.most_expensive.total_price, 0)} {currency} "
            f"({fmt_date(stats.most_expensive.date)})",
        ])
    if stats.largest_liters:
        lines.append(
            f"🛢 Найбільша: {fmt_num(stats.largest_liters.liters)} л "
            f"({fmt_date(stats.largest_liters.date)})"
        )

    if stats.most_common_station:
        lines.extend(["", f"📍 Найчастіша АЗС: <b>{html_escape(stats.most_common_station)}</b>"])
    if stats.most_common_fuel_type:
        lines.append(f"🔧 Найчастіший тип: <b>{html_escape(stats.most_common_fuel_type)}</b>")
    if stats.most_common_fuel_product:
        lines.append(f"🧾 Найчастіше пальне: <b>{html_escape(stats.most_common_fuel_product)}</b>")

    if stats.avg_price_by_fuel_type:
        lines.append("")
        lines.append("<b>Середня ціна за літр:</b>")
        for fuel_type, price in sorted(stats.avg_price_by_fuel_type.items()):
            lines.append(f"  • {html_escape(fuel_type)}: {fmt_num(price)} {currency}")

    if stats.period_start and stats.period_end:
        lines.extend([
            "",
            f"📅 Період: {fmt_date(stats.period_start)} — {fmt_date(stats.period_end)}",
        ])

    return "\n".join(lines)


async def _delete_last_refuel(user_id: int) -> bool:
    """Delete the latest refuel for the active car; return whether a record was removed."""
    car = await db.get_active_car(user_id)
    deleted = await db.delete_last_refuel(user_id, car.id)
    return deleted is not None


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext) -> None:
    """Handle /stats — show aggregate fuel statistics."""
    await state.clear()
    await _show_stats(message, message.from_user.id)


@router.callback_query(F.data == MENU_STATS)
@safe_callback
async def callback_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_stats(callback.message, callback.from_user.id, edit=True)


@router.message(Command("last"))
async def cmd_last(message: Message, state: FSMContext) -> None:
    """Handle /last — show the most recent refuel."""
    await state.clear()
    await _show_last(message, message.from_user.id)


@router.callback_query(F.data == MENU_LAST)
@safe_callback
async def callback_last(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_last(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == LAST_DELETE)
@safe_callback
async def callback_last_delete_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    car = await db.get_active_car(callback.from_user.id)
    record = await db.get_last_refuel(callback.from_user.id, car.id)
    if not record:
        await callback.answer("Немає записів для видалення", show_alert=True)
        await _show_last(callback.message, callback.from_user.id, edit=True)
        return

    await callback.answer()
    await safe_edit_text(
        callback.message,
        active_car_banner(car.name) + "\n" + DELETE_CONFIRM_TEXT,
        reply_markup=last_delete_confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == LAST_DELETE_CANCEL)
@safe_callback
async def callback_last_delete_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _show_last(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == LAST_DELETE_CONFIRM)
@safe_callback
async def callback_last_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    deleted = await _delete_last_refuel(callback.from_user.id)
    await callback.answer("Видалено" if deleted else "Немає записів")
    await _show_last(callback.message, callback.from_user.id, edit=True)


@router.message(Command("delete_last"))
async def cmd_delete_last(message: Message) -> None:
    deleted_ok = await _delete_last_refuel(message.from_user.id)
    if not deleted_ok:
        await message.answer(
            "📭 Немає записів для видалення.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _show_last(message, message.from_user.id)
