"""Safe helpers for editing inline keyboards and wizard prompts."""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from keyboards.main_menu import main_menu_keyboard

PROMPT_CHAT_KEY = "_prompt_chat_id"
PROMPT_MSG_KEY = "_prompt_message_id"


async def safe_clear_markup(message: Message) -> None:
    """Remove inline keyboard markup, ignoring Telegram edit errors."""
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


async def safe_edit_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message | bool:
    """Edit message text; return False when Telegram reports a no-op edit."""
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        err = str(exc).lower()
        if "message is not modified" in err:
            return False
        if "there is no text" in err or "can't be edited" in err:
            return False
        raise


async def show_main_menu(
    target: Message | CallbackQuery,
    text: str,
    *,
    parse_mode: str = "HTML",
) -> Message | None:
    """Show the main menu via edit_text or answer for non-text messages."""
    message = target.message if isinstance(target, CallbackQuery) else target
    if message is None:
        return None

    keyboard = main_menu_keyboard()
    if message.text:
        result = await safe_edit_text(
            message,
            text,
            reply_markup=keyboard,
            parse_mode=parse_mode,
        )
        return message if result is not False else message

    return await message.answer(text, reply_markup=keyboard, parse_mode=parse_mode)


async def track_prompt(state: FSMContext, message: Message) -> None:
    """Store chat/message ids of the current wizard prompt for later cleanup."""
    await state.update_data(
        **{
            PROMPT_CHAT_KEY: message.chat.id,
            PROMPT_MSG_KEY: message.message_id,
        }
    )


async def clear_tracked_prompt(bot: Bot, state: FSMContext) -> None:
    """Remove markup from the tracked wizard prompt message, if any."""
    data = await state.get_data()
    chat_id = data.get(PROMPT_CHAT_KEY)
    msg_id = data.get(PROMPT_MSG_KEY)
    if not chat_id or not msg_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass


async def send_step(
    target: Message,
    state: FSMContext,
    text: str,
    *,
    edit: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
) -> Message:
    """Send or edit a wizard step and track the prompt when a keyboard is shown."""
    if edit:
        await safe_edit_text(target, text, reply_markup=reply_markup, parse_mode=parse_mode)
        result = target
    else:
        result = await target.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

    if reply_markup is not None:
        await track_prompt(state, result)
    else:
        await state.update_data(**{PROMPT_CHAT_KEY: None, PROMPT_MSG_KEY: None})

    return result
