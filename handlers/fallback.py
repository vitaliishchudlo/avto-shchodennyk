"""Fallback handlers for unknown commands and unexpected text messages."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from keyboards.main_menu import main_menu_keyboard

router = Router()

FALLBACK_TEXT = (
    "Я тебе почув 🙂\n"
    "Щоб додати заправку або переглянути статистику, скористайся меню нижче."
)

UNKNOWN_COMMAND_TEXT = (
    "🤔 Не знаю такої команди.\n\n"
    "Скористайся /help або меню нижче."
)


def _is_fsm_active(state_name: str | None) -> bool:
    """Return True when an FSM wizard is in progress and fallback should be suppressed."""
    if not state_name:
        return False
    return state_name.startswith("AddFuelStates:") or state_name.startswith("SettingsStates:")


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message, state: FSMContext) -> None:
    """Reply to unrecognized slash commands when no FSM flow is active."""
    if _is_fsm_active(await state.get_state()):
        return
    await message.answer(UNKNOWN_COMMAND_TEXT, reply_markup=main_menu_keyboard())


@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext) -> None:
    """Reply to plain text when no handler or FSM flow consumed the message."""
    if _is_fsm_active(await state.get_state()):
        return
    await message.answer(FALLBACK_TEXT, reply_markup=main_menu_keyboard())
