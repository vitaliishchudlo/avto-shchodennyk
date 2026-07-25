"""Module: history_format
Description: Format fuel entry history pages and per-segment trip analysis blocks.
"""

from __future__ import annotations

from dataclasses import dataclass

from database import RefuelRecord
from services.calculations import TripStats, calc_full_trip_stats
from services.formatting import fmt_date, fmt_num, html_escape


FIRST_REFUEL_NOTE = "ℹ️ Це перша заправка — немає попередніх даних"

EMPTY_HISTORY_TEXT = (
    "📜 <b>Історія</b>\n\n"
    "Немає заправок для відображення."
)

HISTORY_PER_PAGE = 5

ENTRY_DIVIDER = "━━━━━━━━━━━━━━"


@dataclass(frozen=True)
class HistoryPageResult:
    """Rendered history page with pagination metadata."""

    text: str
    has_prev: bool
    has_next: bool
    page: int
    total_pages: int


def build_prev_map(all_refuels: list[RefuelRecord]) -> dict[int, RefuelRecord | None]:
    """Map each fuel entry id to the previous entry in chronological order.

    Ordering follows date ASC, then id ASC.

    Args:
        all_refuels: Full chronologically sorted fuel entry list.

    Returns:
        Dict mapping record id to the preceding entry, or None for the first entry.
    """
    return {
        record.id: all_refuels[index - 1] if index > 0 else None
        for index, record in enumerate(all_refuels)
    }


def _fuel_line(record: RefuelRecord) -> str:
    """Format fuel name as an HTML line."""
    return f"<b>{html_escape(record.fuel_type)}</b>"


def format_trip_analysis_lines(
    record: RefuelRecord,
    previous: RefuelRecord | None,
    currency: str,
    *,
    header: str = "З попередньої заправки:",
    show_first_note: bool = True,
) -> list[str]:
    """Build the shared trip-analysis block between two fuel entries.

    Used by last-refuel and history views.

    Args:
        record: Current fuel entry.
        previous: Preceding fuel entry, if any.
        currency: Currency code for cost lines.
        header: Section heading (Ukrainian user-facing string).
        show_first_note: When True, show a note if there is no previous entry.

    Returns:
        List of HTML lines; may be empty when trip stats are not computable.
    """
    if previous is None:
        if show_first_note:
            return ["", FIRST_REFUEL_NOTE]
        return []

    trip = calc_full_trip_stats(record, previous)
    if trip is None:
        return []

    return _trip_stats_to_lines(trip, currency, header=header)


def _trip_stats_to_lines(trip: TripStats, currency: str, *, header: str) -> list[str]:
    """Render TripStats as labeled HTML lines."""
    return [
        "",
        f"<b>{header}</b>",
        f"📏 Проїхав: {fmt_num(trip.distance_km, 0)} км",
        f"🔥 Витрата: {fmt_num(trip.consumption_l_per_100km)} л / 100 км",
        f"💸 Вартість 100 км: {fmt_num(trip.cost_per_100km, 0)} {currency}",
        f"💵 Вартість 1 км: {fmt_num(trip.cost_per_km, 2)} {currency}/км",
    ]


def format_trip_from_previous_lines(
    record: RefuelRecord,
    previous: RefuelRecord | None,
    currency: str,
    *,
    style: str = "full",
) -> list[str]:
    """Backward-compatible wrapper around format_trip_analysis_lines.

    Args:
        record: Current fuel entry.
        previous: Preceding fuel entry, if any.
        currency: Currency code for cost lines.
        style: ``"compact"`` uses a shorter header; ``"full"`` uses the default.

    Returns:
        Trip analysis lines from format_trip_analysis_lines.
    """
    if style == "compact":
        return format_trip_analysis_lines(
            record,
            previous,
            currency,
            header="З попередньої:",
        )
    return format_trip_analysis_lines(record, previous, currency)


def _basic_record_lines(record: RefuelRecord, currency: str) -> list[str]:
    """Core field lines for a single fuel entry (date, station, fuel, amounts)."""
    lines = [
        f"📅 {fmt_date(record.date)}",
    ]
    if record.station_name:
        lines.append(f"⛽ <b>{html_escape(record.station_name)}</b>")
    lines.extend([
        f"🧾 {_fuel_line(record)}",
        f"🔢 {fmt_num(record.liters)} л",
        f"💵 {fmt_num(record.price_per_liter)} {currency}/л",
        f"💰 {fmt_num(record.total_price, 0)} {currency}",
    ])
    return lines


def format_history_record(
    record: RefuelRecord,
    previous: RefuelRecord | None,
    currency: str,
    *,
    number: int,
    extended_history: bool = False,
) -> str:
    """Format one history list entry (#1 = newest).

    Args:
        record: Fuel entry to display.
        previous: Preceding entry for optional trip analysis.
        currency: Currency code for amounts.
        number: Display index (1-based, newest first).
        extended_history: When True, append trip analysis from the previous entry.

    Returns:
        Multi-line HTML string for the entry.
    """
    lines = [
        ENTRY_DIVIDER,
        f"<b>#{number}</b> ⛽ Заправка",
        "",
        *_basic_record_lines(record, currency),
    ]

    if extended_history:
        lines.extend(
            format_trip_analysis_lines(
                record,
                previous,
                currency,
                header="З попередньої:",
            )
        )

    return "\n".join(lines)


def format_history_page(
    records: list[RefuelRecord],
    prev_map: dict[int, RefuelRecord | None],
    page: int,
    total_pages: int,
    currency: str,
    *,
    per_page: int = HISTORY_PER_PAGE,
    extended_history: bool = False,
) -> HistoryPageResult:
    """Build one paginated history page and navigation flags.

    Args:
        records: Fuel entries on this page.
        prev_map: Previous-entry lookup from build_prev_map.
        page: Zero-based page index.
        total_pages: Total number of pages.
        currency: Currency code for amounts.
        per_page: Entries per page (for display numbering).
        extended_history: When True, include trip analysis on each entry.

    Returns:
        HistoryPageResult with rendered text and pagination state.
    """
    has_prev = page > 0
    has_next = page < total_pages - 1

    lines = [f"📜 <b>Історія заправок</b> ({page + 1}/{total_pages})\n"]

    for index, record in enumerate(records):
        number = page * per_page + index + 1
        previous = prev_map.get(record.id)
        lines.append(
            format_history_record(
                record,
                previous,
                currency,
                number=number,
                extended_history=extended_history,
            )
        )

    text = "\n".join(lines)
    return HistoryPageResult(
        text=text,
        has_prev=has_prev,
        has_next=has_next,
        page=page + 1,
        total_pages=total_pages,
    )


def format_last_refuel(record: RefuelRecord, previous: RefuelRecord | None, currency: str) -> str:
    """Format the detailed last fuel entry card with trip analysis.

    Args:
        record: Most recent fuel entry.
        previous: Preceding entry for consumption and cost since last fill-up.
        currency: Currency code for amounts.

    Returns:
        Multi-line HTML string for the last-refuel view.
    """
    station = record.station_name
    full_tank = "Так ✅" if record.full_tank else "Ні ❌"

    lines = [
        "⛽ <b>Остання заправка</b>\n",
        f"📅 Дата: {fmt_date(record.date)}",
    ]
    if station:
        lines.append(f"⛽ АЗС: <b>{html_escape(station)}</b>")
    lines.extend([
        f"🧾 Пальне: {_fuel_line(record)}",
        f"🔢 Літри: {fmt_num(record.liters)} л",
        f"💰 Сума: {fmt_num(record.total_price, 0)} {currency}",
        f"🚗 Пробіг: {fmt_num(record.odometer_km, 0)} км",
        f"💵 Ціна/л: {fmt_num(record.price_per_liter)} {currency}",
        f"🛢 Повний бак: {full_tank}",
    ])
    lines.extend(format_trip_analysis_lines(record, previous, currency))
    return "\n".join(lines)
