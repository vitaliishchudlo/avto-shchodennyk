"""Inline keyboards for the main menu and add-fuel flow."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.fuel_products import POPULAR_STATIONS, STATION_SLUGS

# Callback prefixes
MENU_ADD = "menu:add"
MENU_STATS = "menu:stats"
MENU_HISTORY = "menu:history"
MENU_LAST = "menu:last"
MENU_EXPORT = "menu:export"
MENU_SETTINGS = "menu:settings"
MENU_HOME = "menu:home"

HISTORY_PREV = "history:prev"
HISTORY_NEXT = "history:next"

FUEL_DATE_TODAY = "fuel:date:today"
FUEL_DATE_OTHER = "fuel:date:other"
FUEL_STATION_PREFIX = "fuel:st:"
FUEL_STATION_OTHER = "fuel:st:other"
FUEL_ENTER_TOTAL = "fuel:enter_total"
FUEL_TYPE_PREFIX = "fuel:type:"
FUEL_PRODUCT_PREFIX = "fuel:product:"
FUEL_PRODUCT_CUSTOM = "fuel:product:custom"
FUEL_PRODUCT_SKIP = "fuel:product:skip"
FUEL_FULL_TANK_PREFIX = "fuel:full:"
FUEL_CONFIRM_SAVE = "fuel:save"
FUEL_CONFIRM_CANCEL = "fuel:cancel"
FUEL_CONFIRM_RESTART = "fuel:restart"

SETTINGS_CARS = "settings:cars"
SETTINGS_CURRENCY = "settings:currency"
SETTINGS_EXTENDED_HISTORY = "settings:extended:toggle"
SETTINGS_BACK = "settings:back"

LAST_DELETE = "last:delete"
LAST_DELETE_CONFIRM = "last:delete:yes"
LAST_DELETE_CANCEL = "last:delete:no"


def _cancel_row() -> list[InlineKeyboardButton]:
    """Return a single-row cancel button for fuel-flow steps."""
    return [InlineKeyboardButton(text="❌ Скасувати", callback_data=FUEL_CONFIRM_CANCEL)]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the root inline menu shown after /start and navigation home."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати заправку", callback_data=MENU_ADD)],
            [
                InlineKeyboardButton(text="📊 Статистика витрат", callback_data=MENU_STATS),
                InlineKeyboardButton(text="📜 Історія заправок", callback_data=MENU_HISTORY),
            ],
            [
                InlineKeyboardButton(text="⛽ Остання заправка", callback_data=MENU_LAST),
                InlineKeyboardButton(text="📁 Експорт CSV", callback_data=MENU_EXPORT),
            ],
            [InlineKeyboardButton(text="⚙️ Налаштування", callback_data=MENU_SETTINGS)],
        ]
    )


def home_button_keyboard() -> InlineKeyboardMarkup:
    """Build a keyboard with a single back-to-main-menu button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Повернутись у головне меню", callback_data=MENU_HOME)],
        ]
    )


def last_refuel_keyboard() -> InlineKeyboardMarkup:
    """Build actions for viewing the most recent refuel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⛔ Видалити останню", callback_data=LAST_DELETE)],
            [InlineKeyboardButton(text="🏠 Повернутись у головне меню", callback_data=MENU_HOME)],
        ]
    )


def last_delete_confirm_keyboard() -> InlineKeyboardMarkup:
    """Build confirm/cancel buttons for deleting the last refuel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, видалити", callback_data=LAST_DELETE_CONFIRM),
                InlineKeyboardButton(text="❌ Скасувати", callback_data=LAST_DELETE_CANCEL),
            ],
        ]
    )


def refuel_date_keyboard() -> InlineKeyboardMarkup:
    """Build date selection buttons for the add-fuel wizard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сьогодні", callback_data=FUEL_DATE_TODAY)],
            [InlineKeyboardButton(text="📅 Ввести дату", callback_data=FUEL_DATE_OTHER)],
            _cancel_row(),
        ]
    )


def station_keyboard() -> InlineKeyboardMarkup:
    """Build a two-column grid of popular gas stations plus custom entry."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for station in POPULAR_STATIONS:
        slug = STATION_SLUGS[station]
        row.append(
            InlineKeyboardButton(
                text=station,
                callback_data=f"{FUEL_STATION_PREFIX}{slug}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="➕ Інша АЗС", callback_data=FUEL_STATION_OTHER)])
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fuel_type_keyboard() -> InlineKeyboardMarkup:
    """Build fuel-type choices for the add-fuel wizard."""
    types = ["Бензин", "Дизель", "Газ", "Інше"]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=f"{FUEL_TYPE_PREFIX}{t}")]
            for t in types
        ]
        + [_cancel_row()]
    )


def fuel_product_keyboard(products: list[str]) -> InlineKeyboardMarkup:
    """Build product choices for the selected station and fuel type."""
    rows: list[list[InlineKeyboardButton]] = []
    for index, product in enumerate(products):
        rows.append([
            InlineKeyboardButton(
                text=product,
                callback_data=f"{FUEL_PRODUCT_PREFIX}{index}",
            )
        ])
    rows.append([InlineKeyboardButton(text="✍️ Ввести вручну", callback_data=FUEL_PRODUCT_CUSTOM)])
    rows.append([InlineKeyboardButton(text="⏭ Пропустити", callback_data=FUEL_PRODUCT_SKIP)])
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fuel_product_manual_keyboard() -> InlineKeyboardMarkup:
    """Build manual entry and skip buttons when no catalog products exist."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ввести вручну", callback_data=FUEL_PRODUCT_CUSTOM)],
            [InlineKeyboardButton(text="⏭ Пропустити", callback_data=FUEL_PRODUCT_SKIP)],
            _cancel_row(),
        ]
    )


def enter_total_keyboard() -> InlineKeyboardMarkup:
    """Build the optional total-price entry step in the add-fuel wizard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Ввести суму", callback_data=FUEL_ENTER_TOTAL)],
            _cancel_row(),
        ]
    )


def full_tank_keyboard() -> InlineKeyboardMarkup:
    """Build yes/no buttons for the full-tank question."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так", callback_data=f"{FUEL_FULL_TANK_PREFIX}yes"),
                InlineKeyboardButton(text="❌ Ні", callback_data=f"{FUEL_FULL_TANK_PREFIX}no"),
            ],
            _cancel_row(),
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Build save, restart, and cancel buttons for refuel confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Зберегти", callback_data=FUEL_CONFIRM_SAVE)],
            [
                InlineKeyboardButton(text="✏️ Ввести заново", callback_data=FUEL_CONFIRM_RESTART),
                InlineKeyboardButton(text="❌ Скасувати", callback_data=FUEL_CONFIRM_CANCEL),
            ],
        ]
    )


def history_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Build pagination controls for the refuel history view."""
    buttons: list[list[InlineKeyboardButton]] = []
    nav_row: list[InlineKeyboardButton] = []

    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{HISTORY_PREV}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="➡️ Далі", callback_data=f"{HISTORY_NEXT}:{page + 1}")
        )

    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data=MENU_HOME)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_keyboard(*, extended_history: bool = True) -> InlineKeyboardMarkup:
    """Build the settings submenu with current extended-history status."""
    ext_status = "✅ Увімкнено" if extended_history else "❌ Вимкнено"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Авто", callback_data=SETTINGS_CARS)],
            [InlineKeyboardButton(text="💱 Валюта", callback_data=SETTINGS_CURRENCY)],
            [
                InlineKeyboardButton(
                    text=f"📊 Розширена історія: {ext_status}",
                    callback_data=SETTINGS_EXTENDED_HISTORY,
                )
            ],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
        ]
    )
