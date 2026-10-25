"""Deterministic checks for a single AI-recognized refuel draft before saving."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from services.ai_receipt import ReceiptAIResult
from database import RefuelRecord
from services.calculations import odometer_order_error, parse_date, parse_number
from services.fuel_products import match_fuel_product, normalize_station_name

# Draft fields kept in FSM storage (JSON-friendly values only)
DRAFT_FIELDS = (
    "date",
    "odometer_km",
    "liters",
    "price_per_liter",
    "total_price",
    "discount",
    "fuel_type",
    "station_name",
    "full_tank",
    "note",
)

# Required fields that the user may be asked to fill in, in display order
MISSING_ODOMETER = "odometer_km"
MISSING_LITERS = "liters"
MISSING_PRICE = "total_price"
MISSING_FUEL = "fuel_type"
MISSING_DATE = "date"


@dataclass
class DraftCheck:
    """Result of validating a draft: normalized values, gaps, and soft warnings."""

    draft: dict[str, Any]
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    # Existing refuel (database.RefuelRecord) that this draft duplicates, set by the handler
    duplicate: Any = None

    @property
    def is_complete(self) -> bool:
        return not self.missing


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = parse_number(str(value))
        except (ValueError, TypeError):
            return None
    return number if number > 0 else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def draft_from_ai(result: ReceiptAIResult, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert an AI result into a draft, keeping user-set fields the AI did not return."""
    draft = dict(previous or {})
    total = _num(result.total_price)
    discount = _num(result.discount)
    paid = _num(result.paid_amount)
    # An explicit zero means "no discount" and must override an older draft value
    if result.discount is not None and discount is None:
        discount = 0.0

    # Receipt shows only paid sum and discount: restore the pre-discount total
    if total is None and paid is not None and discount:
        total = round(paid + discount, 2)
    # Receipt shows full and paid sums: derive the discount
    if result.discount is None and total is not None and paid is not None and paid < total:
        discount = round(total - paid, 2)

    recognized = {
        "date": _text(result.date),
        "odometer_km": _num(result.odometer_km),
        "liters": _num(result.liters),
        "price_per_liter": _num(result.price_per_liter),
        "total_price": total,
        "discount": discount,
        "fuel_type": _text(result.fuel_type),
        "station_name": _text(result.station_name),
        "full_tank": result.full_tank,
        "note": _text(result.note),
    }
    for key, value in recognized.items():
        if value is not None:
            draft[key] = value
    if recognized["fuel_type"] is not None or recognized["station_name"] is not None:
        # New fuel / station data must be matched against the catalog again
        draft.pop("fuel_confirmed", None)
    if recognized["fuel_type"] is not None:
        draft.pop("fuel_receipt_name", None)
    if recognized["date"] is not None:
        draft.pop("date_assumed", None)
    return draft


def draft_date(draft: dict[str, Any]) -> date | None:
    """Parse the draft date, or None when it is missing or unreadable."""
    if not draft.get("date"):
        return None
    try:
        return parse_date(str(draft["date"]))
    except (ValueError, TypeError):
        return None


def check_draft(
    draft: dict[str, Any],
    *,
    neighbors: tuple[RefuelRecord | None, RefuelRecord | None] = (None, None),
) -> DraftCheck:
    """Normalize the draft, fill computable fields, and list what is still missing.

    Args:
        draft: Draft values (see DRAFT_FIELDS).
        neighbors: Refuels just before / after the draft date (see get_refuel_neighbors);
            the odometer must fit between them.
    """
    result = dict(draft)
    missing: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    refuel_date = draft_date(result)
    if refuel_date is None:
        refuel_date = date.today()
        # Remember the guess so the warning survives later re-checks of the draft
        result["date_assumed"] = True
    if result.get("date_assumed"):
        warnings.append("Дату не знайдено — поставив сьогоднішню.")
    if refuel_date > date.today():
        missing.append(MISSING_DATE)
        warnings.append(f"Дата {refuel_date.strftime('%d.%m.%Y')} у майбутньому.")
    result["date"] = refuel_date.isoformat()

    odometer = _num(result.get("odometer_km"))
    if odometer is None:
        missing.append(MISSING_ODOMETER)
    else:
        order_error = odometer_order_error(odometer, *neighbors)
        if order_error:
            missing.append(MISSING_ODOMETER)
            warnings.append(order_error)
    result["odometer_km"] = odometer

    liters = _num(result.get("liters"))
    price = _num(result.get("price_per_liter"))
    total = _num(result.get("total_price"))
    if liters is None:
        missing.append(MISSING_LITERS)
    if liters is not None:
        if total is None and price is not None:
            total = round(price * liters, 2)
        if total is not None:
            # Same rule as the manual "receipt total" mode: price follows the total
            computed = round(total / liters, 2)
            if price is not None and abs(computed - price) > max(0.5, price * 0.03):
                warnings.append(
                    f"Ціна за літр на чеку ({price:.2f}) не збігається із сумою / літрами "
                    f"({computed:.2f}) — перевір суму та літри."
                )
            price = computed
    if total is None:
        missing.append(MISSING_PRICE)
    result["liters"] = liters
    result["price_per_liter"] = price
    result["total_price"] = total

    discount = _num(result.get("discount")) or 0.0
    if total is not None and discount >= total:
        warnings.append("Знижка не менша за суму чека — знижку не враховано.")
        discount = 0.0
    result["discount"] = round(discount, 2)

    station = _text(result.get("station_name"))
    station = normalize_station_name(station) if station else None
    result["station_name"] = station

    fuel_type = _text(result.get("fuel_type"))
    if not fuel_type:
        missing.append(MISSING_FUEL)
    elif not result.get("fuel_confirmed"):
        canonical = match_fuel_product(station, fuel_type)
        if canonical is None:
            # Unknown name: the user picks a catalog product or keeps the receipt name
            missing.append(MISSING_FUEL)
            warnings.append(f"Не впізнав пальне «{fuel_type}» — обери його зі списку.")
        elif canonical != fuel_type:
            result.setdefault("fuel_receipt_name", fuel_type)
            fuel_type = canonical
    result["fuel_type"] = fuel_type
    receipt_name = result.get("fuel_receipt_name")
    if receipt_name and fuel_type and receipt_name != fuel_type:
        infos.append(f"Пальне з чека «{receipt_name}» → {fuel_type}")

    note = _text(result.get("note"))
    result["note"] = note

    if result.get("full_tank") is None:
        result["full_tank"] = True

    return DraftCheck(draft=result, missing=missing, warnings=warnings, infos=infos)


def apply_direct_answer(draft: dict[str, Any], missing: list[str], text: str) -> bool:
    """Fill the only missing field straight from a short reply, without calling AI.

    Returns True when the reply was applied.
    """
    if len(missing) != 1:
        return False
    field_name = missing[0]
    cleaned = text.strip()

    if field_name == MISSING_FUEL:
        if not cleaned or len(cleaned) > 40:
            return False
        # A typed name is the user's choice: use the catalog name when it matches, else keep as typed
        station = _text(draft.get("station_name"))
        draft["fuel_type"] = match_fuel_product(station, cleaned) or cleaned
        draft["fuel_confirmed"] = True
        return True

    if field_name in (MISSING_ODOMETER, MISSING_LITERS, MISSING_PRICE):
        value = _num(cleaned.replace("км", "").replace("л", ""))
        if value is None:
            return False
        draft[field_name] = value
        return True

    return False


def draft_to_record_data(draft: dict[str, Any]) -> dict[str, Any]:
    """Map a complete draft onto the add-refuel FSM data shape used for display and save."""
    return {
        "refuel_date": date.fromisoformat(draft["date"]),
        "odometer_km": float(draft["odometer_km"]),
        "liters": float(draft["liters"]),
        "price_per_liter": float(draft["price_per_liter"]),
        "total_price": float(draft["total_price"]),
        "discount": float(draft.get("discount") or 0.0),
        "fuel_type": str(draft["fuel_type"]),
        "station_name": draft.get("station_name"),
        "full_tank": bool(draft.get("full_tank", True)),
        "note": draft.get("note"),
    }
