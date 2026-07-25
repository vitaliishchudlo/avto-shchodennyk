"""AI-assisted import of refuel history from files or free text."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.callback_guard import safe_callback
from keyboards.cars import cars_list_keyboard
from keyboards.main_menu import (
    IMPORT_CAR_CHANGE,
    IMPORT_CAR_CONFIRM,
    IMPORT_CAR_PICK_PREFIX,
    IMPORT_CONFIRM_CANCEL,
    IMPORT_CONFIRM_SAVE,
    SETTINGS_AI_IMPORT,
    import_cancel_keyboard,
    import_confirm_car_keyboard,
    import_done_keyboard,
    import_preview_keyboard,
    settings_keyboard,
)
from keyboards.utils import safe_clear_markup, safe_edit_text
from services.ai_import import AIImportError, is_ai_configured, map_import_payload
from services.formatting import code, fmt_date, fmt_num, html_escape
from services.import_parse import ImportParseError, parse_document_bytes, parse_free_text
from services.import_validate import (
    ValidatedRefuel,
    records_to_fsm_dicts,
    validate_ai_result,
)
from states.fuel_states import ImportStates

router = Router()
logger = logging.getLogger(__name__)

PREVIEW_LIMIT = 5

IMPORT_TITLE = "🤖 AI-імпорт заправок"

AWAIT_PAYLOAD_TEXT = (
    f"<b>{IMPORT_TITLE}</b>\n\n"
    "Надішли дані про заправки в зручному вигляді:\n"
    "• файл <b>CSV</b> або <b>Excel</b> (.xlsx)\n"
    "• або звичайне повідомлення — таблицю, список чи короткий опис\n\n"
    "Назви колонок можуть бути будь-якими.\n\n"
    "AI розпізнає, зокрема:\n"
    "дату, пробіг, літри, ціну за літр, суму, пальне (наприклад Pulls 95), "
    "АЗС (якщо є), а також примітки чи знижки.\n\n"
    "Місто чи область як «локацію» вказувати не потрібно.\n"
    "Перед додаванням покажемо прев’ю — ти зможеш перевірити записи."
)

CLARIFY_HINT = (
    "\n\nМожеш дописати відсутні дані повідомленням, "
    "надіслати виправлений файл або скасувати."
)

PROCESSING_TEXT = "⏳ AI зараз аналізує твої дані…"

CANCELLED_TEXT = f"❌ {IMPORT_TITLE} скасовано."


async def _return_to_settings(target: Message, user_id: int, *, edit: bool = True) -> None:
    from handlers.settings import _show_settings

    await _show_settings(target, user_id, edit=edit)


async def _ask_confirm_car(
    target: Message,
    state: FSMContext,
    user_id: int,
    *,
    edit: bool = False,
    previous: Message | None = None,
) -> None:
    if previous:
        await safe_clear_markup(previous)
    car = await db.get_active_car(user_id)
    await state.update_data(car_id=car.id)
    await state.set_state(ImportStates.confirm_car)
    text = (
        f"<b>{IMPORT_TITLE}</b>\n\n"
        f"🚗 Обране авто: <b>{html_escape(car.name)}</b>\n\n"
        "Імпортувати заправки для цього авто?"
    )
    markup = import_confirm_car_keyboard()
    if edit:
        await safe_edit_text(target, text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=markup, parse_mode="HTML")


async def _start_import_flow(
    target: Message,
    state: FSMContext,
    user_id: int,
    *,
    previous: Message | None = None,
) -> None:
    if previous:
        await safe_clear_markup(previous)
    await state.clear()

    if not is_ai_configured():
        settings = await db.ensure_user(user_id)
        text = (
            f"⚠️ <b>{IMPORT_TITLE}</b> ще не налаштовано.\n\n"
            "Звернись до адміністратора бота — потрібен ключ AI."
        )
        markup = settings_keyboard(extended_history=settings.extended_history)
        if previous:
            await safe_edit_text(target, text, reply_markup=markup, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=markup, parse_mode="HTML")
        return

    await _ask_confirm_car(target, state, user_id, edit=bool(previous), previous=None)


async def _ask_payload(target: Message, state: FSMContext, *, edit: bool = False) -> None:
    await state.set_state(ImportStates.await_payload)
    markup = import_cancel_keyboard()
    if edit:
        await safe_edit_text(
            target,
            AWAIT_PAYLOAD_TEXT,
            reply_markup=markup,
            parse_mode="HTML",
        )
    else:
        await target.answer(AWAIT_PAYLOAD_TEXT, reply_markup=markup, parse_mode="HTML")


def _format_preview_row(record: ValidatedRefuel, currency: str) -> str:
    parts = [
        f"📅 {fmt_date(record.refuel_date)}",
        f"{fmt_num(record.odometer_km, 0)} км",
        f"{fmt_num(record.liters)} л",
        f"{fmt_num(record.total_price, 0)} {currency}",
        html_escape(record.fuel_type),
    ]
    if record.station_name:
        parts.append(html_escape(record.station_name))
    return " · ".join(parts)


def _format_preview(
    records: list[ValidatedRefuel],
    *,
    car_name: str,
    currency: str,
) -> str:
    lines = [
        f"📋 <b>Прев’ю — {IMPORT_TITLE}</b>",
        f"Авто: <b>{html_escape(car_name)}</b>",
        f"Записів: {code(len(records))}",
        "",
    ]
    for record in records[:PREVIEW_LIMIT]:
        lines.append("• " + _format_preview_row(record, currency))
    remaining = len(records) - PREVIEW_LIMIT
    if remaining > 0:
        lines.append(f"… і ще {remaining}")
    lines.extend(["", "Усе вірно? Додати ці заправки?"])
    return "\n".join(lines)


async def _show_preview(
    message: Message,
    state: FSMContext,
    user_id: int,
    records: list[ValidatedRefuel],
) -> None:
    data = await state.get_data()
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id
    car = await db.get_car_by_id(car_id, user_id) or await db.get_active_car(user_id)
    settings = await db.ensure_user(user_id)

    await state.update_data(
        car_id=car.id,
        pending_records=records_to_fsm_dicts(records),
    )
    await state.set_state(ImportStates.preview)
    await message.answer(
        _format_preview(records, car_name=car.name, currency=settings.currency),
        reply_markup=import_preview_keyboard(),
        parse_mode="HTML",
    )


async def _ask_clarification(message: Message, state: FSMContext, issues: list[str]) -> None:
    await state.set_state(ImportStates.clarify)
    body = (
        f"⚠️ <b>{IMPORT_TITLE}</b>\n\n"
        "Не всі дані вдалося розпізнати повністю:\n\n"
        + "\n".join(f"• {html_escape(issue)}" for issue in issues[:12])
    )
    if len(issues) > 12:
        body += f"\n… і ще {len(issues) - 12}"
    body += CLARIFY_HINT
    await message.answer(body, reply_markup=import_cancel_keyboard(), parse_mode="HTML")


async def _download_document(bot: Bot, message: Message) -> tuple[str | None, bytes]:
    document = message.document
    assert document is not None
    file = await bot.get_file(document.file_id)
    assert file.file_path is not None
    buffer = await bot.download_file(file.file_path)
    data = buffer.read() if hasattr(buffer, "read") else bytes(buffer)
    return document.file_name, data


async def _process_raw_rows(
    message: Message,
    state: FSMContext,
    raw_rows: list[dict[str, Any]],
    *,
    clarification: str | None = None,
) -> None:
    status_msg = await message.answer(PROCESSING_TEXT)
    try:
        ai_result = await map_import_payload(raw_rows, clarification=clarification)
        validated, issues = validate_ai_result(ai_result)
    except AIImportError as exc:
        await status_msg.edit_text(f"⚠️ {html_escape(str(exc))}", parse_mode="HTML")
        await state.set_state(ImportStates.clarify)
        await message.answer(
            "Можеш надіслати дані ще раз або скасувати.",
            reply_markup=import_cancel_keyboard(),
        )
        return
    except Exception:
        logger.exception("Unexpected import processing error")
        await status_msg.edit_text(
            "⚠️ Не вдалося обробити дані. Спробуй ще раз або надішли інший файл."
        )
        await state.set_state(ImportStates.clarify)
        return

    await state.update_data(raw_rows=raw_rows)

    if not validated:
        try:
            await status_msg.delete()
        except Exception:  # noqa: BLE001
            pass
        await _ask_clarification(
            message,
            state,
            issues or ["Не вдалося розпізнати жодної повної заправки."],
        )
        return

    if issues:
        note = (
            f"✅ Розпізнано {len(validated)} записів.\n"
            f"⚠️ Частину рядків пропущено — їх не додамо без повних даних."
        )
        await status_msg.edit_text(note)
    else:
        try:
            await status_msg.delete()
        except Exception:  # noqa: BLE001
            pass

    await _show_preview(message, state, message.from_user.id, validated)


# --- Entry points ---

@router.message(Command("import"))
async def cmd_import(message: Message, state: FSMContext) -> None:
    await db.ensure_tg_user(message.from_user)
    await _start_import_flow(message, state, message.from_user.id)


@router.callback_query(F.data == SETTINGS_AI_IMPORT)
@safe_callback
async def callback_import(callback: CallbackQuery, state: FSMContext) -> None:
    await db.ensure_tg_user(callback.from_user)
    await callback.answer()
    await _start_import_flow(
        callback.message,
        state,
        callback.from_user.id,
        previous=callback.message,
    )


# --- Car selection ---

@router.callback_query(F.data == IMPORT_CAR_CONFIRM, ImportStates.confirm_car)
@safe_callback
async def callback_import_car_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    car = await db.get_active_car(callback.from_user.id)
    await state.update_data(car_id=car.id, raw_rows=None, pending_records=None)
    await callback.answer()
    await _ask_payload(callback.message, state, edit=True)


@router.callback_query(F.data == IMPORT_CAR_CHANGE, ImportStates.confirm_car)
@safe_callback
async def callback_import_car_change(callback: CallbackQuery, state: FSMContext) -> None:
    cars = await db.get_user_cars(callback.from_user.id)
    await state.set_state(ImportStates.car_pick)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        f"<b>{IMPORT_TITLE}</b>\n\nОбери авто:",
        reply_markup=cars_list_keyboard(
            cars,
            prefix=IMPORT_CAR_PICK_PREFIX,
            back_callback=IMPORT_CAR_CONFIRM,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == IMPORT_CAR_CONFIRM, ImportStates.car_pick)
@safe_callback
async def callback_import_car_pick_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _ask_confirm_car(
        callback.message,
        state,
        callback.from_user.id,
        edit=True,
    )


@router.callback_query(
    F.data.startswith(IMPORT_CAR_PICK_PREFIX),
    ImportStates.car_pick,
)
@safe_callback
async def callback_import_car_pick(callback: CallbackQuery, state: FSMContext) -> None:
    car_id = int(callback.data.removeprefix(IMPORT_CAR_PICK_PREFIX))
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


# --- Payload / clarification ---

@router.message(ImportStates.await_payload, F.document)
@router.message(ImportStates.clarify, F.document)
async def process_import_document(message: Message, state: FSMContext) -> None:
    try:
        filename, data = await _download_document(message.bot, message)
        raw_rows = parse_document_bytes(filename, data)
    except ImportParseError as exc:
        await message.answer(f"⚠️ {html_escape(str(exc))}", parse_mode="HTML")
        return
    except Exception:
        logger.exception("Failed to download/parse import document")
        await message.answer("⚠️ Не вдалося завантажити файл. Спробуй ще раз.")
        return

    await state.update_data(raw_rows=raw_rows)
    await _process_raw_rows(message, state, raw_rows)


@router.message(ImportStates.await_payload, F.text)
@router.message(ImportStates.clarify, F.text)
async def process_import_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Надішли файл або текст із даними про заправки.")
        return

    data = await state.get_data()
    existing_rows = data.get("raw_rows")
    current = await state.get_state()

    if current == ImportStates.clarify.state and existing_rows:
        try:
            maybe_new = parse_free_text(text)
            is_structured = len(maybe_new) > 1 or (
                len(maybe_new) == 1 and "_raw" not in maybe_new[0]
            )
            if is_structured:
                await state.update_data(raw_rows=maybe_new)
                await _process_raw_rows(message, state, maybe_new)
                return
        except ImportParseError:
            pass
        await _process_raw_rows(
            message,
            state,
            existing_rows,
            clarification=text,
        )
        return

    try:
        raw_rows = parse_free_text(text)
    except ImportParseError as exc:
        await message.answer(f"⚠️ {html_escape(str(exc))}", parse_mode="HTML")
        return

    await state.update_data(raw_rows=raw_rows)
    await _process_raw_rows(message, state, raw_rows)


# --- Preview save / cancel ---

@router.callback_query(F.data == IMPORT_CONFIRM_SAVE, ImportStates.preview)
@safe_callback
async def callback_import_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pending = data.get("pending_records") or []
    if not pending:
        await callback.answer("Немає даних для імпорту", show_alert=True)
        await state.clear()
        await _return_to_settings(callback.message, callback.from_user.id, edit=True)
        return

    user_id = callback.from_user.id
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id
    car = await db.get_car_by_id(car_id, user_id) or await db.get_active_car(user_id)

    count = await db.add_refuels_batch(user_id, car_id, pending)
    await state.clear()
    await callback.answer("Готово")
    await safe_edit_text(
        callback.message,
        (
            f"✅ <b>{IMPORT_TITLE}</b> завершено\n\n"
            f"Додано записів: {code(count)}\n"
            f"Авто: <b>{html_escape(car.name)}</b>"
        ),
        reply_markup=import_done_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == IMPORT_CONFIRM_CANCEL)
@safe_callback
async def callback_import_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Скасовано")
    settings = await db.ensure_user(callback.from_user.id)
    active = await db.get_active_car(callback.from_user.id)
    from handlers.settings import _settings_text

    text = CANCELLED_TEXT + "\n\n" + _settings_text(settings, active.name)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=settings_keyboard(extended_history=settings.extended_history),
        parse_mode="HTML",
    )


@router.message(StateFilter(ImportStates.preview))
async def import_preview_hint(message: Message) -> None:
    await message.answer("Підтверди або скасуй імпорт кнопками під прев’ю.")


@router.message(StateFilter(ImportStates.confirm_car, ImportStates.car_pick))
async def import_car_hint(message: Message) -> None:
    await message.answer("Обери варіант кнопкою.")
