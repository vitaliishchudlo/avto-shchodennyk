"""Module: calculations
Description: Parsing, formatting, and fuel consumption statistics for fuel entries.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from database import RefuelRecord
from services.fuel_products import match_fuel_product, normalize_station_name

DAYS_PER_MONTH = 30.44
MIN_DAYS_FOR_MONTHLY = 30


@dataclass
class TripStats:
    """Metrics for a full-tank-to-full-tank segment ending at one fuel entry."""

    distance_km: float
    consumption_l_per_100km: float
    cost_per_100km: float
    cost_per_km: float
    # Fill-ups in the segment (1 = straight from the previous full tank)
    refuels_count: int = 1
    # Date of the full tank the segment starts from
    since: datetime | None = None


@dataclass
class OverallStats:
    """Aggregated statistics over a list of fuel entries."""

    total_refuels: int
    total_liters: float
    total_spent: float
    total_distance_km: float
    avg_consumption: float | None
    avg_cost_per_100km: float | None
    avg_cost_per_km: float | None
    most_expensive: RefuelRecord | None
    largest_liters: RefuelRecord | None
    last_refuel: RefuelRecord | None
    period_start: datetime | None
    period_end: datetime | None
    most_common_station: str | None = None
    most_common_station_count: int = 0
    most_common_fuel_type: str | None = None
    # Sum of discounts; total_spent stays the full pre-discount amount
    total_discount: float = 0.0
    # Rhythm metrics; None when there are fewer than two refuels or too short a period
    avg_days_between: float | None = None
    avg_km_between: float | None = None
    km_per_month: float | None = None
    spent_per_month: float | None = None
    # True when averages come from full-tank segments, False for the rough per-refuel method
    consumption_from_full_tanks: bool = False


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


def odometer_order_error(
    odometer: float,
    before: RefuelRecord | None,
    after: RefuelRecord | None,
) -> str | None:
    """Check that an odometer fits between the neighbouring refuels by date.

    Args:
        odometer: New odometer reading.
        before: Latest refuel on or before the new refuel's date.
        after: Earliest refuel after the new refuel's date (back-dated entries).

    Returns:
        A user-facing error, or None when the reading is consistent.
    """
    if before and odometer <= before.odometer_km:
        return (
            f"Пробіг {format_number(odometer, 0)} км має бути більшим, ніж у заправці "
            f"{format_date(before.date)} ({format_number(before.odometer_km, 0)} км)."
        )
    if after and odometer >= after.odometer_km:
        return (
            f"Пробіг {format_number(odometer, 0)} км має бути меншим, ніж у пізнішій заправці "
            f"{format_date(after.date)} ({format_number(after.odometer_km, 0)} км)."
        )
    return None


def _most_common(values: list[str]) -> str | None:
    """Return the most frequent non-empty string, or None if the list is empty."""
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _station_and_fuel_names(refuels: list[RefuelRecord]) -> tuple[list[str], list[str]]:
    """Unified station / fuel names, so "OKKO" and "ОККО" (or "95 EURO" and "А-95 Євро") count once."""
    stations: list[str] = []
    fuels: list[str] = []
    for r in refuels:
        station = normalize_station_name(r.station_name) if r.station_name else None
        if station:
            stations.append(station)
        fuels.append(match_fuel_product(station, r.fuel_type) or r.fuel_type)
    return stations, fuels


def format_date(dt: datetime | date) -> str:
    """Format a date as DD.MM.YYYY."""
    return dt.strftime("%d.%m.%Y")


def format_datetime(dt: datetime) -> str:
    """Format a datetime as DD.MM.YYYY HH:MM."""
    return dt.strftime("%d.%m.%Y %H:%M")


def _trip(distance: float, liters: float, cost: float, count: int, since: datetime) -> TripStats:
    return TripStats(
        distance_km=distance,
        consumption_l_per_100km=liters / distance * 100,
        cost_per_100km=cost / distance * 100,
        cost_per_km=cost / distance,
        refuels_count=count,
        since=since,
    )


def calc_full_tank_trips(refuels: list[RefuelRecord]) -> dict[int, TripStats]:
    """Consumption per full tank, using the full-to-full method.

    Only a full tank tells how much was burned: everything poured in since the previous
    full tank (partial fill-ups included) was used over the kilometres between the two.
    Partial fill-ups get no entry of their own; their liters count towards the next full tank.

    Args:
        refuels: Fuel entries sorted chronologically (oldest first).

    Returns:
        Mapping of refuel id -> TripStats, only for full tanks that close a segment.
    """
    trips: dict[int, TripStats] = {}
    last_full: RefuelRecord | None = None
    liters = cost = 0.0
    count = 0
    for record in refuels:
        if last_full is not None:
            liters += record.liters
            cost += record.total_price
            count += 1
        if not record.full_tank:
            continue
        if last_full is not None:
            distance = record.odometer_km - last_full.odometer_km
            if distance > 0:
                trips[record.id] = _trip(distance, liters, cost, count, last_full.date)
        last_full = record
        liters = cost = 0.0
        count = 0
    return trips


def _overall_consumption(
    refuels: list[RefuelRecord],
) -> tuple[float, float, float, bool] | None:
    """Return (liters, cost, distance, from_full_tanks) for the period's average consumption.

    Prefers full-tank segments; with none available falls back to the per-refuel sum,
    which is rough per refuel but evens out over a long period.
    """
    trips = calc_full_tank_trips(refuels)
    if trips:
        distance = sum(t.distance_km for t in trips.values())
        liters = sum(t.consumption_l_per_100km * t.distance_km / 100 for t in trips.values())
        cost = sum(t.cost_per_km * t.distance_km for t in trips.values())
        return liters, cost, distance, True

    liters = cost = distance = 0.0
    for i in range(1, len(refuels)):
        dist = refuels[i].odometer_km - refuels[i - 1].odometer_km
        if dist > 0:
            liters += refuels[i].liters
            cost += refuels[i].total_price
            distance += dist
    return (liters, cost, distance, False) if distance > 0 else None


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

    consumption = _overall_consumption(refuels)
    if consumption:
        seg_liters, seg_cost, seg_distance, from_full_tanks = consumption
        avg_consumption = seg_liters / seg_distance * 100
        avg_cost_per_100 = seg_cost / seg_distance * 100
        avg_cost_per_km = seg_cost / seg_distance
    else:
        avg_consumption = avg_cost_per_100 = avg_cost_per_km = None
        from_full_tanks = False

    # Refuel rhythm over the whole period; monthly figures only once a month has passed
    period_days = (refuels[-1].date - refuels[0].date).days
    gaps = len(refuels) - 1
    avg_days_between = period_days / gaps if gaps > 0 and period_days > 0 else None
    avg_km_between = total_distance / gaps if gaps > 0 and total_distance > 0 else None
    months = period_days / DAYS_PER_MONTH
    km_per_month = total_distance / months if period_days >= MIN_DAYS_FOR_MONTHLY else None
    # The last refuel's fuel is still in the tank, so it is not spent within the period
    spent_in_period = total_spent - refuels[0].total_price
    spent_per_month = spent_in_period / months if period_days >= MIN_DAYS_FOR_MONTHLY else None

    stations, fuel_types = _station_and_fuel_names(refuels)
    station_counts = Counter(stations).most_common(1)

    return OverallStats(
        total_refuels=len(refuels),
        total_liters=total_liters,
        total_spent=total_spent,
        total_distance_km=max(total_distance, 0),
        avg_consumption=avg_consumption,
        avg_cost_per_100km=avg_cost_per_100,
        avg_cost_per_km=avg_cost_per_km,
        most_expensive=most_expensive,
        largest_liters=largest_liters,
        last_refuel=last_refuel,
        period_start=refuels[0].date,
        period_end=refuels[-1].date,
        most_common_station=station_counts[0][0] if station_counts else None,
        most_common_station_count=station_counts[0][1] if station_counts else 0,
        most_common_fuel_type=_most_common(fuel_types),
        total_discount=sum(r.discount for r in refuels),
        avg_days_between=avg_days_between,
        avg_km_between=avg_km_between,
        km_per_month=km_per_month,
        spent_per_month=spent_per_month,
        consumption_from_full_tanks=from_full_tanks,
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
