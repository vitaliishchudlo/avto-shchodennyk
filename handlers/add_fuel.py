"""Multi-step FSM handlers for recording a new refuel."""

from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from database import RefuelRecord
from handlers.messages import MAIN_MENU_TEXT
from keyboards.cars import (
    CAR_PICK_PREFIX,
    FUEL_CAR_CHANGE,
    FUEL_CAR_CONFIRM,
    car_pick_keyboard,
    confirm_car_keyboard,
)
from keyboards.main_menu import (
    FUEL_CONFIRM_CANCEL,
    FUEL_CONFIRM_RESTART,
    FUEL_CONFIRM_SAVE,
    FUEL_DATE_OTHER,
    FUEL_DATE_TODAY,
    FUEL_ENTER_TOTAL,
    FUEL_FULL_TANK_PREFIX,
    FUEL_PRODUCT_PREFIX,
    FUEL_STATION_OTHER,
    FUEL_STATION_PREFIX,
    FUEL_TYPE_PREFIX,
    MENU_ADD,
    confirm_keyboard,
    enter_total_keyboard,
    fuel_product_keyboard,
    fuel_product_manual_keyboard,
    fuel_type_keyboard,
    full_tank_keyboard,
    home_button_keyboard,
    main_menu_keyboard,
    refuel_date_keyboard,
    station_keyboard,
)
from keyboards.utils import (
    clear_tracked_prompt,
    safe_clear_markup,
    safe_edit_text,
    send_step,
    track_prompt,
)
from services.calculations import (
    calc_trip_stats,
    parse_date,
    parse_number,
)
from services.formatting import code, fmt_date, fmt_num, html_escape
from services.fuel_products import SLUG_TO_STATION, get_products, normalize_station_name
from states.fuel_states import AddFuelStates

router = Router()

TOTAL_STEPS = 10

DATE_STEP_TEXT = f"<b>1/{TOTAL_STEPS}</b> 📅 Це заправка за сьогодні?"

DATE_INPUT_TEXT = (
    f"<b>1/{TOTAL_STEPS}</b> 📅 Введи дату заправки.\n\n"
    "Формат: <i>день.місяць.рік</i>\n\n"
    "Приклади:\n"
    f"{code('03.07.2026')}\n"
    f"{code('3.7.2026')}\n"
    f"{code('2026-07-03')}"
)

DATE_ERROR_TEXT = (
    "Не зміг розпізнати дату 😕\n"
    "Введи, будь ласка, у форматі <i>день.місяць.рік</i>.\n\n"
    f"Наприклад: {code('03.07.2026')}"
)

DATE_FUTURE_TEXT = (
    "⚠️ Дата заправки не може бути в майбутньому.\n"
    "Введи дату ще раз."
)

ODOMETER_TEXT = (
    f"<b>2/{TOTAL_STEPS}</b> 🚗 Давай зафіксуємо пробіг.\n"
    "Введи число на одометрі.\n\n"
    f"Наприклад: {code('224871')}"
)


def _step(n: int, text: str) -> str:
    """Prefix prompt text with the current step number."""
    return f"<b>{n}/{TOTAL_STEPS}</b> {text}"


async def _ask_confirm_car(
    target: Message,
    state: FSMContext,
    user_id: int,
    *,
    edit: bool = False,
    previous: Message | None = None,
) -> None:
    """Ask the user to confirm the active car before starting the flow."""
    if previous:
        await safe_clear_markup(previous)
    car = await db.get_active_car(user_id)
    await state.update_data(car_id=car.id)
    await state.set_state(AddFuelStates.confirm_car)
    text = (
        f"🚗 <b>Обране авто:</b>\n"
        f"<b>{html_escape(car.name)}</b>\n\n"
        "Це правильно?"
    )
    if edit:
        await safe_edit_text(
            target,
            text,
            reply_markup=confirm_car_keyboard(),
            parse_mode="HTML",
        )
        await track_prompt(state, target)
    else:
        msg = await target.answer(
            text,
            reply_markup=confirm_car_keyboard(),
            parse_mode="HTML",
        )
        await track_prompt(state, msg)


async def _go_to_date_step(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 1: ask whether the refuel date is today."""
    await state.set_state(AddFuelStates.refuel_date)
    if edit:
        await safe_edit_text(
            target,
            DATE_STEP_TEXT,
            reply_markup=refuel_date_keyboard(),
            parse_mode="HTML",
        )
        await track_prompt(state, target)
    else:
        msg = await target.answer(
            DATE_STEP_TEXT,
            reply_markup=refuel_date_keyboard(),
            parse_mode="HTML",
        )
        await track_prompt(state, msg)


async def _start_add_flow(
    target: Message,
    state: FSMContext,
    user_id: int,
    *,
    previous: Message | None = None,
) -> None:
    """Reset FSM state and begin the add-refuel wizard."""
    if previous:
        await safe_clear_markup(previous)
    await state.clear()
    await _ask_confirm_car(target, state, user_id)


async def _ask_odometer(chat: Message, state: FSMContext, *, previous: Message | None = None) -> None:
    """Show step 2: prompt for odometer reading."""
    if previous:
        await safe_clear_markup(previous)
    await clear_tracked_prompt(chat.bot, state)
    await chat.answer(ODOMETER_TEXT, parse_mode="HTML")


async def _ask_station(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 3: gas station selection."""
    await send_step(
        target,
        state,
        _step(3, "📍 Обери АЗС або введи назву вручну."),
        edit=edit,
        reply_markup=station_keyboard(),
    )


async def _ask_fuel_type(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 4: fuel category (filters the product list)."""
    await send_step(
        target,
        state,
        _step(4, "⛽ Обери категорію пального."),
        edit=edit,
        reply_markup=fuel_type_keyboard(),
    )


async def _ask_fuel_product(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 5: specific fuel name (stored in fuel_type)."""
    data = await state.get_data()
    station = data.get("station_name")
    category = data["fuel_category"]
    products = get_products(station, category)
    await state.update_data(_product_list=products)

    if products:
        text = _step(5, "🧾 Обери пальне.")
        markup = fuel_product_keyboard(products)
    else:
        text = _step(
            5,
            "Для цієї АЗС немає готового списку.\n"
            "Введи назву пального вручну (наприклад Pulls 95, ДП Євро).",
        )
        markup = fuel_product_manual_keyboard()

    await send_step(target, state, text, edit=edit, reply_markup=markup)


async def _ask_liters(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 6: liters input."""
    await send_step(
        target,
        state,
        _step(6, f"🔢 Скільки літрів заправив?\n\nНаприклад: {code('42.5')}"),
        edit=edit,
        reply_markup=None,
    )


async def _ask_price(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 7: price per liter or total amount."""
    await send_step(
        target,
        state,
        _step(7, f"💰 Введи ціну за літр або загальну суму.\n\nНаприклад: {code('62.5')}"),
        edit=edit,
        reply_markup=enter_total_keyboard(),
    )


async def _ask_full_tank(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    """Show step 8: full-tank yes/no."""
    await send_step(
        target,
        state,
        _step(9, "🛢 Чи був повний бак?"),
        edit=edit,
        reply_markup=full_tank_keyboard(),
    )


async def _show_confirm(
    target: Message,
    state: FSMContext,
    user_id: int,
    *,
    edit: bool = False,
) -> None:
    """Show step 9: review collected data before saving."""
    data = await state.get_data()
    settings = await db.ensure_user(user_id)
    text = (
        f"<b>{TOTAL_STEPS}/{TOTAL_STEPS}</b> 📋 <b>Перевір дані заправки</b>\n\n"
        f"{_format_confirmation(data, settings.currency)}\n\n"
        "Зберегти?"
    )
    await send_step(target, state, text, edit=edit, reply_markup=confirm_keyboard())


def _format_confirmation(data: dict, currency: str) -> str:
    """Build HTML summary text for the confirmation screen."""
    station = data.get("station_name") or "—"
    full_tank = "Так ✅" if data.get("full_tank") else "Ні ❌"
    refuel_date = data.get("refuel_date")
    date_str = fmt_date(refuel_date) if refuel_date else "—"

    return (
        f"📅 Дата: {date_str}\n"
        f"🚗 Пробіг: {fmt_num(data['odometer_km'], 0)} км\n"
        f"⛽ АЗС: <b>{html_escape(station)}</b>\n"
        f"🧾 Пальне: <b>{html_escape(data['fuel_type'])}</b>\n"
        f"🔢 Літри: {fmt_num(data['liters'])} л\n"
        f"💰 Сума: {fmt_num(data['total_price'], 0)} {currency}\n"
        f"🛢 Повний бак: {full_tank}"
    )


def _format_save_summary(data: dict, currency: str, previous: RefuelRecord | None) -> str:
    """Build HTML summary shown after a refuel is saved, including trip stats."""
    station = data.get("station_name") or "—"
    lines = [
        "Заправку збережено ✅\n",
        f"📅 Дата: {fmt_date(data['refuel_date'])}",
        f"🔢 Літри: {fmt_num(data['liters'])} л",
        f"💰 Сума: {fmt_num(data['total_price'], 0)} {currency}",
        f"⛽ АЗС: <b>{html_escape(station)}</b>",
        f"🧾 Пальне: <b>{html_escape(data['fuel_type'])}</b>",
        f"🚗 Пробіг: {fmt_num(data['odometer_km'], 0)} км",
    ]

    if previous:
        current = RefuelRecord(
            id=0,
            user_id=0,
            date=datetime.combine(data["refuel_date"], datetime.min.time()),
            odometer_km=data["odometer_km"],
            liters=data["liters"],
            price_per_liter=data["price_per_liter"],
            total_price=data["total_price"],
            fuel_type=data["fuel_type"],
            station_name=data.get("station_name"),
            full_tank=data.get("full_tank", False),
            note=None,
        )
        trip = calc_trip_stats(current, previous)
        if trip:
            lines.extend([
                "",
                "<b>З попередньої заправки:</b>",
                f"📏 Проїхав: {fmt_num(trip.distance_km, 0)} км",
                f"🔥 Витрата: {fmt_num(trip.consumption_l_per_100km)} л / 100 км",
                f"💸 Вартість 100 км: {fmt_num(trip.cost_per_100km, 0)} {currency}",
                f"🪙 Вартість 1 км: {fmt_num(trip.cost_per_km, 2)} {currency}",
            ])
    else:
        lines.extend([
            "",
            "ℹ️ Це перший запис. Статистика між заправками буде доступна після наступної заправки.",
        ])

    return "\n".join(lines)


# --- Flow start ---

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    """Handle /add — start the add-refuel wizard."""
    await db.ensure_tg_user(message.from_user)
    await _start_add_flow(message, state, message.from_user.id)


@router.callback_query(F.data == MENU_ADD)
async def callback_add(callback: CallbackQuery, state: FSMContext) -> None:
    await db.ensure_tg_user(callback.from_user)
    await callback.answer()
    await _start_add_flow(callback.message, state, callback.from_user.id, previous=callback.message)


@router.callback_query(F.data == FUEL_CONFIRM_RESTART)
async def callback_restart(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_add_flow(callback.message, state, callback.from_user.id, previous=callback.message)


# --- Step 0: confirm car ---

@router.callback_query(F.data == FUEL_CAR_CONFIRM, AddFuelStates.confirm_car)
async def callback_car_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    car = await db.get_active_car(callback.from_user.id)
    await state.update_data(car_id=car.id)
    await callback.answer()
    await _go_to_date_step(callback.message, state, edit=True)


@router.callback_query(F.data == FUEL_CAR_CHANGE, AddFuelStates.confirm_car)
async def callback_car_change(callback: CallbackQuery, state: FSMContext) -> None:
    cars = await db.get_user_cars(callback.from_user.id)
    await state.set_state(AddFuelStates.car_pick)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🔄 <b>Обери авто для заправки:</b>",
        reply_markup=car_pick_keyboard(cars),
        parse_mode="HTML",
    )


@router.callback_query(F.data == FUEL_CAR_CONFIRM, AddFuelStates.car_pick)
async def callback_car_pick_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _ask_confirm_car(
        callback.message,
        state,
        callback.from_user.id,
        edit=True,
    )


@router.callback_query(F.data.startswith(CAR_PICK_PREFIX), AddFuelStates.car_pick)
async def callback_car_pick(callback: CallbackQuery, state: FSMContext) -> None:
    car_id = int(callback.data.removeprefix(CAR_PICK_PREFIX))
    car = await db.get_car_by_id(car_id, callback.from_user.id)
    if not car:
        await callback.answer("Авто не знайдено", show_alert=True)
        return

    await db.set_active_car(callback.from_user.id, car_id)
    await state.update_data(car_id=car_id)
    await callback.answer(f"Обрано: {car.name}")
    await _ask_confirm_car(
        callback.message,
        state,
        callback.from_user.id,
        edit=True,
    )


# --- Step 1: date ---

@router.callback_query(F.data == FUEL_DATE_TODAY, AddFuelStates.refuel_date)
async def callback_date_today(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(refuel_date=date.today())
    await state.set_state(AddFuelStates.odometer)
    await callback.answer()
    await _ask_odometer(callback.message, state, previous=callback.message)


@router.callback_query(F.data == FUEL_DATE_OTHER, AddFuelStates.refuel_date)
async def callback_date_other(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddFuelStates.refuel_date_input)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        DATE_INPUT_TEXT,
        reply_markup=None,
        parse_mode="HTML",
    )


@router.message(AddFuelStates.refuel_date_input)
async def process_refuel_date_input(message: Message, state: FSMContext) -> None:
    try:
        parsed = parse_date(message.text)
    except (ValueError, TypeError):
        await message.answer(DATE_ERROR_TEXT, parse_mode="HTML")
        return

    if parsed > date.today():
        await message.answer(DATE_FUTURE_TEXT, parse_mode="HTML")
        return

    await state.update_data(refuel_date=parsed)
    await state.set_state(AddFuelStates.odometer)
    await _ask_odometer(message, state)


# --- Step 2: odometer ---

@router.message(AddFuelStates.odometer)
async def process_odometer(message: Message, state: FSMContext) -> None:
    try:
        odometer = parse_number(message.text)
        if odometer <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            "⚠️ Введи коректний кілометраж (ціле або дробове число).",
            parse_mode="HTML",
        )
        return

    user_id = message.from_user.id
    data = await state.get_data()
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id
    previous = await db.get_previous_refuel(user_id, car_id, odometer)
    if previous and odometer <= previous.odometer_km:
        await message.answer(
            "⚠️ Кілометраж має бути більший, ніж у попередньому записі "
            f"({fmt_num(previous.odometer_km, 0)} км).",
            parse_mode="HTML",
        )
        return

    await state.update_data(odometer_km=odometer)
    await state.set_state(AddFuelStates.station)
    await _ask_station(message, state)


# --- Step 3: gas station ---

@router.callback_query(F.data == FUEL_STATION_OTHER, AddFuelStates.station)
async def callback_station_other(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddFuelStates.station_custom)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        _step(3, "📍 Введи назву АЗС вручну.\nНаприклад: Avantage 7, Mango, Motto"),
        reply_markup=None,
        parse_mode="HTML",
    )


@router.callback_query(
    F.data.startswith(FUEL_STATION_PREFIX),
    ~F.data.in_({FUEL_STATION_OTHER}),
    AddFuelStates.station,
)
async def callback_station(callback: CallbackQuery, state: FSMContext) -> None:
    slug = callback.data.removeprefix(FUEL_STATION_PREFIX)
    station = SLUG_TO_STATION.get(slug)
    if not station:
        await callback.answer("Невідома АЗС", show_alert=True)
        return

    await state.update_data(station_name=station)
    await state.set_state(AddFuelStates.fuel_type)
    await callback.answer()
    await _ask_fuel_type(callback.message, state, edit=True)


@router.message(AddFuelStates.station)
async def process_station_text(message: Message, state: FSMContext) -> None:
    station = message.text.strip()
    if not station:
        await message.answer("Введи назву АЗС або обери зі списку.")
        return

    await clear_tracked_prompt(message.bot, state)
    await state.update_data(station_name=normalize_station_name(station))
    await state.set_state(AddFuelStates.fuel_type)
    await _ask_fuel_type(message, state)


@router.message(AddFuelStates.station_custom)
async def process_station_custom(message: Message, state: FSMContext) -> None:
    station = message.text.strip()
    if not station:
        await message.answer("Введи назву АЗС.")
        return

    await state.update_data(station_name=normalize_station_name(station))
    await state.set_state(AddFuelStates.fuel_type)
    await _ask_fuel_type(message, state)


# --- Step 4: fuel type ---

@router.callback_query(F.data.startswith(FUEL_TYPE_PREFIX), AddFuelStates.fuel_type)
async def callback_fuel_type(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.removeprefix(FUEL_TYPE_PREFIX)
    await state.update_data(fuel_category=category)
    await state.set_state(AddFuelStates.fuel_product)
    await callback.answer()
    await _ask_fuel_product(callback.message, state, edit=True)


# --- Step 5: fuel name (stored as fuel_type) ---

@router.callback_query(
    F.data.startswith(FUEL_PRODUCT_PREFIX),
    AddFuelStates.fuel_product,
)
async def callback_fuel_product(callback: CallbackQuery, state: FSMContext) -> None:
    suffix = callback.data.removeprefix(FUEL_PRODUCT_PREFIX)

    if suffix == "custom":
        await state.set_state(AddFuelStates.fuel_product_custom)
        await callback.answer()
        await safe_edit_text(
            callback.message,
            _step(5, "✍️ Введи назву пального вручну.\nНаприклад: Pulls 95, ДП Євро"),
            reply_markup=None,
            parse_mode="HTML",
        )
        return

    if suffix == "skip":
        data = await state.get_data()
        await state.update_data(fuel_type=data.get("fuel_category") or "Інше")
        await state.set_state(AddFuelStates.liters)
        await callback.answer()
        await _ask_liters(callback.message, state, edit=True)
        return

    try:
        idx = int(suffix)
        data = await state.get_data()
        product = data["_product_list"][idx]
    except (ValueError, KeyError, IndexError):
        await callback.answer("Невідомий варіант", show_alert=True)
        return

    await state.update_data(fuel_type=product)
    await state.set_state(AddFuelStates.liters)
    await callback.answer()
    await _ask_liters(callback.message, state, edit=True)


@router.message(AddFuelStates.fuel_product)
async def process_fuel_product_text(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Введи назву пального або обери з кнопок.")
        return

    await clear_tracked_prompt(message.bot, state)
    await state.update_data(fuel_type=name)
    await state.set_state(AddFuelStates.liters)
    await _ask_liters(message, state)


@router.message(AddFuelStates.fuel_product_custom)
async def process_fuel_product_custom(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Введи назву пального.")
        return

    await state.update_data(fuel_type=name)
    await state.set_state(AddFuelStates.liters)
    await _ask_liters(message, state)


# --- Step 6: liters ---

@router.message(AddFuelStates.liters)
async def process_liters(message: Message, state: FSMContext) -> None:
    try:
        liters = parse_number(message.text)
        if liters <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            f"⚠️ Введи коректну кількість літрів.\nНаприклад: {code('42.5')}",
            parse_mode="HTML",
        )
        return

    await state.update_data(liters=liters, price_mode="per_liter")
    await state.set_state(AddFuelStates.price_mode)
    await _ask_price(message, state)


# --- Step 7: price ---

@router.message(AddFuelStates.price_mode)
async def process_price_per_liter(message: Message, state: FSMContext) -> None:
    try:
        price = parse_number(message.text)
        if price <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            f"⚠️ Введи коректну ціну за літр.\nНаприклад: {code('62.5')}",
            parse_mode="HTML",
        )
        return

    await clear_tracked_prompt(message.bot, state)

    data = await state.get_data()
    total_price = round(price * data["liters"], 2)

    await state.update_data(price_per_liter=price, total_price=total_price)
    await state.set_state(AddFuelStates.full_tank)
    await _ask_full_tank(message, state)


@router.callback_query(F.data == FUEL_ENTER_TOTAL, AddFuelStates.price_mode)
async def callback_enter_total(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(price_mode="total")
    await state.set_state(AddFuelStates.total_price)
    await safe_edit_text(
        callback.message,
        _step(7, f"💰 Введи загальну суму заправки.\n\nНаприклад: {code('2650')}"),
        reply_markup=None,
        parse_mode="HTML",
    )


@router.message(AddFuelStates.total_price)
async def process_total_price(message: Message, state: FSMContext) -> None:
    try:
        total = parse_number(message.text)
        if total <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            f"⚠️ Введи коректну суму.\nНаприклад: {code('2650')}",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    price_per_liter = round(total / data["liters"], 2)

    await state.update_data(total_price=total, price_per_liter=price_per_liter)
    await state.set_state(AddFuelStates.full_tank)
    await _ask_full_tank(message, state)


# --- Step 8: full tank ---

@router.callback_query(F.data.startswith(FUEL_FULL_TANK_PREFIX), AddFuelStates.full_tank)
async def callback_full_tank(callback: CallbackQuery, state: FSMContext) -> None:
    is_full = callback.data.endswith("yes")
    await state.update_data(full_tank=is_full)
    await state.set_state(AddFuelStates.confirm)
    await callback.answer()
    await _show_confirm(callback.message, state, callback.from_user.id, edit=True)


# --- Step 9: confirmation ---

@router.callback_query(F.data == FUEL_CONFIRM_SAVE, AddFuelStates.confirm)
async def callback_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id
    previous = await db.get_previous_refuel(user_id, car_id, data["odometer_km"])

    await db.add_refuel(
        user_id,
        car_id=car_id,
        refuel_date=data["refuel_date"],
        odometer_km=data["odometer_km"],
        liters=data["liters"],
        price_per_liter=data["price_per_liter"],
        total_price=data["total_price"],
        fuel_type=data["fuel_type"],
        station_name=data.get("station_name"),
        full_tank=data.get("full_tank", False),
    )

    settings = await db.ensure_user(user_id)
    await state.clear()
    await callback.answer("Збережено")

    text = _format_save_summary(data, settings.currency, previous)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=home_button_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == FUEL_CONFIRM_CANCEL)
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Скасовано")
    await safe_edit_text(
        callback.message,
        "❌ Додавання заправки скасовано.\n\n" + MAIN_MENU_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


# --- Hint for button-driven steps ---

@router.message(StateFilter(AddFuelStates))
async def add_fuel_hint(message: Message, state: FSMContext) -> None:
    """Remind the user to use buttons when free-text is not expected."""
    current = await state.get_state()
    text_steps = {
        AddFuelStates.confirm_car.state: "обери варіант кнопкою",
        AddFuelStates.car_pick.state: "обери авто кнопкою",
        AddFuelStates.refuel_date.state: "обери варіант кнопкою",
        AddFuelStates.fuel_type.state: "обери тип пального кнопкою",
        AddFuelStates.full_tank.state: "обери «Так» або «Ні» кнопкою",
        AddFuelStates.confirm.state: "підтвердь або скасуй кнопкою",
    }
    hint = text_steps.get(current, "введи дані як просив бот на цьому кроці")
    await message.answer(f"💡 Будь ласка, {hint}.")
