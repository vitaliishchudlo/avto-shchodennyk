"""Handlers for managing user cars (add, rename, switch, delete)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback, show_or_edit
from keyboards.cars import (
    CARS_ADD,
    CARS_ADD_ACTIVE_NO,
    CARS_ADD_ACTIVE_YES,
    CARS_BACK_SETTINGS,
    CARS_DELETE,
    CARS_DELETE_CANCEL,
    CARS_DELETE_CONFIRM_PREFIX,
    CARS_MENU,
    CARS_RENAME,
    CARS_SWITCH,
    CAR_SELECT_PREFIX,
    car_add_active_keyboard,
    car_delete_confirm_keyboard,
    cars_list_keyboard,
    cars_menu_keyboard,
)
from keyboards.main_menu import SETTINGS_CARS
from keyboards.utils import safe_edit_text
from services.formatting import html_escape
from states.fuel_states import CarStates

router = Router()


async def _show_cars_menu(target: Message, user_id: int, *, edit: bool = False) -> None:
    """Display the cars management screen with the active car highlighted."""
    active = await db.get_active_car(user_id)
    cars = await db.get_user_cars(user_id)

    lines = [
        "🚗 <b>Авто</b>\n",
        "📌 <b>Активне авто:</b>",
        f"👉 <b>{html_escape(active.name)}</b>\n",
    ]

    if cars:
        lines.append("<b>Список:</b>")
        for car in cars:
            marker = " (активне)" if car.is_active else ""
            lines.append(f"• 🚗 {html_escape(car.name)}{marker}")
    else:
        lines.append("<i>Ще немає авто. Додай перше.</i>")

    await show_or_edit(
        target,
        "\n".join(lines),
        edit=edit,
        reply_markup=cars_menu_keyboard(),
    )


@router.callback_query(F.data == SETTINGS_CARS)
@safe_callback
async def callback_settings_cars(callback: CallbackQuery, state: FSMContext) -> None:
    """Open the cars menu from settings."""
    await state.clear()
    await callback.answer()
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == CARS_MENU)
@safe_callback
async def callback_cars_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == CARS_BACK_SETTINGS)
@safe_callback
async def callback_cars_back_settings(callback: CallbackQuery, state: FSMContext) -> None:
    from handlers.settings import _show_settings

    await state.clear()
    await callback.answer()
    await _show_settings(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == CARS_ADD)
@safe_callback
async def callback_cars_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CarStates.add_name)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🚗 <b>Введи назву авто</b>\n\nНаприклад: <code>Audi Q5</code>",
        reply_markup=None,
        parse_mode="HTML",
    )


@router.message(CarStates.add_name)
async def process_car_add_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 50:
        await message.answer("⚠️ Введи назву авто (до 50 символів).")
        return

    await state.update_data(new_car_name=name)
    await state.set_state(CarStates.add_set_active)
    await message.answer(
        f"🚗 Зробити <b>{html_escape(name)}</b> активним авто?",
        reply_markup=car_add_active_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == CARS_ADD_ACTIVE_YES, CarStates.add_set_active)
@safe_callback
async def callback_car_add_active_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    name = data.get("new_car_name", "Моє авто")
    await db.add_car(callback.from_user.id, name, set_active=True)
    await state.clear()
    await callback.answer("Авто додано ✅")
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == CARS_ADD_ACTIVE_NO, CarStates.add_set_active)
@safe_callback
async def callback_car_add_active_no(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    name = data.get("new_car_name", "Моє авто")
    await db.add_car(callback.from_user.id, name, set_active=False)
    await state.clear()
    await callback.answer("Авто додано ✅")
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == CARS_SWITCH)
@safe_callback
async def callback_cars_switch(callback: CallbackQuery, state: FSMContext) -> None:
    cars = await db.get_user_cars(callback.from_user.id)
    if len(cars) <= 1:
        await callback.answer("Додай ще одне авто для перемикання", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🔄 <b>Обери авто для перемикання:</b>",
        reply_markup=cars_list_keyboard(cars),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(CAR_SELECT_PREFIX), CarStates.rename_pick)
@safe_callback
async def callback_car_rename_pick(callback: CallbackQuery, state: FSMContext) -> None:
    car_id = int(callback.data.removeprefix(CAR_SELECT_PREFIX))
    car = await db.get_car_by_id(car_id, callback.from_user.id)
    if not car:
        await callback.answer("Авто не знайдено", show_alert=True)
        return

    await state.update_data(rename_car_id=car_id)
    await state.set_state(CarStates.rename_name)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        f"✏️ Введи нову назву для <b>{html_escape(car.name)}</b>:",
        reply_markup=None,
        parse_mode="HTML",
    )


@router.message(CarStates.rename_name)
async def process_car_rename_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 50:
        await message.answer("⚠️ Введи назву авто (до 50 символів).")
        return

    data = await state.get_data()
    car_id = data.get("rename_car_id")
    if not car_id:
        await state.clear()
        await message.answer("⚠️ Сесію перервано. Спробуй ще раз.")
        return

    await db.rename_car(message.from_user.id, car_id, name)
    await state.clear()
    await message.answer(f"✅ Назву змінено на <b>{html_escape(name)}</b>", parse_mode="HTML")
    await _show_cars_menu(message, message.from_user.id)


@router.callback_query(F.data.startswith(CAR_SELECT_PREFIX), CarStates.delete_pick)
@safe_callback
async def callback_car_delete_pick(callback: CallbackQuery, state: FSMContext) -> None:
    car_id = int(callback.data.removeprefix(CAR_SELECT_PREFIX))
    car = await db.get_car_by_id(car_id, callback.from_user.id)
    if not car:
        await callback.answer("Авто не знайдено", show_alert=True)
        return

    count = await db.count_refuels_for_car(car_id)
    await state.clear()
    await callback.answer()

    text = (
        f"⚠️ <b>Видалити {html_escape(car.name)}?</b>\n\n"
        f"У цього авто <b>{count}</b> заправок.\n"
        "Видалення авто також видалить усю його історію."
        if count > 0
        else f"Видалити <b>{html_escape(car.name)}</b>?"
    )
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=car_delete_confirm_keyboard(car_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(CAR_SELECT_PREFIX))
@safe_callback
async def callback_car_select(callback: CallbackQuery, state: FSMContext) -> None:
    """Switch the active car (not in rename/delete FSM states)."""
    car_id = int(callback.data.removeprefix(CAR_SELECT_PREFIX))
    car = await db.get_car_by_id(car_id, callback.from_user.id)
    if not car:
        await callback.answer("Авто не знайдено", show_alert=True)
        return

    await db.set_active_car(callback.from_user.id, car_id)
    await state.clear()
    await callback.answer(f"Активне: {car.name}")
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == CARS_RENAME)
@safe_callback
async def callback_cars_rename(callback: CallbackQuery, state: FSMContext) -> None:
    cars = await db.get_user_cars(callback.from_user.id)
    await state.set_state(CarStates.rename_pick)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "✏️ <b>Обери авто для перейменування:</b>",
        reply_markup=cars_list_keyboard(cars),
        parse_mode="HTML",
    )


@router.callback_query(F.data == CARS_DELETE)
@safe_callback
async def callback_cars_delete(callback: CallbackQuery, state: FSMContext) -> None:
    cars = await db.get_user_cars(callback.from_user.id)
    if len(cars) <= 1:
        await callback.answer("Не можна видалити єдине авто", show_alert=True)
        return

    await state.set_state(CarStates.delete_pick)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🗑 <b>Обери авто для видалення:</b>",
        reply_markup=cars_list_keyboard(cars),
        parse_mode="HTML",
    )


@router.callback_query(F.data == CARS_DELETE_CANCEL)
@safe_callback
async def callback_car_delete_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data.startswith(CARS_DELETE_CONFIRM_PREFIX))
@safe_callback
async def callback_car_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    car_id = int(callback.data.removeprefix(CARS_DELETE_CONFIRM_PREFIX))
    ok = await db.delete_car(callback.from_user.id, car_id)
    await state.clear()
    if not ok:
        await callback.answer("Не вдалося видалити", show_alert=True)
        return

    await callback.answer("Авто видалено")
    await _show_cars_menu(callback.message, callback.from_user.id, edit=True)
