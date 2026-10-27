"""Handlers for statistics, last refuel view, and record deletion."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.archive import format_year_ranges, hidden_years_banner
from handlers.callback_guard import safe_callback, show_or_edit
from keyboards.main_menu import (
    LAST_DELETE,
    LAST_DELETE_CANCEL,
    LAST_DELETE_CONFIRM,
    MENU_LAST,
    MENU_STATS,
    STATS_PERIOD_ALL,
    STATS_PERIOD_PREFIX,
    last_delete_confirm_keyboard,
    last_refuel_keyboard,
    main_menu_keyboard,
    stats_keyboard,
)
from keyboards.utils import safe_edit_text
from services.calculations import calc_full_tank_trips, calc_overall_stats
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
    trip = calc_full_tank_trips(all_refuels).get(record.id)
    text = active_car_banner(car.name) + "\n" + format_last_refuel(
        record, previous, settings.currency, trip
    )
    await show_or_edit(target, text, edit=edit, reply_markup=last_refuel_keyboard())


async def _show_stats(
    target: Message,
    user_id: int,
    *,
    edit: bool = False,
    year: int | None = None,
) -> None:
    """Display statistics for the active car.

    Archived years are left out everywhere, the period switcher included.
    year=None covers all visible years and is labelled with their real range
    ("весь час" only when nothing is archived). Each period starts from zero:
    only its own refuels are counted.
    """
    car = await db.get_active_car(user_id)
    settings = await db.ensure_user(user_id)
    all_refuels = await db.get_all_refuels(user_id, car.id)
    data_years = {r.date.year for r in all_refuels}
    hidden = await db.get_hidden_years(car.id) & data_years
    visible_years = sorted(data_years - hidden, reverse=True)

    if not all_refuels:
        text = (
            active_car_banner(car.name)
            + "\n📭 Заправок ще немає.\n\nДодай першу заправку, щоб побачити статистику."
        )
        await show_or_edit(target, text, edit=edit, reply_markup=main_menu_keyboard())
        return

    banner = active_car_banner(car.name) + hidden_years_banner(hidden)
    all_label = format_year_ranges(set(visible_years)) if hidden else "Весь час"
    keyboard = stats_keyboard(visible_years, year, all_label=all_label)

    if not visible_years:
        text = (
            banner
            + f"\n📊 <b>Статистика — {html_escape(car.name)}</b>\n\n"
            "Усі роки приховано в архіві.\n"
            "Показати їх можна в «⚙️ Налаштування» → «🗄 Архів років»."
        )
        await show_or_edit(target, text, edit=edit, reply_markup=keyboard)
        return

    if year not in visible_years:
        year = None  # an archived year from an old button falls back to all visible years
    if year is None:
        refuels = [r for r in all_refuels if r.date.year not in hidden]
        period = all_label.lower() if not hidden else all_label
    else:
        refuels = [r for r in all_refuels if r.date.year == year]
        period = f"{year} рік"

    keyboard = stats_keyboard(visible_years, year, all_label=all_label)
    text = banner + "\n" + _format_stats(calc_overall_stats(refuels), settings, car.name, period)
    await show_or_edit(target, text, edit=edit, reply_markup=keyboard)


def _format_stats(stats, settings, car_name: str, period: str) -> str:
    """Build HTML text for the statistics screen."""
    currency = settings.currency
    lines = [
        f"📊 <b>Статистика — {html_escape(car_name)} · {period}</b>\n",
        f"🧾 Заправок: {fmt_num(stats.total_refuels, 0)}",
        f"📏 Пробіг за період: {fmt_num(stats.total_distance_km, 0)} км",
        f"🔢 Всього пального: {fmt_num(stats.total_liters)} л",
        f"💰 Всього витрачено: {fmt_num(stats.total_spent, 0)} {currency}",
    ]
    if stats.total_discount > 0:
        lines.append(
            f"🏷 Знижки: {fmt_num(stats.total_discount, 0)} {currency} "
            f"(сплачено {fmt_num(stats.total_spent - stats.total_discount, 0)} {currency})"
        )
    lines.append("")

    if stats.avg_consumption is not None:
        lines.append(f"🔥 Середня витрата: {fmt_num(stats.avg_consumption)} л / 100 км")
        if not stats.consumption_from_full_tanks:
            lines.append(
                "<i>Приблизно: немає двох заправок «повний бак» поспіль — "
                "точний розрахунок з’явиться після них.</i>"
            )
    if stats.avg_cost_per_100km is not None:
        lines.append(f"💸 Середня вартість 100 км: {fmt_num(stats.avg_cost_per_100km, 0)} {currency}")
    if stats.avg_cost_per_km is not None:
        lines.append(f"🪙 Середня вартість 1 км: {fmt_num(stats.avg_cost_per_km, 2)} {currency}")

    rhythm: list[str] = []
    if stats.km_per_month is not None:
        rhythm.append(f"🗓 Пробіг на місяць: ~{fmt_num(stats.km_per_month, 0)} км")
    if stats.spent_per_month is not None:
        rhythm.append(f"💳 Витрати на місяць: ~{fmt_num(stats.spent_per_month, 0)} {currency}")
    if stats.avg_days_between is not None:
        rhythm.append(f"⏱ Заправка в середньому раз на {fmt_num(stats.avg_days_between, 0)} дн.")
    if stats.avg_km_between is not None:
        rhythm.append(f"📏 Між заправками: ~{fmt_num(stats.avg_km_between, 0)} км")
    if rhythm:
        lines.extend(["", *rhythm])

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
        share = round(stats.most_common_station_count / stats.total_refuels * 100)
        lines.extend([
            "",
            f"⛽ Найчастіша АЗС: <b>{html_escape(stats.most_common_station)}</b> "
            f"<i>({stats.most_common_station_count} з {stats.total_refuels}, {share}%)</i>",
        ])
    if stats.most_common_fuel_type:
        lines.append(f"🧾 Найчастіше пальне: <b>{html_escape(stats.most_common_fuel_type)}</b>")

    if stats.period_start and stats.period_end:
        lines.extend([
            "",
            f"📅 Період: {fmt_date(stats.period_start)} — {fmt_date(stats.period_end)}",
        ])

    # Sections are optional, so collapse the blank separators they leave behind
    compact: list[str] = []
    for line in lines:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    return "\n".join(compact)


async def _delete_last_refuel(user_id: int) -> bool:
    """Delete the latest refuel for the active car; return whether a record was removed."""
    car = await db.get_active_car(user_id)
    deleted = await db.delete_last_refuel(user_id, car.id)
    return deleted is not None


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext) -> None:
    """Handle /stats — show aggregate fuel statistics."""
    await state.clear()
    await db.ensure_tg_user(message.from_user)
    await _show_stats(message, message.from_user.id)


@router.callback_query(F.data == MENU_STATS)
@safe_callback
async def callback_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.ensure_tg_user(callback.from_user)
    await callback.answer()
    await _show_stats(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data.startswith(STATS_PERIOD_PREFIX))
@safe_callback
async def callback_stats_period(callback: CallbackQuery, state: FSMContext) -> None:
    """Switch the statistics period (all visible years or one year)."""
    suffix = callback.data.removeprefix(STATS_PERIOD_PREFIX)
    year = None if callback.data == STATS_PERIOD_ALL else int(suffix) if suffix.isdigit() else None
    await callback.answer()
    await _show_stats(callback.message, callback.from_user.id, edit=True, year=year)


@router.message(Command("last"))
async def cmd_last(message: Message, state: FSMContext) -> None:
    """Handle /last — show the most recent refuel."""
    await state.clear()
    await db.ensure_tg_user(message.from_user)
    await _show_last(message, message.from_user.id)


@router.callback_query(F.data == MENU_LAST)
@safe_callback
async def callback_last(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.ensure_tg_user(callback.from_user)
    await callback.answer()
    await _show_last(callback.message, callback.from_user.id, edit=True)


def _delete_confirm_text(car_name: str, record, currency: str) -> str:
    """Confirmation prompt that names the refuel about to be deleted."""
    return (
        active_car_banner(car_name)
        + "\n"
        + DELETE_CONFIRM_TEXT
        + f"\n\n📅 {fmt_date(record.date)} · 🚗 {fmt_num(record.odometer_km, 0)} км · "
        f"🔢 {fmt_num(record.liters)} л · 💰 {fmt_num(record.total_price, 0)} {currency}"
    )


@router.callback_query(F.data == LAST_DELETE)
@safe_callback
async def callback_last_delete_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    car = await db.get_active_car(callback.from_user.id)
    record = await db.get_last_refuel(callback.from_user.id, car.id)
    if not record:
        await callback.answer("Немає записів для видалення", show_alert=True)
        await _show_last(callback.message, callback.from_user.id, edit=True)
        return

    settings = await db.ensure_user(callback.from_user.id)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        _delete_confirm_text(car.name, record, settings.currency),
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
async def cmd_delete_last(message: Message, state: FSMContext) -> None:
    """Handle /delete_last — ask for confirmation, same as the menu button."""
    await state.clear()
    user_id = message.from_user.id
    car = await db.get_active_car(user_id)
    record = await db.get_last_refuel(user_id, car.id)
    if not record:
        await message.answer(
            "📭 Немає записів для видалення.",
            reply_markup=main_menu_keyboard(),
        )
        return

    settings = await db.ensure_user(user_id)
    await message.answer(
        _delete_confirm_text(car.name, record, settings.currency),
        reply_markup=last_delete_confirm_keyboard(),
        parse_mode="HTML",
    )
