"""Handlers for paginated refuel history."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback, show_or_edit
from keyboards.main_menu import (
    HISTORY_NEXT,
    HISTORY_PREV,
    MENU_HISTORY,
    history_keyboard,
    main_menu_keyboard,
)
from services.formatting import active_car_banner
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
            reply_markup=main_menu_keyboard(),
        )
        return

    total_pages = (total + HISTORY_PER_PAGE - 1) // HISTORY_PER_PAGE
    page = max(0, min(page, total_pages - 1))

    refuels = await db.get_refuels_page(user_id, car.id, page, HISTORY_PER_PAGE)
    settings = await db.ensure_user(user_id)
    all_refuels = await db.get_all_refuels(user_id, car.id)
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
    await _show_history(message, message.from_user.id, page=0)


@router.callback_query(F.data == MENU_HISTORY)
@safe_callback
async def callback_history(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_history(callback.message, callback.from_user.id, page=0, edit=True)


@router.callback_query(F.data.startswith(f"{HISTORY_PREV}:"))
@safe_callback
async def callback_history_prev(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[-1])
    await callback.answer()
    await _show_history(callback.message, callback.from_user.id, page=page, edit=True)


@router.callback_query(F.data.startswith(f"{HISTORY_NEXT}:"))
@safe_callback
async def callback_history_next(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[-1])
    await callback.answer()
    await _show_history(callback.message, callback.from_user.id, page=page, edit=True)
