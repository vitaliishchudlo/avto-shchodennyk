"""Inline keyboards for the main menu and add-fuel flow."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.fuel_products import POPULAR_STATIONS, STATION_SLUGS

# Callback prefixes
MENU_ADD = "menu:add"
MENU_ADD_PHOTO = "menu:add_photo"
MENU_STATS = "menu:stats"
MENU_HISTORY = "menu:history"
MENU_LAST = "menu:last"
MENU_SETTINGS = "menu:settings"
MENU_HOME = "menu:home"

SETTINGS_CARS = "settings:cars"
SETTINGS_CURRENCY = "settings:currency"
SETTINGS_EXTENDED_HISTORY = "settings:extended:toggle"
SETTINGS_AI_IMPORT = "settings:ai_import"
SETTINGS_ARCHIVE = "settings:archive"

ARCHIVE_TOGGLE_PREFIX = "archive:t:"
ARCHIVE_SHOW_ALL = "archive:show_all"
ARCHIVE_HIDE_ALL = "archive:hide_all"

STATS_PERIOD_PREFIX = "stats:p:"
STATS_PERIOD_ALL = "stats:p:all"
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
FUEL_ENTER_PER_LITER = "fuel:enter_per_liter"
FUEL_DISCOUNT_NONE = "fuel:discount:none"
FUEL_DISCOUNT_AMOUNT = "fuel:discount:amount"
FUEL_DISCOUNT_PER_LITER = "fuel:discount:per_liter"
FUEL_NOTE_SKIP = "fuel:note:skip"
FUEL_TYPE_PREFIX = "fuel:type:"
FUEL_PRODUCT_PREFIX = "fuel:product:"
FUEL_PRODUCT_CUSTOM = "fuel:product:custom"
FUEL_PRODUCT_SKIP = "fuel:product:skip"
FUEL_FULL_TANK_PREFIX = "fuel:full:"
FUEL_CONFIRM_SAVE = "fuel:save"
FUEL_CONFIRM_CANCEL = "fuel:cancel"
FUEL_CONFIRM_RESTART = "fuel:restart"

PHOTO_SAVE = "photo:save"
PHOTO_TOGGLE_FULL = "photo:full"
PHOTO_NOTE = "photo:note"
PHOTO_EDIT = "photo:edit"
PHOTO_CAR = "photo:car"
PHOTO_CAR_PICK_PREFIX = "photo:car:pick:"
PHOTO_FUEL_PREFIX = "photo:fuel:"
PHOTO_FUEL_KEEP = "photo:fuel:keep"
PHOTO_BACK = "photo:back"
PHOTO_CANCEL = "photo:cancel"

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
            [
                InlineKeyboardButton(text="📸 Заправка по фото", callback_data=MENU_ADD_PHOTO),
                InlineKeyboardButton(text="✍️ Вручну", callback_data=MENU_ADD),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data=MENU_STATS),
                InlineKeyboardButton(text="📜 Історія", callback_data=MENU_HISTORY),
            ],
            [
                InlineKeyboardButton(text="⛽ Остання заправка", callback_data=MENU_LAST),
                InlineKeyboardButton(text="⚙️ Налаштування", callback_data=MENU_SETTINGS),
            ],
        ]
    )


def photo_cancel_keyboard() -> InlineKeyboardMarkup:
    """Single cancel button while waiting for photo input."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=PHOTO_CANCEL)],
        ]
    )


def photo_fuel_keyboard(products: list[str], keep_name: str | None) -> InlineKeyboardMarkup:
    """Catalog fuel choices for an unrecognized receipt fuel name, two per row."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, product in enumerate(products):
        row.append(InlineKeyboardButton(text=product, callback_data=f"{PHOTO_FUEL_PREFIX}{index}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if keep_name:
        label = keep_name if len(keep_name) <= 30 else keep_name[:29] + "…"
        rows.append([
            InlineKeyboardButton(text=f"✍️ Залишити «{label}»", callback_data=PHOTO_FUEL_KEEP)
        ])
    rows.append([InlineKeyboardButton(text="❌ Скасувати", callback_data=PHOTO_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def photo_back_keyboard() -> InlineKeyboardMarkup:
    """Back-to-preview button for note / correction prompts."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад до перевірки", callback_data=PHOTO_BACK)],
        ]
    )


def photo_preview_keyboard(*, full_tank: bool, has_note: bool) -> InlineKeyboardMarkup:
    """Build preview actions for a photo-recognized refuel."""
    tank_label = "🛢 Повний бак: Так" if full_tank else "🛢 Повний бак: Ні"
    note_label = "📝 Змінити примітку" if has_note else "📝 Додати примітку"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Зберегти", callback_data=PHOTO_SAVE)],
            [
                InlineKeyboardButton(text=tank_label, callback_data=PHOTO_TOGGLE_FULL),
                InlineKeyboardButton(text=note_label, callback_data=PHOTO_NOTE),
            ],
            [
                InlineKeyboardButton(text="✏️ Виправити", callback_data=PHOTO_EDIT),
                InlineKeyboardButton(text="🚗 Інше авто", callback_data=PHOTO_CAR),
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=PHOTO_CANCEL)],
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


def price_mode_keyboard() -> InlineKeyboardMarkup:
    """Build the choice between entering the receipt total or price per liter."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧾 Сума чека", callback_data=FUEL_ENTER_TOTAL)],
            [InlineKeyboardButton(text="⛽ Ціна за літр", callback_data=FUEL_ENTER_PER_LITER)],
            _cancel_row(),
        ]
    )


def discount_keyboard() -> InlineKeyboardMarkup:
    """Build discount options: none, a flat amount, or per liter."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➖ Без знижки", callback_data=FUEL_DISCOUNT_NONE)],
            [InlineKeyboardButton(text="💸 Знижка сумою", callback_data=FUEL_DISCOUNT_AMOUNT)],
            [InlineKeyboardButton(text="⛽ Знижка на літр", callback_data=FUEL_DISCOUNT_PER_LITER)],
            _cancel_row(),
        ]
    )


def note_keyboard() -> InlineKeyboardMarkup:
    """Build the skip button for the optional note step."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустити", callback_data=FUEL_NOTE_SKIP)],
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


def archive_keyboard(years: list[tuple[int, int]], hidden: set[int]) -> InlineKeyboardMarkup:
    """Year toggles for the archive screen (✅ visible / 🙈 hidden) plus bulk actions."""
    rows: list[list[InlineKeyboardButton]] = []
    for year, count in years:
        mark = "🙈" if year in hidden else "✅"
        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {year} · {count} зап.",
                callback_data=f"{ARCHIVE_TOGGLE_PREFIX}{year}",
            )
        ])
    if years:
        rows.append([
            InlineKeyboardButton(text="👁 Показати всі", callback_data=ARCHIVE_SHOW_ALL),
            InlineKeyboardButton(text="🙈 Сховати всі", callback_data=ARCHIVE_HIDE_ALL),
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Налаштування", callback_data=SETTINGS_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stats_keyboard(
    years: list[int],
    selected: int | None,
    *,
    all_label: str = "Весь час",
) -> InlineKeyboardMarkup:
    """Period switcher for statistics: all visible years, or one visible year.

    all_label names the "all" period honestly, e.g. "2025–2026" while years are archived.
    """
    def label(text: str, active: bool) -> str:
        return f"• {text} •" if active else text

    period_buttons = []
    if years:
        period_buttons.append(
            InlineKeyboardButton(text=label(all_label, selected is None), callback_data=STATS_PERIOD_ALL)
        )
    # With a single year the "all" button already is that year
    if len(years) > 1:
        period_buttons.extend(
            InlineKeyboardButton(text=label(str(year), selected == year), callback_data=f"{STATS_PERIOD_PREFIX}{year}")
            for year in years
        )
    rows = [period_buttons[i:i + 4] for i in range(0, len(period_buttons), 4)]
    rows.append([InlineKeyboardButton(text="🏠 Головне меню", callback_data=MENU_HOME)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard(*, extended_history: bool = True) -> InlineKeyboardMarkup:
    """Build the settings submenu: cars, currency, toggles, rare AI import."""
    ext_label = "Увімк." if extended_history else "Вимк."
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Авто", callback_data=SETTINGS_CARS)],
            [InlineKeyboardButton(text="💱 Валюта", callback_data=SETTINGS_CURRENCY)],
            [InlineKeyboardButton(text="🗄 Архів років", callback_data=SETTINGS_ARCHIVE)],
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
