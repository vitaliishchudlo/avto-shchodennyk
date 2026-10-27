"""Per-car archive of years hidden from history and statistics."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback
from keyboards.main_menu import (
    ARCHIVE_HIDE_ALL,
    ARCHIVE_SHOW_ALL,
    ARCHIVE_TOGGLE_PREFIX,
    SETTINGS_ARCHIVE,
    archive_keyboard,
)
from keyboards.utils import safe_edit_text
from services.formatting import html_escape

router = Router()


def format_year_ranges(years: set[int]) -> str:
    """Compact list of years: consecutive runs collapse, e.g. "2020, 2022–2024"."""
    parts: list[str] = []
    ordered = sorted(years)
    start = prev = None
    for year in [*ordered, None]:
        if year is not None and prev is not None and year == prev + 1:
            prev = year
            continue
        if start is not None:
            parts.append(str(start) if start == prev else f"{start}–{prev}")
        start = prev = year
    return ", ".join(parts)


def _years_word(count: int) -> str:
    """Ukrainian plural of "рік" for a count."""
    if count % 10 == 1 and count % 100 != 11:
        return "рік"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "роки"
    return "років"


def hidden_years_banner(hidden: set[int]) -> str:
    """One-line reminder shown on history / statistics while some years are archived."""
    if not hidden:
        return ""
    return (
        f"🗄 <i>В архіві: {format_year_ranges(hidden)} "
        f"({len(hidden)} {_years_word(len(hidden))})</i>\n"
    )


async def _show_archive(target: Message, user_id: int) -> None:
    car = await db.get_active_car(user_id)
    years = await db.get_refuel_years(user_id, car.id)
    hidden = await db.get_hidden_years(car.id)

    lines = [
        "🗄 <b>Архів років</b>\n",
        f"🚗 Авто: <b>{html_escape(car.name)}</b>\n",
        "Приховані роки (🙈) не показуються в історії та статистиці — "
        "наприклад, щоб почати статистику нового року з нуля.\n",
        "<i>Дані не видаляються: заправки зберігаються, перевірки пробігу їх враховують, "
        "а експорт CSV завжди містить усі записи.</i>",
    ]
    if years:
        lines.append("\nНатисни на рік, щоб сховати або показати його.")
    else:
        lines.append("\n📭 Заправок ще немає.")

    await safe_edit_text(
        target,
        "\n".join(lines),
        reply_markup=archive_keyboard(years, hidden),
        parse_mode="HTML",
    )


@router.callback_query(F.data == SETTINGS_ARCHIVE)
@safe_callback
async def callback_archive(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_archive(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith(ARCHIVE_TOGGLE_PREFIX))
@safe_callback
async def callback_archive_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        year = int(callback.data.removeprefix(ARCHIVE_TOGGLE_PREFIX))
    except ValueError:
        await callback.answer()
        return

    car = await db.get_active_car(callback.from_user.id)
    hidden = await db.get_hidden_years(car.id)
    if year in hidden:
        hidden.discard(year)
        await callback.answer(f"{year} знову видно")
    else:
        hidden.add(year)
        await callback.answer(f"{year} приховано")
    await db.set_hidden_years(car.id, hidden)
    await _show_archive(callback.message, callback.from_user.id)


@router.callback_query(F.data.in_({ARCHIVE_SHOW_ALL, ARCHIVE_HIDE_ALL}))
@safe_callback
async def callback_archive_bulk(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    car = await db.get_active_car(user_id)
    if callback.data == ARCHIVE_SHOW_ALL:
        await db.set_hidden_years(car.id, set())
        await callback.answer("Усі роки видно")
    else:
        years = {year for year, _ in await db.get_refuel_years(user_id, car.id)}
        await db.set_hidden_years(car.id, years)
        await callback.answer("Усі роки приховано")
    await _show_archive(callback.message, user_id)
