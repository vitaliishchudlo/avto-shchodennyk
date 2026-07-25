"""Inline keyboards for the main menu and add-fuel flow."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.fuel_products import POPULAR_STATIONS, STATION_SLUGS

# Callback prefixes
MENU_ADD = "menu:add"
MENU_STATS = "menu:stats"
MENU_HISTORY = "menu:history"
MENU_LAST = "menu:last"
MENU_SETTINGS = "menu:settings"
MENU_HOME = "menu:home"

SETTINGS_CARS = "settings:cars"
SETTINGS_CURRENCY = "settings:currency"
SETTINGS_EXTENDED_HISTORY = "settings:extended:toggle"
SETTINGS_AI_IMPORT = "settings:ai_import"
SETTINGS_BACK = "settings:back"

IMPORT_CAR_CONFIRM = "import:car:yes"
IMPORT_CAR_CHANGE = "import:car:change"
IMPORT_CAR_PICK_PREFIX = "import:car:pick:"
IMPORT_CONFIRM_SAVE = "import:save"
IMPORT_CONFIRM_CANCEL = "import:cancel"

HISTORY_GOTO = "hist:g:"
HISTORY_NOOP = "hist:noop"
HISTORY_EXPORT = "hist:exp"

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

LAST_DELETE = "last:delete"
LAST_DELETE_CONFIRM = "last:delete:yes"
LAST_DELETE_CANCEL = "last:delete:no"

# Backward-compatible aliases (old export/import menu callbacks)
MENU_EXPORT = HISTORY_EXPORT
MENU_IMPORT = SETTINGS_AI_IMPORT


def _cancel_row() -> list[InlineKeyboardButton]:
    """Return a single-row cancel button for fuel-flow steps."""
    return [InlineKeyboardButton(text="❌ Скасувати", callback_data=FUEL_CONFIRM_CANCEL)]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the root inline menu shown after /start and navigation home."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати заправку", callback_data=MENU_ADD)],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data=MENU_STATS),
                InlineKeyboardButton(text="📜 Історія", callback_data=MENU_HISTORY),
            ],
            [InlineKeyboardButton(text="⛽ Остання заправка", callback_data=MENU_LAST)],
            [InlineKeyboardButton(text="⚙️ Налаштування", callback_data=MENU_SETTINGS)],
        ]
    )


def import_confirm_car_keyboard() -> InlineKeyboardMarkup:
    """Confirm / change car before AI import."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так", callback_data=IMPORT_CAR_CONFIRM),
                InlineKeyboardButton(text="🔄 Змінити авто", callback_data=IMPORT_CAR_CHANGE),
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=IMPORT_CONFIRM_CANCEL)],
        ]
    )


def import_preview_keyboard() -> InlineKeyboardMarkup:
    """Confirm or cancel an AI-mapped import batch."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Додати записи", callback_data=IMPORT_CONFIRM_SAVE)],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=IMPORT_CONFIRM_CANCEL)],
        ]
    )


def import_cancel_keyboard() -> InlineKeyboardMarkup:
    """Single cancel button while waiting for import payload."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=IMPORT_CONFIRM_CANCEL)],
        ]
    )


def import_done_keyboard() -> InlineKeyboardMarkup:
    """After successful AI import: back to settings or main menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Налаштування", callback_data=MENU_SETTINGS)],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
        ]
    )


def home_button_keyboard() -> InlineKeyboardMarkup:
    """Build a keyboard with a single back-to-main-menu button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
        ]
    )


def last_refuel_keyboard() -> InlineKeyboardMarkup:
    """Build actions for viewing the most recent refuel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⛔ Видалити останню", callback_data=LAST_DELETE)],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
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
    """Build history controls: first/prev/indicator/next/last + export + home.

    Always shows five nav buttons. Edge pages re-target the current page so
    taps never error. Page indicator uses a no-op callback.
    """
    last_page = max(0, total_pages - 1)
    prev_page = max(0, page - 1)
    next_page = min(last_page, page + 1)
    indicator = f"{page + 1} / {total_pages}"

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="⏮", callback_data=f"{HISTORY_GOTO}0"),
            InlineKeyboardButton(text="◀️", callback_data=f"{HISTORY_GOTO}{prev_page}"),
            InlineKeyboardButton(text=indicator, callback_data=HISTORY_NOOP),
            InlineKeyboardButton(text="▶️", callback_data=f"{HISTORY_GOTO}{next_page}"),
            InlineKeyboardButton(text="⏭", callback_data=f"{HISTORY_GOTO}{last_page}"),
        ],
        [InlineKeyboardButton(text="📁 Експорт CSV", callback_data=HISTORY_EXPORT)],
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_empty_keyboard() -> InlineKeyboardMarkup:
    """Keyboard when history has no records."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
        ]
    )


def settings_keyboard(*, extended_history: bool = True) -> InlineKeyboardMarkup:
    """Build the settings submenu: cars, currency, toggles, rare AI import."""
    ext_label = "Увімк." if extended_history else "Вимк."
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Авто", callback_data=SETTINGS_CARS)],
            [InlineKeyboardButton(text="💱 Валюта", callback_data=SETTINGS_CURRENCY)],
            [
                InlineKeyboardButton(
                    text=f"📊 Розширена історія: {ext_label}",
                    callback_data=SETTINGS_EXTENDED_HISTORY,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 AI-імпорт заправок",
                    callback_data=SETTINGS_AI_IMPORT,
                )
            ],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)],
        ]
    )
