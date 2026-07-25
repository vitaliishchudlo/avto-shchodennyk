"""Handlers for exporting refuel history to CSV (/export command)."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

import database as db
from keyboards.main_menu import history_empty_keyboard, home_button_keyboard
from services.csv_export import csv_filename, export_refuels_to_csv
from services.formatting import active_car_banner, code, html_escape

router = Router()

EMPTY_EXPORT_TEXT = "Немає даних для експорту."


@router.message(Command("export"))
async def cmd_export(message: Message, state: FSMContext) -> None:
    """Handle /export — send active car history as CSV (newest first)."""
    await state.clear()
    user_id = message.from_user.id
    car = await db.get_active_car(user_id)
    refuels = await db.get_all_refuels(user_id, car.id, ascending=False)

    if not refuels:
        await message.answer(
            active_car_banner(car.name) + "\n" + EMPTY_EXPORT_TEXT,
            reply_markup=history_empty_keyboard(),
            parse_mode="HTML",
        )
        return

    document = BufferedInputFile(
        export_refuels_to_csv(refuels, car_name=car.name),
        filename=csv_filename(car.name),
    )
    await message.answer_document(
        document,
        caption=(
            f"📁 Експорт для <b>{html_escape(car.name)}</b>\n"
            f"Записів: {code(len(refuels))}"
        ),
        parse_mode="HTML",
    )
    await message.answer(
        "Експорт готовий.",
        reply_markup=home_button_keyboard(),
        parse_mode="HTML",
    )
