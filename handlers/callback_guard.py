"""Callback deduplication guard and safe message edit helpers."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, TypeVar

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from handlers.messages import MAIN_MENU_TEXT
from keyboards.main_menu import MENU_HOME, main_menu_keyboard
from keyboards.utils import safe_edit_text, show_main_menu

_CALLBACK_TTL_SEC = 120.0
_ACTION_TTL_SEC = 1.0
_seen_callbacks: OrderedDict[str, float] = OrderedDict()
_recent_actions: OrderedDict[tuple[int, str], float] = OrderedDict()
_MAX_SEEN = 2000

logger = logging.getLogger(__name__)


def _is_duplicate_action(user_id: int, action: str) -> bool:
    """Return True if the same user triggered the same action within the TTL window."""
    now = time.time()
    key = (user_id, action)

    while _recent_actions and _recent_actions[next(iter(_recent_actions))] < now - _ACTION_TTL_SEC:
        _recent_actions.popitem(last=False)

    last = _recent_actions.get(key)
    if last is not None and now - last < _ACTION_TTL_SEC:
        return True

    _recent_actions[key] = now
    if len(_recent_actions) > _MAX_SEEN:
        _recent_actions.popitem(last=False)
    return False

F = TypeVar("F", bound=Callable[..., Any])


def is_duplicate_callback(callback_id: str) -> bool:
    """Return True if this callback query ID was already processed recently."""
    now = time.time()
    while _seen_callbacks and _seen_callbacks[next(iter(_seen_callbacks))] < now - _CALLBACK_TTL_SEC:
        _seen_callbacks.popitem(last=False)

    if callback_id in _seen_callbacks:
        return True

    _seen_callbacks[callback_id] = now
    if len(_seen_callbacks) > _MAX_SEEN:
        _seen_callbacks.popitem(last=False)
    return False


async def guard_callback(callback: CallbackQuery) -> bool:
    """Return False for duplicate callbacks (already answers the query)."""
    if is_duplicate_callback(str(callback.id)):
        await callback.answer()
        return False

    if callback.from_user and callback.data:
        if _is_duplicate_action(callback.from_user.id, callback.data):
            await callback.answer()
            return False

    return True


async def show_or_edit(
    target: Message,
    text: str,
    *,
    edit: bool,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
) -> None:
    """Edit the existing message or send a new one depending on *edit*."""
    if edit:
        await safe_edit_text(target, text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await target.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


def safe_callback(handler: F) -> F:
    """Decorator: deduplicate callbacks and handle handler errors gracefully."""
    @wraps(handler)
    async def wrapper(callback: CallbackQuery, *args: Any, **kwargs: Any) -> Any:
        if not await guard_callback(callback):
            return None
        try:
            return await handler(callback, *args, **kwargs)
        except Exception:
            logger.exception(
                "Callback handler failed (data=%s, user=%s)",
                callback.data,
                callback.from_user.id if callback.from_user else None,
            )
            if callback.data == MENU_HOME:
                try:
                    state: FSMContext | None = kwargs.get("state")
                    if state is not None:
                        await state.clear()
                    await show_main_menu(callback, MAIN_MENU_TEXT)
                    await callback.answer()
                    return None
                except Exception:
                    logger.exception("MENU_HOME fallback failed")
            await callback.answer("⚠️ Сталася помилка", show_alert=True)
            try:
                await callback.message.answer(
                    "⚠️ Сталася помилка. Спробуй ще раз або повернись у меню.",
                    reply_markup=main_menu_keyboard(),
                )
            except Exception:
                pass
            return None

    return wrapper  # type: ignore[return-value]
