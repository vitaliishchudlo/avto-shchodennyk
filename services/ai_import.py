"""Map arbitrary user fuel-tracker data onto refuel schema via Gemini."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ти допомагаєш імпортувати історію заправок у Telegram-бот обліку пального.

Цільова структура ОДНОГО запису заправки:
- date (обов'язково): дата YYYY-MM-DD
- odometer_km (обов'язково): пробіг / одометр у км (число > 0)
- liters (обов'язково): літри (число > 0)
- price_per_liter (обов'язково): ціна за літр; можна обчислити як total_price / liters
- total_price (обов'язково): загальна сума; можна обчислити як price_per_liter * liters
- fuel_type (обов'язково): назва пального (Pulls 95, А-95, ДП Євро, газ тощо). \
Одне поле — і категорія, і конкретна марка. Якщо є і тип і продукт — обери найконкретніше.
- station_name (опційно): лише мережа/назва АЗС (ОККО, WOG, SOCAR…). \
НЕ місто, область чи «локація» на кшталт «Івано-Франківськ». Якщо є лише місто — station_name = null.
- full_tank (опційно): true/false; якщо невідомо — null
- note (опційно): примітка, знижка, або зайва гео-локація якщо хочеш зберегти її текстом

Правила:
1. Користувачі ведуть трекери ПО-РІЗНОМУ: будь-які мови, назви колонок, порядок, формати дат.
2. Сам зрозумій сенс колонок і значень і піджени під цільову схему. Не вимагай фіксованих назв колонок.
3. Якщо є лише ціна за літр і літри — порахуй total_price. Якщо лише сума і літри — порахуй price_per_liter.
4. Дати нормалізуй у YYYY-MM-DD (розумій DD.MM.YYYY, MM/DD/YYYY, Excel-дати тощо).
5. Числа: крапка або кома як десятковий роздільник; ігноруй валютні символи та «км», «л».
6. НІКОЛИ не вигадуй пробіг, дату, літри, суми чи АЗС, яких немає в даних.
7. Гео-локацію (місто/область) не клади в station_name. Без АЗС — station_name = null.
8. Якщо якогось обов'язкового поля бракує і його неможливо обчислити — status=need_clarification,
   заповни missing і questions українською (що саме надіслати).
9. Якщо все можна зібрати — status=ok і records з усіма рядками.
10. Рядки без жодних даних про заправку пропускай.
11. Відповідай лише структурованим JSON за схемою.
"""


class MissingInfo(BaseModel):
    row: int = Field(description="1-based row number in the source data")
    fields: list[str] = Field(description="Missing required target field names")


class ColumnMapping(BaseModel):
    """One source-to-target mapping entry (list form for Gemini Developer API)."""

    source: str = Field(description="Original column / field name from user data")
    target: str = Field(description="Target schema field name, e.g. odometer_km")


class ImportRecord(BaseModel):
    date: str | None = None
    odometer_km: float | None = None
    liters: float | None = None
    price_per_liter: float | None = None
    total_price: float | None = None
    fuel_type: str | None = None
    station_name: str | None = None
    full_tank: bool | None = None
    note: str | None = None


class ImportAIResult(BaseModel):
    status: Literal["ok", "need_clarification"]
    column_mapping: list[ColumnMapping] = Field(default_factory=list)
    records: list[ImportRecord] = Field(default_factory=list)
    missing: list[MissingInfo] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class AIImportError(RuntimeError):
    """Raised when the AI provider fails or is not configured."""


def is_ai_configured() -> bool:
    return bool(GEMINI_API_KEY)


def _build_user_prompt(
    raw_rows: list[dict[str, Any]],
    *,
    clarification: str | None = None,
) -> str:
    payload = {
        "rows": raw_rows,
        "row_count": len(raw_rows),
    }
    parts = [
        "Ось дані користувача для імпорту (довільна структура):",
        json.dumps(payload, ensure_ascii=False, default=str),
    ]
    if clarification:
        parts.append(
            "Користувач надіслав уточнення / додаткові дані:\n" + clarification.strip()
        )
    parts.append("Піджени дані під схему заправок.")
    return "\n\n".join(parts)


async def map_import_payload(
    raw_rows: list[dict[str, Any]],
    *,
    clarification: str | None = None,
) -> ImportAIResult:
    """Ask Gemini to map arbitrary rows onto the refuel schema."""
    if not GEMINI_API_KEY:
        raise AIImportError(
            "AI не налаштовано. Додай GEMINI_API_KEY у файл .env "
            "(ключ з https://aistudio.google.com/apikey)."
        )

    try:
        from google import genai
    except ImportError as exc:
        raise AIImportError(
            "Пакет google-genai не встановлено. Виконай: pip install google-genai"
        ) from exc

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = _build_user_prompt(raw_rows, clarification=clarification)

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "response_schema": ImportAIResult,
                "temperature": 0.1,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gemini import mapping failed")
        message = str(exc)
        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            raise AIImportError(
                "Ліміт Gemini вичерпано (квота free tier).\n\n"
                f"Поточна модель: {GEMINI_MODEL}\n"
                "Спробуй пізніше або постав у .env іншу модель, напр.\n"
                "GEMINI_MODEL=gemini-3.5-flash-lite\n"
                "і перезапусти бота."
            ) from exc
        raise AIImportError(
            "Не вдалося обробити дані через AI. Спробуй ще раз пізніше."
        ) from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ImportAIResult):
        return parsed
    if isinstance(parsed, dict):
        return ImportAIResult.model_validate(parsed)

    text = getattr(response, "text", None) or ""
    if not text.strip():
        raise AIImportError("AI повернув порожню відповідь.")
    try:
        return ImportAIResult.model_validate_json(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse AI JSON: %s", text[:500])
        raise AIImportError("AI повернув некоректну відповідь. Спробуй ще раз.") from exc
