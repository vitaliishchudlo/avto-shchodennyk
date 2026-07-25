"""
Імпорт заправок з Excel у fuel_tracker.db.

Запуск:
    python test.py          # виконати INSERT-и
    python test.py --dry    # лише показати SQL, без запису в БД

Перед запуском перевір USER_ID та CAR_ID (див. вивід cars/user_settings у БД).
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "fuel_tracker.db"

# Значення з поточної БД; зміни, якщо імпортуєш для іншого користувача/авто.
USER_ID = 498570021
CAR_ID = 1

# TYPE, KILOMETERS, LITERS, PRICE PER L, SUM PRICE, FUEL TYPE, DATE, LOCATION
RAW_ROWS: list[tuple] = [
    ("FUEL", 119640, 37.74, 60.99, 2300, "95 PULLS", "05.06.25", "Трускавець"),
    ("FUEL", 120150, 57, 58.99, 3360, "95 PULLS", "08.06.25", "Тернопіль"),
    ("FUEL", 120530, 30, 62.99, 1890, "95 PULLS", "16.06.25", "ІФ"),
    ("FUEL", 120638, 52.06, 64.99, "3383.38(-441.42)=2942", "95 PULLS", "25.06.25", "ІФ"),
    ("FUEL", 121058, 52.76, 64.99, 3429, "95 PULLS", "29.06.25", "-"),
    ("FUEL", 121368, 52.86, 64.99, 3435.37, "95 PULLS", "12.07.25", "Надвірна"),
    ("FUEL", 121741, 51.47, 61.99, 3190.63, "95 EURO", "24.07.25", "ІФ"),
    ("FUEL", 121905, 29.53, 61.99, "777(-1053.56)", "95 EURO", "01.08.25", ""),
    ("FUEL", 122277, 48.87, 56.99, 2785.1, "95 EURO", "10.08.25", ""),
    ("FUEL", 122667, 51.68, 61.99, 3199.92, "95 EURO", "17.08.25", ""),
    ("FUEL", 122900, 31.81, 61.99, 1971.9, "95 EURO", "26.08.25", ""),
    ("FUEL", 123460, 52.05, 61.99, 3226.58, "95 EURO", "06.09.25", ""),
    ("FUEL", 123819, 46.56, 64.99, 3025.93, "95 PULLS", "17.09.25", ""),
    ("FUEL", 124097, 48.4, 61.99, "1778 (-1222.32)", "95 EURO", "01.10.25", ""),
    ("FUEL", 124404, 53.31, 61.99, 3304.69, "95 EURO", "16.10.25", ""),
    ("FUEL", 124670, 51, 61.99, 3161.49, "95 EURO", "02.11.25", ""),
    ("FUEL", 124921, 43, 61.99, 2665.57, "95 EURO", "16.11.25", ""),
    ("FUEL", 125357, 52.31, 64.99, 3399.63, "95 PULLS", "27.11.25", ""),
    ("FUEL", 125672, 47.58, 61.99, "1899.48(-1050)", "95 EURO", "06.12.25", ""),
    ("FUEL", 126029, 54.04, 61.99, 3349.94, "95 EURO", "18.12.25", ""),
    ("FUEL", 126456, 48.94, 61.99, 3033.79, "95 EURO", "26.12.25", ""),
    ("FUEL", 126897, 50.58, 61.99, "2333(-802)", "95 EURO", "06.01.26", ""),
    ("FUEL", 127035, 51.86, 61.99, 3214, "95 EURO", "16.01.26", ""),
    ("FUEL", 127408, 46.34, 63.99, 2965, "95 EURO", "04.02.26", ""),
    ("FUEL", 127696, 35.77, 63.99, 2288.92, "95 EURO", "11.02.26", ""),
    ("FUEL", 128079, 49.7, 64.99, 3230, "95 EURO", "21.02.26", ""),
    ("FUEL", 128377, 38.66, 66.99, "1393(-1196)", "95 EURO", "01.03.26", ""),
    ("FUEL", 128578, 36, 70.99, 2557, "95 EURO", "08.03.26", ""),
    ("FUEL", 128962, 47.76, 74.99, 3581, "95 EURO", "22.03.26", ""),
    ("FUEL", 129280, 38.34, 74.99, 2875, "95 EURO", "29.03.26", ""),
    ("FUEL", 129781, 50, 76.99, 3845, "95 EURO", "06.04.26", ""),
    ("FUEL", 130000, 44.96, 76.99, 3457, "95 EURO", "15.04.26", ""),
    ("FUEL", 130400, 50.87, 75.99, "2676(-1185)", "95 EURO", "26.04.26", ""),
    ("FUEL", 130786, 53.28, 77.9, 4150, "95 EURO", "08.05.26", ""),
    ("FUEL", 131125, "46,7", 78.9, 3684, "95 EURO", "18.05.26", ""),
    ("FUEL", 131451, 48.08, 74.9, 3601, "95 ukrnafta", "28.05.26", ""),
    ("FUEL", 131764, 53, 78.9, 4181.7, "95 EURO", "14.06.26", ""),
    ("FUEL", 132185, 56.19, 78.9, "3555(-878)", "95 EURO", "22.06.26", ""),
    ("FUEL", 132545, 49.29, 78.9, 3889, "95 EURO", "29.06.26", ""),
]


def parse_liters(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", ".").strip())


def parse_total_price(value: str | int | float) -> float:
    """Повна сума без знижки: 3555(-878) -> 4433."""
    text = str(value).strip().replace(" ", "")
    match = re.match(r"^([\d.]+)\(-([\d.]+)\)", text)
    if match:
        paid = float(match.group(1))
        discount = float(match.group(2))
        return round(paid + discount, 2)
    match = re.match(r"^([\d.]+)\(-([\d.]+)\)=", text)
    if match:
        paid = float(match.group(1))
        discount = float(match.group(2))
        return round(paid + discount, 2)
    return round(parse_liters(value), 2)


def parse_date(value: str) -> str:
    day, month, year = value.strip().split(".")
    full_year = 2000 + int(year)
    return f"{full_year}-{int(month):02d}-{int(day):02d}"


def map_fuel_name(excel_fuel: str) -> str:
    """Excel FUEL TYPE -> single fuel_type value."""
    key = excel_fuel.strip().upper()
    if "PULLS" in key:
        return "Pulls 95"
    if "UKRNAFTA" in key or "УКРНАФТА" in key:
        return "А-95"
    return excel_fuel.strip() or "А-95"


def build_records() -> list[dict]:
    records: list[dict] = []
    for row in RAW_ROWS:
        _type, odometer, liters_raw, _price_per_l, total_raw, fuel_excel, date_raw, _location = row
        liters = parse_liters(liters_raw)
        total_price = parse_total_price(total_raw)
        price_per_liter = round(total_price / liters, 2)
        # LOCATION in Excel is a city — not stored as АЗС
        records.append(
            {
                "date": parse_date(date_raw),
                "odometer_km": float(odometer),
                "liters": liters,
                "price_per_liter": price_per_liter,
                "total_price": total_price,
                "fuel_type": map_fuel_name(fuel_excel),
                "station_name": None,
            }
        )
    return records


def sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def build_insert_sql(records: list[dict]) -> str:
    lines: list[str] = [
        "-- Імпорт заправок з Excel у таблицю refuels",
        f"-- user_id={USER_ID}, car_id={CAR_ID}, full_tank=1 для всіх записів",
        "",
    ]
    for rec in records:
        lines.append(
            "INSERT INTO refuels ("
            "user_id, car_id, date, odometer_km, liters, price_per_liter, "
            "total_price, fuel_type, station_name, full_tank, note"
            ") VALUES ("
            f"{USER_ID}, "
            f"{CAR_ID}, "
            f"{sql_literal(rec['date'])}, "
            f"{rec['odometer_km']}, "
            f"{rec['liters']}, "
            f"{rec['price_per_liter']}, "
            f"{rec['total_price']}, "
            f"{sql_literal(rec['fuel_type'])}, "
            f"{sql_literal(rec['station_name'])}, "
            "1, "
            "NULL"
            ");"
        )
    return "\n".join(lines)


def run_import(dry_run: bool = False) -> None:
    records = build_records()
    sql = build_insert_sql(records)

    print(sql)
    print()
    print(f"Записів: {len(records)}")

    if dry_run:
        print("Dry-run: у БД нічого не записано.")
        return

    with sqlite3.connect(DATABASE_PATH) as db:
        db.executescript(sql)
        count = db.execute("SELECT COUNT(*) FROM refuels WHERE user_id = ?", (USER_ID,)).fetchone()[0]
    print(f"Готово. У refuels для user_id={USER_ID} тепер {count} запис(ів).")


if __name__ == "__main__":
    dry = "--dry" in sys.argv or "-n" in sys.argv
    run_import(dry_run=dry)
