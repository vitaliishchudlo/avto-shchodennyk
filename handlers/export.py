"""Handlers for exporting refuel history to CSV."""

from aiogram import F, Router

from aiogram.filters import Command

from aiogram.fsm.context import FSMContext

from aiogram.types import BufferedInputFile, CallbackQuery, Message



import database as db

from handlers.callback_guard import safe_callback, show_or_edit

from keyboards.main_menu import MENU_EXPORT, home_button_keyboard, main_menu_keyboard

from services.csv_export import csv_filename, export_refuels_to_csv

from services.formatting import active_car_banner, code, html_escape



router = Router()



EMPTY_EXPORT_TEXT = "📁 Немає даних для експорту."





async def _send_export(target: Message, user_id: int, *, edit: bool = False) -> None:

    """Generate and send a CSV export for the active car's refuels."""
    car = await db.get_active_car(user_id)

    settings = await db.ensure_user(user_id)

    refuels = await db.get_all_refuels(user_id, car.id)



    if not refuels:

        text = active_car_banner(car.name) + "\n" + EMPTY_EXPORT_TEXT

        await show_or_edit(

            target,

            text,

            edit=edit,

            reply_markup=main_menu_keyboard(),

        )

        return



    csv_data = export_refuels_to_csv(refuels, car_name=car.name)

    filename = csv_filename(car.name)

    document = BufferedInputFile(csv_data, filename=filename)



    await target.answer_document(

        document,

        caption=(

            f"📁 Експорт заправок для <b>{html_escape(car.name)}</b>\n"

            f"Записів: {code(len(refuels))}"

        ),

        parse_mode="HTML",

    )

    await target.answer(

        active_car_banner(car.name) + "\n📁 Експорт завершено",

        reply_markup=home_button_keyboard(),

        parse_mode="HTML",

    )





@router.message(Command("export"))

async def cmd_export(message: Message, state: FSMContext) -> None:

    """Handle /export — send refuel history as a CSV file."""
    await state.clear()

    await _send_export(message, message.from_user.id)





@router.callback_query(F.data == MENU_EXPORT)

@safe_callback

async def callback_export(callback: CallbackQuery, state: FSMContext) -> None:

    await state.clear()

    await callback.answer()

    await _send_export(callback.message, callback.from_user.id, edit=True)

