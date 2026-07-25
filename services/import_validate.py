"""Deterministic validation of AI-mapped import records before DB insert."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from services.ai_import import ImportAIResult, ImportRecord
from services.calculations import parse_date, parse_number


REQUIRED_FIELDS = (
    "date",
    "odometer_km",
    "liters",
    "price_per_liter",
    "total_price",
    "fuel_type",
)


@dataclass
class ValidatedRefuel:
    refuel_date: date
    odometer_km: float
    liters: float
    price_per_liter: float
    total_price: float
    fuel_type: str
    station_name: str | None
    full_tank: bool
    note: str | None


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return parse_number(str(value))
    except (ValueError, TypeError):
        return None


def _parse_record_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    try:
        return parse_date(text)
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _complete_prices(
    liters: float | None,
    price_per_liter: float | None,
    total_price: float | None,
) -> tuple[float | None, float | None]:
    if liters and liters > 0:
        if price_per_liter is None and total_price is not None and total_price > 0:
            price_per_liter = round(total_price / liters, 4)
        if total_price is None and price_per_liter is not None and price_per_liter > 0:
            total_price = round(price_per_liter * liters, 2)
    return price_per_liter, total_price


def validate_ai_result(
    result: ImportAIResult,
) -> tuple[list[ValidatedRefuel], list[str]]:
    """Validate AI output into insertable records and human-readable issues."""
    issues: list[str] = []

    if result.status == "need_clarification" or result.questions:
        issues.extend(q.strip() for q in result.questions if q and q.strip())
        for miss in result.missing:
            fields = ", ".join(miss.fields) if miss.fields else "?"
            issues.append(f"Рядок {miss.row}: не вистачає полів ({fields}).")

    validated: list[ValidatedRefuel] = []
    for idx, raw in enumerate(result.records, start=1):
        item, row_issues = _validate_one(raw, idx)
        issues.extend(row_issues)
        if item is not None:
            validated.append(item)

    if not validated and not issues:
        issues.append(
            "Не вдалося розпізнати жодного запису заправки. "
            "Надішли CSV/Excel або текст з датами, пробігом, літрами та ціною."
        )

    seen: set[str] = set()
    unique_issues: list[str] = []
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            unique_issues.append(issue)

    return validated, unique_issues


def _validate_one(
    raw: ImportRecord,
    row_no: int,
) -> tuple[ValidatedRefuel | None, list[str]]:
    issues: list[str] = []
    refuel_date = _parse_record_date(raw.date)
    odometer = _parse_optional_number(raw.odometer_km)
    liters = _parse_optional_number(raw.liters)
    price = _parse_optional_number(raw.price_per_liter)
    total = _parse_optional_number(raw.total_price)
    price, total = _complete_prices(liters, price, total)
    fuel_type = _as_optional_str(raw.fuel_type)

    missing: list[str] = []
    if refuel_date is None:
        missing.append("date")
    elif refuel_date > date.today():
        issues.append(f"Рядок {row_no}: дата в майбутньому ({refuel_date}).")
        return None, issues

    if odometer is None or odometer <= 0:
        missing.append("odometer_km")
    if liters is None or liters <= 0:
        missing.append("liters")
    if price is None or price <= 0:
        missing.append("price_per_liter")
    if total is None or total <= 0:
        missing.append("total_price")
    if not fuel_type:
        missing.append("fuel_type")

    if missing:
        issues.append(
            f"Рядок {row_no}: не вистачає або некоректні поля ({', '.join(missing)})."
        )
        return None, issues

    assert refuel_date is not None
    assert odometer is not None
    assert liters is not None
    assert price is not None
    assert total is not None
    assert fuel_type is not None

    return (
        ValidatedRefuel(
            refuel_date=refuel_date,
            odometer_km=odometer,
            liters=liters,
            price_per_liter=price,
            total_price=total,
            fuel_type=fuel_type,
            station_name=_as_optional_str(raw.station_name),
            full_tank=bool(raw.full_tank) if raw.full_tank is not None else False,
            note=_as_optional_str(raw.note),
        ),
        issues,
    )


def records_to_fsm_dicts(records: list[ValidatedRefuel]) -> list[dict[str, Any]]:
    """Serialize validated records for FSM storage (JSON-friendly)."""
    return [
        {
            "refuel_date": r.refuel_date.isoformat(),
            "odometer_km": r.odometer_km,
            "liters": r.liters,
            "price_per_liter": r.price_per_liter,
            "total_price": r.total_price,
            "fuel_type": r.fuel_type,
            "station_name": r.station_name,
            "full_tank": r.full_tank,
            "note": r.note,
        }
        for r in records
    ]


def fsm_dicts_to_records(data: list[dict[str, Any]]) -> list[ValidatedRefuel]:
    """Restore validated records from FSM data."""
    result: list[ValidatedRefuel] = []
    for item in data:
        result.append(
            ValidatedRefuel(
                refuel_date=date.fromisoformat(item["refuel_date"]),
                odometer_km=float(item["odometer_km"]),
                liters=float(item["liters"]),
                price_per_liter=float(item["price_per_liter"]),
                total_price=float(item["total_price"]),
                fuel_type=str(item["fuel_type"]),
                station_name=item.get("station_name"),
                full_tank=bool(item.get("full_tank", False)),
                note=item.get("note"),
            )
        )
    return result
