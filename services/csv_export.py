"""Module: csv_export
Description: Export fuel entries to CSV for download.
"""

import csv
import io
from datetime import date, datetime

from database import RefuelRecord

CSV_HEADERS = [
    "date",
    "car_name",
    "odometer_km",
    "station_name",
    "fuel_type",
    "fuel_product_name",
    "liters",
    "price_per_liter",
    "total_price",
    "full_tank",
    "note",
]


def _csv_cell(value: object) -> str | int | float | bool:
    """Normalize a single cell value for CSV output.

    Args:
        value: Raw field value from a fuel entry.

    Returns:
        CSV-safe scalar; None becomes an empty string, dates use ISO format.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value  # type: ignore[return-value]


def export_refuels_to_csv(refuels: list[RefuelRecord], *, car_name: str) -> bytes:
    """Serialize fuel entries to a UTF-8 CSV with BOM for Excel compatibility.

    Args:
        refuels: Fuel entries to export.
        car_name: Car name written on every row.

    Returns:
        CSV file contents as bytes (utf-8-sig).
    """
    buffer = io.BytesIO()
    text = io.TextIOWrapper(buffer, encoding="utf-8-sig", newline="")
    writer = csv.writer(
        text,
        delimiter=",",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )

    writer.writerow(CSV_HEADERS)

    for record in refuels:
        writer.writerow([
            _csv_cell(record.date),
            car_name,
            _csv_cell(record.odometer_km),
            _csv_cell(record.station_name),
            _csv_cell(record.fuel_type),
            _csv_cell(record.fuel_product_name),
            _csv_cell(record.liters),
            _csv_cell(record.price_per_liter),
            _csv_cell(record.total_price),
            _csv_cell(record.full_tank),
            _csv_cell(record.note),
        ])

    text.flush()
    return buffer.getvalue()


def csv_filename(car_name: str) -> str:
    """Build a safe download filename for a car's fuel export.

    Args:
        car_name: Car display name; non-alphanumeric characters are replaced.

    Returns:
        Filename like fuel_export_{car}_{YYYYMMDD}.csv.
    """
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in car_name)
    date_str = datetime.now().strftime("%Y%m%d")
    return f"fuel_export_{safe_name}_{date_str}.csv"
