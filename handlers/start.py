"""Handlers for /start, /help, and main-menu home navigation."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback
from handlers.messages import HELP_TEXT, WELCOME_TEXT
from keyboards.main_menu import MENU_HOME, main_menu_keyboard
from keyboards.utils import show_main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Register the user and show the welcome message with the main menu."""
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Show the help text with available commands."""
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == MENU_HOME)
@safe_callback
async def callback_home(callback: CallbackQuery, state: FSMContext) -> None:
    """Clear FSM state and return to the main menu."""
    await state.clear()
    await callback.answer()
    await show_main_menu(callback, WELCOME_TEXT)
