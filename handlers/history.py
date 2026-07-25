"""Handlers for paginated refuel history and in-history CSV export."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback, show_or_edit
from keyboards.main_menu import (
    HISTORY_EXPORT,
    HISTORY_GOTO,
    HISTORY_NOOP,
    MENU_HISTORY,
    history_empty_keyboard,
    history_keyboard,
)
from services.csv_export import csv_filename, export_refuels_to_csv
from services.formatting import active_car_banner, code, html_escape
from services.history_format import (
    EMPTY_HISTORY_TEXT,
    HISTORY_PER_PAGE,
    build_prev_map,
    format_history_page,
)

router = Router()


async def _show_history(target: Message, user_id: int, page: int, *, edit: bool = False) -> None:
    """Render one page of refuel history for the active car."""
    car = await db.get_active_car(user_id)
    total = await db.count_refuels(user_id, car.id)
    if total == 0:
        text = active_car_banner(car.name) + "\n" + EMPTY_HISTORY_TEXT
        await show_or_edit(
            target,
            text,
            edit=edit,
            reply_markup=history_empty_keyboard(),
        )
        return

    total_pages = (total + HISTORY_PER_PAGE - 1) // HISTORY_PER_PAGE
    page = max(0, min(page, total_pages - 1))

    refuels = await db.get_refuels_page(user_id, car.id, page, HISTORY_PER_PAGE)
    settings = await db.ensure_user(user_id)
    all_refuels = await db.get_all_refuels(user_id, car.id, ascending=True)
    prev_map = build_prev_map(all_refuels)

    result = format_history_page(
        refuels,
        prev_map,
        page,
        total_pages,
        settings.currency,
        per_page=HISTORY_PER_PAGE,
        extended_history=settings.extended_history,
    )

    text = active_car_banner(car.name) + "\n" + result.text
    keyboard = history_keyboard(page, total_pages)
    await show_or_edit(target, text, edit=edit, reply_markup=keyboard)


@router.message(Command("history"))
async def cmd_history(message: Message, state: FSMContext) -> None:
    """Handle /history — show the first page of refuel history."""
    await state.clear()
    await db.ensure_tg_user(message.from_user)
    await _show_history(message, message.from_user.id, page=0)


@router.callback_query(F.data == MENU_HISTORY)
@safe_callback
async def callback_history(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.ensure_tg_user(callback.from_user)
    await callback.answer()
    await _show_history(callback.message, callback.from_user.id, page=0, edit=True)


@router.callback_query(F.data.startswith(HISTORY_GOTO))
@safe_callback
async def callback_history_goto(callback: CallbackQuery) -> None:
    try:
        page = int(callback.data.removeprefix(HISTORY_GOTO))
    except ValueError:
        await callback.answer()
        return
    await callback.answer()
    await _show_history(callback.message, callback.from_user.id, page=page, edit=True)


@router.callback_query(F.data == HISTORY_NOOP)
@safe_callback
async def callback_history_noop(callback: CallbackQuery) -> None:
    """Page indicator — acknowledge without changing the view."""
    await callback.answer()


@router.callback_query(F.data == HISTORY_EXPORT)
@safe_callback
async def callback_history_export(callback: CallbackQuery, state: FSMContext) -> None:
    """Export active car history to CSV from the history screen."""
    await callback.answer()
    user_id = callback.from_user.id
    car = await db.get_active_car(user_id)
    refuels = await db.get_all_refuels(user_id, car.id, ascending=False)

    if not refuels:
        await callback.message.answer(
            active_car_banner(car.name) + "\nНемає даних для експорту.",
            reply_markup=history_empty_keyboard(),
            parse_mode="HTML",
        )
        return

    document = BufferedInputFile(
        export_refuels_to_csv(refuels, car_name=car.name),
        filename=csv_filename(car.name),
    )
    await callback.message.answer_document(
        document,
        caption=(
            f"📁 Експорт для <b>{html_escape(car.name)}</b>\n"
            f"Записів: {code(len(refuels))}"
        ),
        parse_mode="HTML",
    )
    total = len(refuels)
    total_pages = max(1, (total + HISTORY_PER_PAGE - 1) // HISTORY_PER_PAGE)
    await callback.message.answer(
        "Експорт готовий.",
        reply_markup=history_keyboard(0, total_pages),
        parse_mode="HTML",
    )
