"""Module: calculations
Description: Parsing, formatting, and fuel consumption statistics for fuel entries.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from database import RefuelRecord


@dataclass
class TripStats:
    """Per-segment metrics between two consecutive fuel entries."""

    distance_km: float
    consumption_l_per_100km: float
    cost_per_100km: float
    cost_per_km: float


@dataclass
class OverallStats:
    """Aggregated statistics over a list of fuel entries."""

    total_refuels: int
    total_liters: float
    total_spent: float
    total_distance_km: float
    avg_consumption: float | None
    avg_price_per_liter: float
    avg_cost_per_100km: float | None
    avg_cost_per_km: float | None
    most_expensive: RefuelRecord | None
    largest_liters: RefuelRecord | None
    last_refuel: RefuelRecord | None
    period_start: datetime | None
    period_end: datetime | None
    most_common_station: str | None = None
    most_common_fuel_type: str | None = None
    most_common_fuel_product: str | None = None
    avg_price_by_fuel_type: dict[str, float] = field(default_factory=dict)


def parse_number(text: str) -> float:
    """Parse a number that uses either a dot or comma as the decimal separator.

    Args:
        text: Raw numeric string, optionally with spaces.

    Returns:
        Parsed float value.

    Raises:
        ValueError: If the string is not a valid number.
    """
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    return float(cleaned)


def format_number(value: float, decimals: int = 1) -> str:
    """Format a number with spaces as thousands separators (Ukrainian locale style).

    Args:
        value: Number to format.
        decimals: Decimal places to show; 0 rounds to an integer.

    Returns:
        Locale-formatted string.
    """
    if decimals == 0:
        return f"{round(value):,}".replace(",", " ")

    formatted = f"{value:,.{decimals}f}"
    int_part, _, dec_part = formatted.partition(".")
    return f"{int_part.replace(',', ' ')},{dec_part}"


def parse_date(text: str) -> date:
    """Parse a date from common day-first and ISO formats.

    Supported patterns include DD.MM.YYYY, D.M.YYYY, YYYY-MM-DD, and DD/MM/YYYY.

    Args:
        text: Date string to parse.

    Returns:
        Parsed date.

    Raises:
        ValueError: If no supported format matches.
    """
    cleaned = text.strip()
    formats = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y")
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    parts = re.split(r"[.\-/]", cleaned)
    if len(parts) == 3:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year += 2000
        return date(year, month, day)

    raise ValueError("invalid date")


def _most_common(values: list[str]) -> str | None:
    """Return the most frequent non-empty string, or None if the list is empty."""
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _avg_price_by_type(refuels: list[RefuelRecord]) -> dict[str, float]:
    """Compute average price per liter grouped by fuel type."""
    buckets: dict[str, list[float]] = {}
    for r in refuels:
        buckets.setdefault(r.fuel_type, []).append(r.price_per_liter)
    return {
        fuel_type: sum(prices) / len(prices)
        for fuel_type, prices in buckets.items()
        if prices
    }


def format_date(dt: datetime | date) -> str:
    """Format a date as DD.MM.YYYY."""
    return dt.strftime("%d.%m.%Y")


def format_datetime(dt: datetime) -> str:
    """Format a datetime as DD.MM.YYYY HH:MM."""
    return dt.strftime("%d.%m.%Y %H:%M")


def calc_trip_stats(
    current: RefuelRecord,
    previous: RefuelRecord | None,
) -> TripStats | None:
    """Compute trip metrics between two consecutive fuel entries.

    Args:
        current: The newer fuel entry.
        previous: The preceding fuel entry, if any.

    Returns:
        TripStats when odometer distance is positive; otherwise None.
    """
    if not previous:
        return None

    distance = current.odometer_km - previous.odometer_km
    if distance <= 0:
        return None

    consumption = current.liters / distance * 100
    cost_per_100 = current.total_price / distance * 100
    cost_per_km = current.total_price / distance

    return TripStats(
        distance_km=distance,
        consumption_l_per_100km=consumption,
        cost_per_100km=cost_per_100,
        cost_per_km=cost_per_km,
    )


def calc_full_trip_stats(
    current: RefuelRecord,
    previous: RefuelRecord | None,
) -> TripStats | None:
    """Full trip analysis between two fuel entries (alias for calc_trip_stats).

    Args:
        current: The newer fuel entry.
        previous: The preceding fuel entry, if any.

    Returns:
        TripStats when odometer distance is positive; otherwise None.
    """
    return calc_trip_stats(current, previous)


def calc_overall_stats(refuels: list[RefuelRecord]) -> OverallStats:
    """Aggregate statistics across chronologically ordered fuel entries.

    Args:
        refuels: Fuel entries sorted by date (ascending).

    Returns:
        OverallStats with totals, averages, and highlights; empty stats if no entries.
    """
    if not refuels:
        return OverallStats(
            total_refuels=0,
            total_liters=0,
            total_spent=0,
            total_distance_km=0,
            avg_consumption=None,
            avg_price_per_liter=0,
            avg_cost_per_100km=None,
            avg_cost_per_km=None,
            most_expensive=None,
            largest_liters=None,
            last_refuel=None,
            period_start=None,
            period_end=None,
        )

    total_liters = sum(r.liters for r in refuels)
    total_spent = sum(r.total_price for r in refuels)
    most_expensive = max(refuels, key=lambda r: r.total_price)
    largest_liters = max(refuels, key=lambda r: r.liters)
    last_refuel = refuels[-1]

    # Odometer distance between the first and last fuel entry
    total_distance = refuels[-1].odometer_km - refuels[0].odometer_km

    # Average consumption: liters between consecutive entries / total distance * 100
    # Only segments with positive odometer delta are included
    segment_liters = 0.0
    segment_distance = 0.0
    for i in range(1, len(refuels)):
        dist = refuels[i].odometer_km - refuels[i - 1].odometer_km
        if dist > 0:
            segment_liters += refuels[i].liters
            segment_distance += dist

    avg_consumption = (segment_liters / segment_distance * 100) if segment_distance > 0 else None
    avg_cost_per_100 = (total_spent / segment_distance * 100) if segment_distance > 0 else None
    avg_cost_per_km = (total_spent / segment_distance) if segment_distance > 0 else None
    avg_price_per_liter = total_spent / total_liters if total_liters > 0 else 0

    stations = [r.station_name for r in refuels if r.station_name]
    fuel_types = [r.fuel_type for r in refuels]
    products = [r.fuel_product_name for r in refuels if r.fuel_product_name]

    return OverallStats(
        total_refuels=len(refuels),
        total_liters=total_liters,
        total_spent=total_spent,
        total_distance_km=max(total_distance, 0),
        avg_consumption=avg_consumption,
        avg_price_per_liter=avg_price_per_liter,
        avg_cost_per_100km=avg_cost_per_100,
        avg_cost_per_km=avg_cost_per_km,
        most_expensive=most_expensive,
        largest_liters=largest_liters,
        last_refuel=last_refuel,
        period_start=refuels[0].date,
        period_end=refuels[-1].date,
        most_common_station=_most_common(stations),
        most_common_fuel_type=_most_common(fuel_types),
        most_common_fuel_product=_most_common(products),
        avg_price_by_fuel_type=_avg_price_by_type(refuels),
    )


def calc_consumption_for_record(
    record: RefuelRecord,
    previous: RefuelRecord | None,
) -> float | None:
    """Compute consumption (L/100 km) for one fuel entry relative to the previous one.

    Args:
        record: Current fuel entry.
        previous: Preceding fuel entry, if any.

    Returns:
        Consumption in liters per 100 km, or None when not computable.
    """
    if not previous:
        return None
    distance = record.odometer_km - previous.odometer_km
    if distance <= 0:
        return None
    return record.liters / distance * 100
