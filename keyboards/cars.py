"""Inline keyboards for car management."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import Car
from keyboards.main_menu import MENU_HOME

CARS_MENU = "cars:menu"
CARS_ADD = "cars:add"
CARS_SWITCH = "cars:switch"
CARS_RENAME = "cars:rename"
CARS_DELETE = "cars:delete"
CARS_BACK_SETTINGS = "cars:back:settings"
CARS_ADD_ACTIVE_YES = "cars:add:active:yes"
CARS_ADD_ACTIVE_NO = "cars:add:active:no"
CARS_DELETE_CONFIRM_PREFIX = "cars:del:confirm:"
CARS_DELETE_CANCEL = "cars:del:cancel"
CAR_SELECT_PREFIX = "car:select:"
CAR_PICK_PREFIX = "car:pick:"

FUEL_CAR_CONFIRM = "fuel:car:yes"
FUEL_CAR_CHANGE = "fuel:car:change"


def cars_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the car management submenu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати авто", callback_data=CARS_ADD)],
            [InlineKeyboardButton(text="🔄 Перемкнути авто", callback_data=CARS_SWITCH)],
            [InlineKeyboardButton(text="✏️ Перейменувати", callback_data=CARS_RENAME)],
            [InlineKeyboardButton(text="🗑 Видалити авто", callback_data=CARS_DELETE)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=CARS_BACK_SETTINGS)],
        ]
    )


def cars_list_keyboard(
    cars: list[Car],
    *,
    prefix: str = CAR_SELECT_PREFIX,
    back_callback: str = CARS_MENU,
) -> InlineKeyboardMarkup:
    """Build a selectable list of the user's cars with an active marker."""
    rows: list[list[InlineKeyboardButton]] = []
    for car in cars:
        label = f"🚗 {car.name}"
        if car.is_active:
            label += " (активне)"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"{prefix}{car.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def car_add_active_keyboard() -> InlineKeyboardMarkup:
    """Build yes/no buttons for making a newly added car active."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, зробити активним", callback_data=CARS_ADD_ACTIVE_YES),
                InlineKeyboardButton(text="❌ Ні", callback_data=CARS_ADD_ACTIVE_NO),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=CARS_MENU)],
        ]
    )


def car_delete_confirm_keyboard(car_id: int) -> InlineKeyboardMarkup:
    """Build confirm/cancel buttons for deleting a car."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Так, видалити",
                    callback_data=f"{CARS_DELETE_CONFIRM_PREFIX}{car_id}",
                ),
                InlineKeyboardButton(text="❌ Скасувати", callback_data=CARS_DELETE_CANCEL),
            ],
        ]
    )


def confirm_car_keyboard() -> InlineKeyboardMarkup:
    """Build confirm/change/cancel buttons for the active car in add-fuel."""
    from keyboards.main_menu import FUEL_CONFIRM_CANCEL

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так", callback_data=FUEL_CAR_CONFIRM),
                InlineKeyboardButton(text="🔄 Змінити авто", callback_data=FUEL_CAR_CHANGE),
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=FUEL_CONFIRM_CANCEL)],
        ]
    )


def car_pick_keyboard(cars: list[Car]) -> InlineKeyboardMarkup:
    """Build a car picker for the add-fuel flow."""
    return cars_list_keyboard(cars, prefix=CAR_PICK_PREFIX, back_callback=FUEL_CAR_CONFIRM)
