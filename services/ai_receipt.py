"""Recognize a single refuel from receipt / dashboard photos and text via Gemini."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from services.ai_import import AIImportError, generate_structured
from services.fuel_products import POPULAR_STATIONS, catalog_prompt_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""\
Ти допомагаєш додати ОДНУ заправку в Telegram-бот обліку пального за фото та текстом користувача.

Що можна отримати:
- фото фіскального чека АЗС;
- фото приладової панелі (одометр — загальний пробіг авто);
- фото табло колонки;
- підпис чи повідомлення користувача (наприклад «151253» — це пробіг у км, «повний бак», «знижка 2 грн/л»).

Заповни поля:
- date: дата заправки YYYY-MM-DD (з чека). Якщо дати ніде немає — null.
- odometer_km: ЗАГАЛЬНИЙ пробіг з одометра (не добовий лічильник trip A/B, не запас ходу). \
Число в підписі користувача на кшталт «151253» чи «пробіг 151 253» — це odometer_km.
- liters: кількість літрів саме пального.
- price_per_liter: ціна за літр ДО знижки (ціна з табло / ціна в рядку товару).
- total_price: вартість пального ДО знижки. Не включай у неї каву, їжу, мийку та інші товари з чека.
- discount: сума всіх знижок на пальне (додатне число). Знижку на літр помнож на літри. Немає — null.
- paid_amount: скільки фактично сплачено за пальне після знижки, якщо видно.
- fuel_type: ТОЧНА назва пального з довідника нижче для цієї АЗС \
(наприклад «Бенз.авто А-95-Євро5-E10» на ОККО → «А-95 Євро», «PULLS 95» → «Pulls 95»). \
Якщо однозначно відповідної назви в довіднику немає — напиши назву як на чеку.
- station_name: мережа АЗС (відомі: {", ".join(POPULAR_STATIONS)}). Не місто і не адреса. Немає — null.
- full_tank: true лише якщо користувач прямо каже про повний бак, false — якщо каже, що неповний; інакше null.
- note: коротка примітка, лише якщо користувач сам її написав. Інакше null.
- is_refuel: false, якщо на фото взагалі немає даних про заправку.
- problems: список українською, що не вдалося прочитати чи що виглядає підозріло \
(розмите фото, кілька видів пального в чеку тощо). Порожній, якщо все добре.

Правила:
1. НІКОЛИ не вигадуй значень. Якщо не видно — null.
2. Числа: кома або крапка як десятковий роздільник; без валюти й одиниць.
3. Якщо передано поточну чернетку — збережи її значення і зміни лише те, що уточнює нове \
повідомлення чи фото. Пряме виправлення користувача («пробіг 151300», «АЗС WOG») має пріоритет.
4. Якщо користувач виправляє ціну за літр або літри — перерахуй total_price = price_per_liter * liters.
5. Відповідай лише структурованим JSON за схемою.

Довідник пального (уніфіковані назви):
{catalog_prompt_text()}
"""


class ReceiptAIResult(BaseModel):
    is_refuel: bool = True
    date: str | None = None
    odometer_km: float | None = None
    liters: float | None = None
    price_per_liter: float | None = None
    total_price: float | None = None
    discount: float | None = None
    paid_amount: float | None = None
    fuel_type: str | None = None
    station_name: str | None = None
    full_tank: bool | None = None
    note: str | None = None
    problems: list[str] = Field(default_factory=list)


@dataclass
class ReceiptInput:
    """One batch of user input: photos (raw bytes + mime type) and texts."""

    images: list[tuple[bytes, str]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)


def _build_prompt_text(
    payload: ReceiptInput,
    *,
    draft: dict[str, Any] | None,
    last_odometer: float | None,
    currency: str,
) -> str:
    parts = [
        f"Сьогодні: {date.today().isoformat()}. Валюта користувача: {currency}.",
    ]
    if last_odometer:
        parts.append(
            f"Останній відомий пробіг цього авто: {last_odometer:.0f} км "
            "(новий пробіг має бути більшим)."
        )
    if draft:
        parts.append(
            "Поточна чернетка заправки (онови її новими даними):\n"
            + json.dumps(draft, ensure_ascii=False, default=str)
        )
    if payload.images:
        parts.append(f"Фото у повідомленні: {len(payload.images)}.")
    if payload.texts:
        parts.append("Текст користувача:\n" + "\n".join(t.strip() for t in payload.texts))
    else:
        parts.append("Текстового підпису немає.")
    return "\n\n".join(parts)


async def recognize_refuel(
    payload: ReceiptInput,
    *,
    draft: dict[str, Any] | None = None,
    last_odometer: float | None = None,
    currency: str = "грн",
) -> ReceiptAIResult:
    """Ask Gemini to extract (or update) one refuel from photos and text."""
    try:
        from google.genai import types
    except ImportError as exc:
        raise AIImportError(
            "Пакет google-genai не встановлено. Виконай: pip install google-genai"
        ) from exc

    contents: list[Any] = [
        types.Part.from_bytes(data=data, mime_type=mime) for data, mime in payload.images
    ]
    contents.append(
        _build_prompt_text(
            payload,
            draft=draft,
            last_odometer=last_odometer,
            currency=currency,
        )
    )
    return await generate_structured(
        contents,
        schema=ReceiptAIResult,
        system_prompt=SYSTEM_PROMPT,
        log_label="receipt recognition",
    )
