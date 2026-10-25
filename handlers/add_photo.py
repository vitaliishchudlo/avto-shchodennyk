"""Add one refuel from receipt / dashboard photos (and optional text) recognized by AI."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import IMPORT_MAX_FILE_BYTES
from handlers.add_fuel import _format_confirmation, build_save_summary
from handlers.callback_guard import safe_callback
from handlers.filters import NotForeignCommand
from handlers.messages import MAIN_MENU_TEXT
from keyboards.cars import cars_list_keyboard
from keyboards.main_menu import (
    MENU_ADD_PHOTO,
    PHOTO_BACK,
    PHOTO_CANCEL,
    PHOTO_CAR,
    PHOTO_CAR_PICK_PREFIX,
    PHOTO_EDIT,
    PHOTO_FUEL_KEEP,
    PHOTO_FUEL_PREFIX,
    PHOTO_NOTE,
    PHOTO_SAVE,
    PHOTO_TOGGLE_FULL,
    home_button_keyboard,
    main_menu_keyboard,
    photo_back_keyboard,
    photo_cancel_keyboard,
    photo_fuel_keyboard,
    photo_preview_keyboard,
)
from keyboards.utils import clear_tracked_prompt, safe_clear_markup, safe_edit_text, track_prompt
from services.ai_import import AIImportError, is_ai_configured
from services.ai_receipt import ReceiptInput, recognize_refuel
from services.formatting import code, fmt_date, fmt_num, html_escape
from services.fuel_products import get_all_products
from services.receipt_validate import (
    DRAFT_FIELDS,
    MISSING_DATE,
    MISSING_FUEL,
    MISSING_LITERS,
    MISSING_ODOMETER,
    MISSING_PRICE,
    DraftCheck,
    apply_direct_answer,
    check_draft,
    draft_date,
    draft_from_ai,
    draft_to_record_data,
)
from states.fuel_states import PhotoFuelStates

router = Router()
router.message.filter(NotForeignCommand("photo"))
logger = logging.getLogger(__name__)

TITLE = "📸 Заправка по фото"

# Telegram delivers an album as separate updates; wait this long to collect them all
DEBOUNCE_SEC = 1.5
MAX_IMAGES = 4
NOTE_MAX_LENGTH = 500

AWAIT_INPUT_TEXT = (
    f"<b>{TITLE}</b>\n\n"
    "Надішли одне або кілька фото:\n"
    "• 🧾 чек з АЗС\n"
    "• 🚗 табло з пробігом (одометр)\n\n"
    "Пробіг можна просто дописати підписом до фото, наприклад "
    f"{code('151253')}.\n"
    "Також можна написати все текстом: "
    f"{code('ОККО А-95 42 л 2650 грн пробіг 151253')}\n\n"
    "AI розпізнає дані, а перед збереженням я покажу, що вийшло."
)

PROCESSING_TEXT = "⏳ AI розпізнає дані…"

NOT_CONFIGURED_TEXT = (
    f"⚠️ <b>{TITLE}</b> ще не налаштовано — потрібен ключ AI.\n\n"
    "Поки що додай заправку вручну: «✍️ Вручну»."
)

FIELD_HINTS = {
    MISSING_ODOMETER: f"🚗 <b>Пробіг</b> — фото одометра або просто число, напр. {code('151253')}",
    MISSING_LITERS: f"🔢 <b>Літри</b> — напиши число, напр. {code('42.5')}",
    MISSING_PRICE: (
        f"💰 <b>Сума</b> — сума чека без знижки, напр. {code('2650')}, "
        f"або ціна за літр: {code('ціна 62.5')}"
    ),
    MISSING_FUEL: f"🧾 <b>Пальне</b> — напиши назву, напр. {code('А-95')}",
    MISSING_DATE: f"📅 <b>Дата</b> — напиши дату, напр. {code('03.07.2026')}",
}

_buffers: dict[int, list[Message]] = {}
_timers: dict[int, asyncio.Task] = {}
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


# --- Input buffering ---

def _drop_buffer(user_id: int) -> None:
    """Forget queued input for the user (on cancel / save)."""
    _buffers.pop(user_id, None)
    timer = _timers.pop(user_id, None)
    if timer and not timer.done():
        timer.cancel()


def _enqueue(message: Message, state: FSMContext) -> None:
    """Queue a message and (re)start the debounce timer for this user."""
    user_id = message.from_user.id
    _buffers.setdefault(user_id, []).append(message)
    timer = _timers.get(user_id)
    if timer and not timer.done():
        timer.cancel()
    _timers[user_id] = asyncio.create_task(_flush_later(user_id, state))


async def _flush_later(user_id: int, state: FSMContext) -> None:
    try:
        await asyncio.sleep(DEBOUNCE_SEC)
    except asyncio.CancelledError:
        return
    # Detach before processing so new input starts a fresh batch instead of cancelling this one
    _timers.pop(user_id, None)
    messages = _buffers.pop(user_id, [])
    if not messages:
        return
    try:
        async with _locks[user_id]:
            await _process_batch(messages, state)
    except Exception:
        logger.exception("Photo refuel processing failed (user=%s)", user_id)
        await messages[-1].answer(
            "⚠️ Не вдалося обробити дані. Спробуй ще раз або додай заправку вручну.",
            reply_markup=photo_cancel_keyboard(),
        )


def _image_file(message: Message) -> tuple[str, str] | None:
    """Return (file_id, mime_type) for a photo or an image sent as a file."""
    if message.photo:
        return message.photo[-1].file_id, "image/jpeg"
    document = message.document
    if document and (document.mime_type or "").startswith("image/"):
        if document.file_size and document.file_size > IMPORT_MAX_FILE_BYTES:
            return None
        return document.file_id, document.mime_type or "image/jpeg"
    return None


async def _collect_input(bot: Bot, messages: list[Message]) -> tuple[ReceiptInput, int]:
    """Download photos and gather texts; return the payload and the number of skipped images."""
    payload = ReceiptInput()
    skipped = 0
    for message in messages:
        text = message.caption or message.text
        if text and text.strip():
            payload.texts.append(text.strip())
        image = _image_file(message)
        if image is None:
            if message.document:
                skipped += 1
            continue
        if len(payload.images) >= MAX_IMAGES:
            skipped += 1
            continue
        file_id, mime = image
        buffer = await bot.download(file_id)
        payload.images.append((buffer.read(), mime))
    return payload, skipped


# --- Flow ---

async def _start_flow(
    target: Message,
    state: FSMContext,
    user_id: int,
    *,
    edit: bool,
    keep_buffer: bool = False,
) -> bool:
    """Reset state and wait for photos. Return False when AI is not configured."""
    if not keep_buffer:
        _drop_buffer(user_id)
    await state.clear()
    if not is_ai_configured():
        if edit:
            await safe_edit_text(
                target, NOT_CONFIGURED_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML"
            )
        else:
            await target.answer(NOT_CONFIGURED_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")
        return False

    car = await db.get_active_car(user_id)
    await state.set_state(PhotoFuelStates.await_input)
    await state.update_data(car_id=car.id, draft=None, missing=[])
    return True


async def _check(user_id: int, car_id: int, draft: dict[str, Any]) -> DraftCheck:
    """Validate the draft; reject duplicates and enforce a growing odometer for new refuels."""
    neighbors = await db.get_refuel_neighbors(user_id, car_id, draft_date(draft) or date.today())
    check = check_draft(draft, neighbors=neighbors)

    check.draft.pop("duplicate_of", None)
    odometer = check.draft.get("odometer_km")
    if odometer:
        # After the user answered a duplicate notice, only an identical odometer still counts
        liters = None if check.draft.get("duplicate_override") else check.draft.get("liters")
        duplicate = await db.find_duplicate_refuel(
            user_id,
            car_id,
            refuel_date=date.fromisoformat(check.draft["date"]),
            odometer_km=odometer,
            liters=liters,
        )
        if duplicate:
            check.duplicate = duplicate
            check.draft["duplicate_of"] = duplicate.id
            if MISSING_ODOMETER not in check.missing:
                check.missing.insert(0, MISSING_ODOMETER)
            # The duplicate notice replaces the generic "odometer not greater" warning
            check.warnings = [w for w in check.warnings if not w.startswith("Пробіг ")]
    return check


def _draft_for_ai(draft: dict[str, Any] | None) -> dict[str, Any] | None:
    """Only data fields go to the AI, not internal flags; a guessed date is left out
    so the AI cannot echo it back as if it had been recognized."""
    if not draft:
        return None
    return {
        key: draft[key]
        for key in DRAFT_FIELDS
        if key in draft and not (key == "date" and draft.get("date_assumed"))
    }


async def _process_batch(messages: list[Message], state: FSMContext) -> None:
    message = messages[-1]
    user_id = message.from_user.id
    current = await state.get_state()
    if current not in (
        PhotoFuelStates.await_input.state,
        PhotoFuelStates.clarify.state,
        PhotoFuelStates.preview.state,
    ):
        return  # flow was cancelled or moved on while waiting

    data = await state.get_data()
    draft: dict[str, Any] | None = data.get("draft")
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id
    settings = await db.ensure_user(user_id)
    if draft and draft.get("duplicate_of") and current == PhotoFuelStates.clarify.state:
        # Any answer to the duplicate notice means "this is a different refuel"
        draft = {**draft, "duplicate_override": True}

    payload, skipped = await _collect_input(message.bot, messages)
    if skipped:
        await message.answer(
            f"ℹ️ Пропустив файлів: {skipped} (беру до {MAX_IMAGES} фото, "
            f"лише зображення до {IMPORT_MAX_FILE_BYTES // (1024 * 1024)} МБ)."
        )
    if not payload.images and not payload.texts:
        await message.answer("Надішли фото чека або напиши дані текстом.")
        return

    # A short reply to a single missing field does not need an AI round-trip
    if (
        draft is not None
        and current == PhotoFuelStates.clarify.state
        and not payload.images
        and apply_direct_answer(draft, data.get("missing") or [], " ".join(payload.texts))
    ):
        await _show_result(message, state, user_id, car_id, draft, problems=[])
        return

    last = await db.get_last_refuel(user_id, car_id)
    status = await message.answer(PROCESSING_TEXT)
    try:
        result = await recognize_refuel(
            payload,
            draft=_draft_for_ai(draft),
            last_odometer=last.odometer_km if last else None,
            currency=settings.currency,
        )
    except AIImportError as exc:
        await safe_edit_text(status, f"⚠️ {html_escape(str(exc))}", parse_mode="HTML")
        await message.answer(
            "Можеш надіслати дані ще раз або скасувати.",
            reply_markup=photo_cancel_keyboard(),
        )
        return

    try:
        await status.delete()
    except Exception:  # noqa: BLE001
        pass

    if await state.get_state() != current:
        return  # user cancelled or started another flow while AI was working

    if not result.is_refuel and draft is None:
        await message.answer(
            "🤔 Не знайшов на фото даних про заправку.\n"
            "Надішли чіткіше фото чека або напиши дані текстом.",
            reply_markup=photo_cancel_keyboard(),
        )
        return

    draft = draft_from_ai(result, draft)
    await _show_result(message, state, user_id, car_id, draft, problems=result.problems)


async def _show_result(
    message: Message,
    state: FSMContext,
    user_id: int,
    car_id: int,
    draft: dict[str, Any],
    *,
    problems: list[str],
) -> None:
    """Validate the draft and show either a clarification request or the preview."""
    check = await _check(user_id, car_id, draft)
    warnings = [*problems, *check.warnings]
    await state.update_data(
        draft=check.draft,
        missing=check.missing,
        warnings=warnings,
        infos=check.infos,
    )
    await clear_tracked_prompt(message.bot, state)

    if check.missing:
        await state.set_state(PhotoFuelStates.clarify)
        settings = await db.ensure_user(user_id)
        markup = photo_cancel_keyboard()
        if MISSING_FUEL in check.missing:
            # Offer the station's catalog so the fuel is always bound to a unified name
            options = get_all_products(check.draft.get("station_name"))
            await state.update_data(_fuel_options=options)
            markup = photo_fuel_keyboard(options, keep_name=check.draft.get("fuel_type"))
        sent = await message.answer(
            _format_clarify(check, warnings, settings.currency),
            reply_markup=markup,
            parse_mode="HTML",
        )
        await track_prompt(state, sent)
        return

    await state.set_state(PhotoFuelStates.preview)
    text, markup = await _preview(state, user_id)
    sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
    await track_prompt(state, sent)


def _format_known(draft: dict[str, Any], currency: str) -> list[str]:
    """Lines for the fields recognized so far (used while data is incomplete)."""
    lines: list[str] = []
    if draft.get("date"):
        lines.append(f"📅 Дата: {fmt_date(date.fromisoformat(draft['date']))}")
    if draft.get("odometer_km"):
        lines.append(f"🚗 Пробіг: {fmt_num(draft['odometer_km'], 0)} км")
    if draft.get("station_name"):
        lines.append(f"⛽ АЗС: <b>{html_escape(draft['station_name'])}</b>")
    if draft.get("fuel_type"):
        lines.append(f"🧾 Пальне: <b>{html_escape(draft['fuel_type'])}</b>")
    if draft.get("liters"):
        lines.append(f"🔢 Літри: {fmt_num(draft['liters'])} л")
    if draft.get("total_price"):
        lines.append(f"💰 Сума: {fmt_num(draft['total_price'], 0)} {currency}")
    if draft.get("discount"):
        lines.append(f"🏷 Знижка: −{fmt_num(draft['discount'], 0)} {currency}")
    return lines


def _format_duplicate(check: DraftCheck, currency: str) -> str:
    dup = check.duplicate
    summary = " · ".join(
        part
        for part in (
            f"📅 {fmt_date(dup.date)}",
            f"🚗 {fmt_num(dup.odometer_km, 0)} км",
            f"🔢 {fmt_num(dup.liters)} л",
            f"💰 {fmt_num(dup.total_price, 0)} {currency}",
            html_escape(dup.station_name) if dup.station_name else "",
        )
        if part
    )
    return (
        f"<b>{TITLE}</b>\n\n"
        "⚠️ <b>Ця заправка вже є в базі</b>, повторно не додаю:\n"
        f"{summary}\n\n"
        "Якщо це <b>інша</b> заправка — надішли правильний пробіг "
        f"(числом, напр. {code('151253')}, або фото одометра).\n"
        "Інакше просто натисни «Скасувати»."
    )


def _format_clarify(check: DraftCheck, warnings: list[str], currency: str) -> str:
    if check.duplicate is not None:
        return _format_duplicate(check, currency)
    lines = [f"<b>{TITLE}</b>\n"]
    known = _format_known(check.draft, currency)
    if known:
        lines.append("<b>Вже розпізнав:</b>")
        lines.extend(known)
        lines.append("")
    lines.append("<b>Не вистачає:</b>")
    lines.extend(FIELD_HINTS[name] for name in check.missing if name in FIELD_HINTS)
    if warnings or check.infos:
        lines.append("")
        lines.extend(f"⚠️ {html_escape(w)}" for w in warnings[:5])
        lines.extend(f"ℹ️ {html_escape(i)}" for i in check.infos)
    lines.append("")
    if check.missing == [MISSING_FUEL]:
        lines.append("Обери пальне кнопкою нижче або напиши назву 👇")
    elif len(check.missing) == 1:
        lines.append("Просто надішли відповідь одним повідомленням 👇")
    else:
        lines.append(
            "Надішли відповідь одним повідомленням (можна все разом) "
            "або ще одне фото 👇"
        )
    return "\n".join(lines)


async def _preview(state: FSMContext, user_id: int):
    """Build preview text and keyboard from the current (complete) draft."""
    data = await state.get_data()
    draft = data["draft"]
    settings = await db.ensure_user(user_id)
    car = await db.get_car_by_id(data["car_id"], user_id) or await db.get_active_car(user_id)
    record = draft_to_record_data(draft)

    lines = [
        "📋 <b>Перевір розпізнану заправку</b>\n",
        f"🚘 Авто: <b>{html_escape(car.name)}</b>",
        _format_confirmation(record, settings.currency),
    ]
    warnings = data.get("warnings") or []
    infos = data.get("infos") or []
    if warnings or infos:
        lines.append("")
        lines.extend(f"⚠️ {html_escape(w)}" for w in warnings[:5])
        lines.extend(f"ℹ️ {html_escape(i)}" for i in infos)
    lines.extend([
        "",
        "Щось не так — натисни «✏️ Виправити» або просто напиши виправлення.",
    ])
    markup = photo_preview_keyboard(full_tank=record["full_tank"], has_note=bool(record["note"]))
    return "\n".join(lines), markup


async def _edit_preview(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PhotoFuelStates.preview)
    text, markup = await _preview(state, callback.from_user.id)
    await safe_edit_text(callback.message, text, reply_markup=markup, parse_mode="HTML")
    await track_prompt(state, callback.message)


# --- Entry points ---

@router.callback_query(F.data == MENU_ADD_PHOTO)
@safe_callback
async def callback_add_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await db.ensure_tg_user(callback.from_user)
    await callback.answer()
    if await _start_flow(callback.message, state, callback.from_user.id, edit=True):
        await safe_edit_text(
            callback.message,
            AWAIT_INPUT_TEXT,
            reply_markup=photo_cancel_keyboard(),
            parse_mode="HTML",
        )


@router.message(Command("photo"))
async def cmd_photo(message: Message, state: FSMContext) -> None:
    await db.ensure_tg_user(message.from_user)
    if await _start_flow(message, state, message.from_user.id, edit=False):
        await message.answer(AWAIT_INPUT_TEXT, reply_markup=photo_cancel_keyboard(), parse_mode="HTML")


@router.message(StateFilter(None), F.photo)
@router.message(StateFilter(None), F.document.mime_type.startswith("image/"))
async def photo_without_flow(message: Message, state: FSMContext) -> None:
    """A photo sent outside any wizard starts the photo flow right away."""
    user_id = message.from_user.id
    # Album photos arrive concurrently: only the first one starts the flow, the rest just queue
    already_starting = bool(_buffers.get(user_id))
    _enqueue(message, state)
    if already_starting:
        return
    await db.ensure_tg_user(message.from_user)
    if not await _start_flow(message, state, user_id, edit=False, keep_buffer=True):
        _drop_buffer(user_id)


# --- Input during the flow ---

@router.message(
    StateFilter(PhotoFuelStates.await_input, PhotoFuelStates.clarify, PhotoFuelStates.preview),
    F.photo | F.document | F.text,
)
async def photo_flow_input(message: Message, state: FSMContext) -> None:
    if message.document and not (message.document.mime_type or "").startswith("image/"):
        await message.answer(
            "Тут потрібні фото чека / табла. Для CSV чи Excel скористайся AI-імпортом у налаштуваннях."
        )
        return
    _enqueue(message, state)


@router.message(PhotoFuelStates.note)
async def process_photo_note(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if not note:
        await message.answer("Напиши примітку текстом або повернись до перевірки.")
        return
    if len(note) > NOTE_MAX_LENGTH:
        await message.answer(
            f"⚠️ Примітка задовга ({len(note)} символів). Максимум — {NOTE_MAX_LENGTH}."
        )
        return

    data = await state.get_data()
    draft = dict(data["draft"])
    draft["note"] = None if note == "-" else note
    await state.update_data(draft=draft)
    await clear_tracked_prompt(message.bot, state)
    await state.set_state(PhotoFuelStates.preview)
    text, markup = await _preview(state, message.from_user.id)
    sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
    await track_prompt(state, sent)


@router.message(PhotoFuelStates.car_pick)
async def photo_car_hint(message: Message) -> None:
    await message.answer("Обери авто кнопкою.")


# --- Preview actions ---

@router.callback_query(F.data == PHOTO_TOGGLE_FULL, PhotoFuelStates.preview)
@safe_callback
async def callback_photo_toggle_full(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = dict(data["draft"])
    draft["full_tank"] = not bool(draft.get("full_tank", True))
    await state.update_data(draft=draft)
    await callback.answer()
    await _edit_preview(callback, state)


@router.callback_query(F.data == PHOTO_NOTE, PhotoFuelStates.preview)
@safe_callback
async def callback_photo_note(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    has_note = bool(data["draft"].get("note"))
    await state.set_state(PhotoFuelStates.note)
    await callback.answer()
    text = (
        "📝 Напиши примітку до заправки одним повідомленням.\n\n"
        "Наприклад: <i>Поїздка у Львів</i>"
    )
    if has_note:
        text += f"\n\nЩоб прибрати примітку, надішли {code('-')}"
    await safe_edit_text(callback.message, text, reply_markup=photo_back_keyboard(), parse_mode="HTML")
    await track_prompt(state, callback.message)


@router.callback_query(F.data == PHOTO_EDIT, PhotoFuelStates.preview)
@safe_callback
async def callback_photo_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await safe_edit_text(
        callback.message,
        (
            "✏️ Напиши, що виправити, наприклад:\n"
            f"{code('пробіг 151300')}\n"
            f"{code('літри 45.2')}\n"
            f"{code('знижка 120')} або {code('без знижки')}\n"
            f"{code('АЗС WOG, пальне 95 Mustang')}\n\n"
            "Або надішли інше / додаткове фото."
        ),
        reply_markup=photo_back_keyboard(),
        parse_mode="HTML",
    )
    await track_prompt(state, callback.message)


@router.callback_query(F.data == PHOTO_CAR, PhotoFuelStates.preview)
@safe_callback
async def callback_photo_car(callback: CallbackQuery, state: FSMContext) -> None:
    cars = await db.get_user_cars(callback.from_user.id)
    await state.set_state(PhotoFuelStates.car_pick)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🔄 <b>Обери авто для заправки:</b>",
        reply_markup=cars_list_keyboard(cars, prefix=PHOTO_CAR_PICK_PREFIX, back_callback=PHOTO_BACK),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(PHOTO_CAR_PICK_PREFIX), PhotoFuelStates.car_pick)
@safe_callback
async def callback_photo_car_pick(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    car_id = int(callback.data.removeprefix(PHOTO_CAR_PICK_PREFIX))
    car = await db.get_car_by_id(car_id, user_id)
    if not car:
        await callback.answer("Авто не знайдено", show_alert=True)
        return

    await db.set_active_car(user_id, car_id)
    await state.update_data(car_id=car_id)
    await callback.answer(f"Обрано: {car.name}")

    # The odometer rule depends on the car, so re-validate before showing the preview
    data = await state.get_data()
    check = await _check(user_id, car_id, data["draft"])
    if check.missing:
        await safe_clear_markup(callback.message)
        await _show_result(callback.message, state, user_id, car_id, data["draft"], problems=[])
        return
    await state.update_data(
        draft=check.draft, missing=[], warnings=check.warnings, infos=check.infos
    )
    await _edit_preview(callback, state)


@router.callback_query(F.data.startswith(PHOTO_FUEL_PREFIX), PhotoFuelStates.clarify)
@safe_callback
async def callback_photo_fuel(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = dict(data["draft"])
    suffix = callback.data.removeprefix(PHOTO_FUEL_PREFIX)

    if callback.data == PHOTO_FUEL_KEEP:
        if not draft.get("fuel_type"):
            await callback.answer("Немає назви з чека — обери зі списку", show_alert=True)
            return
    else:
        try:
            product = (data.get("_fuel_options") or [])[int(suffix)]
        except (ValueError, IndexError):
            await callback.answer("Невідомий варіант", show_alert=True)
            return
        if draft.get("fuel_type") and draft["fuel_type"] != product:
            draft.setdefault("fuel_receipt_name", draft["fuel_type"])
        draft["fuel_type"] = product
    draft["fuel_confirmed"] = True

    await callback.answer()
    await safe_clear_markup(callback.message)
    user_id = callback.from_user.id
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id
    await _show_result(callback.message, state, user_id, car_id, draft, problems=[])


@router.callback_query(
    F.data == PHOTO_BACK,
    StateFilter(PhotoFuelStates.preview, PhotoFuelStates.note, PhotoFuelStates.car_pick),
)
@safe_callback
async def callback_photo_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _edit_preview(callback, state)


@router.callback_query(F.data == PHOTO_SAVE, PhotoFuelStates.preview)
@safe_callback
async def callback_photo_save(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    car_id = data.get("car_id") or (await db.get_active_car(user_id)).id

    check = await _check(user_id, car_id, data["draft"])
    if check.missing:
        await callback.answer("Не вистачає даних", show_alert=True)
        await safe_clear_markup(callback.message)
        await _show_result(callback.message, state, user_id, car_id, data["draft"], problems=[])
        return

    record = draft_to_record_data(check.draft)
    record_id = await db.add_refuel(
        user_id,
        car_id=car_id,
        refuel_date=record["refuel_date"],
        odometer_km=record["odometer_km"],
        liters=record["liters"],
        price_per_liter=record["price_per_liter"],
        total_price=record["total_price"],
        fuel_type=record["fuel_type"],
        station_name=record["station_name"],
        full_tank=record["full_tank"],
        note=record["note"],
        discount=record["discount"],
    )

    _drop_buffer(user_id)
    await state.clear()
    settings = await db.ensure_user(user_id)
    await callback.answer("Збережено")
    await safe_edit_text(
        callback.message,
        await build_save_summary(user_id, car_id, record_id, record, settings.currency),
        reply_markup=home_button_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == PHOTO_CANCEL)
@safe_callback
async def callback_photo_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    _drop_buffer(callback.from_user.id)
    await state.clear()
    await callback.answer("Скасовано")
    await safe_edit_text(
        callback.message,
        f"❌ {TITLE} — скасовано.\n\n" + MAIN_MENU_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
