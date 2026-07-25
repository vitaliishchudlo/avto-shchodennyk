"""FSM state groups for add-fuel, settings, cars, and AI import flows."""

from aiogram.fsm.state import State, StatesGroup


class AddFuelStates(StatesGroup):
    """States for the multi-step add-refuel wizard."""

    confirm_car = State()
    car_pick = State()
    refuel_date = State()
    refuel_date_input = State()
    odometer = State()
    station = State()
    station_custom = State()
    fuel_type = State()
    fuel_product = State()
    fuel_product_custom = State()
    liters = State()
    price_mode = State()
    total_price = State()
    full_tank = State()
    confirm = State()


class SettingsStates(StatesGroup):
    """States for user settings edits."""

    currency = State()


class CarStates(StatesGroup):
    """States for creating, renaming, and deleting cars."""

    add_name = State()
    add_set_active = State()
    rename_pick = State()
    rename_name = State()
    delete_pick = State()


class ImportStates(StatesGroup):
    """States for AI-assisted bulk import of refuel records."""

    confirm_car = State()
    car_pick = State()
    await_payload = State()
    clarify = State()
    preview = State()
