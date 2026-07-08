"""SQLite persistence layer for users, cars, and refuel records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import aiosqlite

from config import DATABASE_PATH


@dataclass
class UserSettings:
    user_id: int
    currency: str = "грн"
    units: str = "км / л"
    car_name: str = "Моє авто"
    extended_history: bool = True


@dataclass
class Car:
    id: int
    user_id: int
    name: str
    created_at: datetime
    is_active: bool


@dataclass
class RefuelRecord:
    id: int
    user_id: int
    date: datetime
    odometer_km: float
    liters: float
    price_per_liter: float
    total_price: float
    fuel_type: str
    station_name: str | None
    full_tank: bool
    note: str | None
    fuel_product_name: str | None = None
    car_id: int | None = None


def _parse_stored_date(value: str) -> datetime:
    """Parse a date stored in the DB (YYYY-MM-DD or ISO datetime)."""
    if "T" in value:
        return datetime.fromisoformat(value)
    return datetime.strptime(value, "%Y-%m-%d")


def _row_to_car(row: aiosqlite.Row) -> Car:
    created = row["created_at"]
    if isinstance(created, str) and "T" not in created:
        created_at = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
    else:
        created_at = datetime.fromisoformat(str(created))
    return Car(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        created_at=created_at,
        is_active=bool(row["is_active"]),
    )


def _row_to_refuel(row: aiosqlite.Row) -> RefuelRecord:
    keys = row.keys()
    return RefuelRecord(
        id=row["id"],
        user_id=row["user_id"],
        date=_parse_stored_date(row["date"]),
        odometer_km=row["odometer_km"],
        liters=row["liters"],
        price_per_liter=row["price_per_liter"],
        total_price=row["total_price"],
        fuel_type=row["fuel_type"],
        station_name=row["station_name"],
        full_tank=bool(row["full_tank"]),
        note=row["note"],
        fuel_product_name=row["fuel_product_name"] if "fuel_product_name" in keys else None,
        car_id=row["car_id"] if "car_id" in keys else None,
    )


async def _migrate_refuels_table(db: aiosqlite.Connection) -> None:
    """Add optional refuel columns introduced after the initial schema."""
    cursor = await db.execute("PRAGMA table_info(refuels)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "fuel_product_name" not in columns:
        await db.execute("ALTER TABLE refuels ADD COLUMN fuel_product_name TEXT")
    if "car_id" not in columns:
        await db.execute("ALTER TABLE refuels ADD COLUMN car_id INTEGER")


async def _migrate_cars_table(db: aiosqlite.Connection) -> None:
    """Create the cars table and related indexes if they do not exist."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            is_active INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cars_user ON cars(user_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_refuels_car ON refuels(car_id)"
    )


async def _migrate_legacy_cars(db: aiosqlite.Connection) -> None:
    """Backfill cars from user_settings.car_name and attach orphan refuels."""
    cursor = await db.execute("SELECT user_id, car_name FROM user_settings")
    users = await cursor.fetchall()

    for row in users:
        user_id = row["user_id"]
        car_name = row["car_name"]

        car_cursor = await db.execute(
            "SELECT id FROM cars WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        existing = await car_cursor.fetchone()

        if existing:
            car_id = existing["id"]
        else:
            await db.execute(
                """
                INSERT INTO cars (user_id, name, is_active)
                VALUES (?, ?, 1)
                """,
                (user_id, car_name),
            )
            car_id_cursor = await db.execute("SELECT last_insert_rowid()")
            car_id = (await car_id_cursor.fetchone())[0]

        await db.execute(
            "UPDATE refuels SET car_id = ? WHERE user_id = ? AND car_id IS NULL",
            (car_id, user_id),
        )

    orphan_cursor = await db.execute(
        "SELECT DISTINCT user_id FROM refuels WHERE car_id IS NULL"
    )
    for row in await orphan_cursor.fetchall():
        user_id = row["user_id"]
        await db.execute(
            """
            INSERT INTO cars (user_id, name, is_active)
            VALUES (?, 'Моє авто', 1)
            """,
            (user_id,),
        )
        car_id_cursor = await db.execute("SELECT last_insert_rowid()")
        car_id = (await car_id_cursor.fetchone())[0]
        await db.execute(
            "UPDATE refuels SET car_id = ? WHERE user_id = ? AND car_id IS NULL",
            (car_id, user_id),
        )


async def _migrate_user_settings_table(db: aiosqlite.Connection) -> None:
    """Add extended_history and bump PRAGMA user_version when needed."""
    cursor = await db.execute("PRAGMA table_info(user_settings)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "extended_history" not in columns:
        await db.execute(
            "ALTER TABLE user_settings ADD COLUMN extended_history INTEGER NOT NULL DEFAULT 1"
        )

    version_row = await db.execute("PRAGMA user_version")
    version = (await version_row.fetchone())[0]
    if version < 1:
        await db.execute("UPDATE user_settings SET extended_history = 1")
        await db.execute("PRAGMA user_version = 1")


async def init_db() -> None:
    """Create tables, run migrations, and ensure indexes exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                currency TEXT NOT NULL DEFAULT 'грн',
                units TEXT NOT NULL DEFAULT 'км / л',
                car_name TEXT NOT NULL DEFAULT 'Моє авто'
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS refuels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                odometer_km REAL NOT NULL,
                liters REAL NOT NULL,
                price_per_liter REAL NOT NULL,
                total_price REAL NOT NULL,
                fuel_type TEXT NOT NULL,
                station_name TEXT,
                full_tank INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                fuel_product_name TEXT
            )
            """
        )
        await _migrate_refuels_table(db)
        await _migrate_cars_table(db)
        await _migrate_user_settings_table(db)
        await _migrate_legacy_cars(db)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_refuels_user_date ON refuels(user_id, date)"
        )
        await db.commit()


async def ensure_user(user_id: int) -> UserSettings:
    """Ensure default settings and at least one car exist for the user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO user_settings (user_id)
            VALUES (?)
            """,
            (user_id,),
        )
        await db.commit()

    await _ensure_default_car(user_id)
    return await _get_user_settings(user_id)


async def _ensure_default_car(user_id: int) -> None:
    cars = await get_user_cars(user_id)
    if cars:
        return
    settings = await _get_user_settings(user_id)
    await add_car(user_id, settings.car_name, set_active=True)


async def _get_user_settings(user_id: int) -> UserSettings:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        keys = row.keys()
        return UserSettings(
            user_id=row["user_id"],
            currency=row["currency"],
            units=row["units"],
            car_name=row["car_name"],
            extended_history=bool(row["extended_history"]) if "extended_history" in keys else True,
        )


async def _sync_settings_car_name(user_id: int, car_name: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE user_settings SET car_name = ? WHERE user_id = ?",
            (car_name, user_id),
        )
        await db.commit()


async def get_user_cars(user_id: int) -> list[Car]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM cars
            WHERE user_id = ?
            ORDER BY is_active DESC, id ASC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_car(row) for row in rows]


async def get_car_by_id(car_id: int, user_id: int) -> Car | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM cars WHERE id = ? AND user_id = ?",
            (car_id, user_id),
        )
        row = await cursor.fetchone()
        return _row_to_car(row) if row else None


async def get_active_car(user_id: int) -> Car:
    """Return the user's active car, creating or selecting one if needed."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()

    cars = await get_user_cars(user_id)
    if not cars:
        await _ensure_default_car(user_id)
        cars = await get_user_cars(user_id)

    active = next((car for car in cars if car.is_active), None)
    if active:
        return active

    await set_active_car(user_id, cars[0].id)
    return await get_car_by_id(cars[0].id, user_id)  # type: ignore[return-value]


async def add_car(user_id: int, name: str, *, set_active: bool = False) -> Car:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if set_active:
            await db.execute(
                "UPDATE cars SET is_active = 0 WHERE user_id = ?",
                (user_id,),
            )
        is_active = 1 if set_active else 0
        if not set_active:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM cars WHERE user_id = ?",
                (user_id,),
            )
            count = (await cursor.fetchone())[0]
            if count == 0:
                is_active = 1

        cursor = await db.execute(
            """
            INSERT INTO cars (user_id, name, is_active)
            VALUES (?, ?, ?)
            """,
            (user_id, name, is_active),
        )
        car_id = cursor.lastrowid
        await db.commit()

    if is_active:
        await _sync_settings_car_name(user_id, name)

    return await get_car_by_id(car_id, user_id)  # type: ignore[return-value]


async def set_active_car(user_id: int, car_id: int) -> Car:
    car = await get_car_by_id(car_id, user_id)
    if not car:
        raise ValueError("car not found")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE cars SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.execute(
            "UPDATE cars SET is_active = 1 WHERE id = ? AND user_id = ?",
            (car_id, user_id),
        )
        await db.commit()

    await _sync_settings_car_name(user_id, car.name)
    return await get_car_by_id(car_id, user_id)  # type: ignore[return-value]


async def rename_car(user_id: int, car_id: int, name: str) -> Car:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE cars SET name = ? WHERE id = ? AND user_id = ?",
            (name, car_id, user_id),
        )
        await db.commit()

    car = await get_car_by_id(car_id, user_id)
    if car and car.is_active:
        await _sync_settings_car_name(user_id, name)
    return car  # type: ignore[return-value]


async def count_refuels_for_car(car_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM refuels WHERE car_id = ?",
            (car_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def delete_car(user_id: int, car_id: int) -> bool:
    """Delete a car and its refuels; refuse when it is the user's only car."""
    cars = await get_user_cars(user_id)
    if len(cars) <= 1:
        return False

    car = await get_car_by_id(car_id, user_id)
    if not car:
        return False

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM refuels WHERE car_id = ?", (car_id,))
        await db.execute(
            "DELETE FROM cars WHERE id = ? AND user_id = ?",
            (car_id, user_id),
        )
        await db.commit()

    if car.is_active:
        remaining = await get_user_cars(user_id)
        if remaining:
            await set_active_car(user_id, remaining[0].id)

    return True


async def update_user_settings(
    user_id: int,
    *,
    currency: str | None = None,
    units: str | None = None,
    car_name: str | None = None,
    extended_history: bool | None = None,
) -> UserSettings:
    await ensure_user(user_id)
    updates: list[str] = []
    params: list[Any] = []

    if currency is not None:
        updates.append("currency = ?")
        params.append(currency)
    if units is not None:
        updates.append("units = ?")
        params.append(units)
    if car_name is not None:
        updates.append("car_name = ?")
        params.append(car_name)
    if extended_history is not None:
        updates.append("extended_history = ?")
        params.append(int(extended_history))

    if updates:
        params.append(user_id)
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                f"UPDATE user_settings SET {', '.join(updates)} WHERE user_id = ?",
                params,
            )
            await db.commit()

        if car_name is not None:
            active = await get_active_car(user_id)
            await rename_car(user_id, active.id, car_name)

    return await _get_user_settings(user_id)


async def add_refuel(
    user_id: int,
    *,
    car_id: int,
    refuel_date: date,
    odometer_km: float,
    liters: float,
    price_per_liter: float,
    total_price: float,
    fuel_type: str,
    station_name: str | None,
    full_tank: bool,
    fuel_product_name: str | None = None,
    note: str | None = None,
) -> int:
    """Insert a refuel record and return its row id."""
    date_str = refuel_date.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO refuels (
                user_id, car_id, date, odometer_km, liters, price_per_liter,
                total_price, fuel_type, station_name, full_tank, note,
                fuel_product_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                car_id,
                date_str,
                odometer_km,
                liters,
                price_per_liter,
                total_price,
                fuel_type,
                station_name,
                int(full_tank),
                note,
                fuel_product_name,
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_last_refuel(
    user_id: int,
    car_id: int,
    exclude_id: int | None = None,
) -> RefuelRecord | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if exclude_id:
            cursor = await db.execute(
                """
                SELECT * FROM refuels
                WHERE user_id = ? AND car_id = ? AND id != ?
                ORDER BY date DESC, id DESC
                LIMIT 1
                """,
                (user_id, car_id, exclude_id),
            )
        else:
            cursor = await db.execute(
                """
                SELECT * FROM refuels
                WHERE user_id = ? AND car_id = ?
                ORDER BY date DESC, id DESC
                LIMIT 1
                """,
                (user_id, car_id),
            )
        row = await cursor.fetchone()
        return _row_to_refuel(row) if row else None


async def get_previous_refuel(
    user_id: int,
    car_id: int,
    before_odometer: float,
) -> RefuelRecord | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM refuels
            WHERE user_id = ? AND car_id = ? AND odometer_km < ?
            ORDER BY odometer_km DESC, date DESC
            LIMIT 1
            """,
            (user_id, car_id, before_odometer),
        )
        row = await cursor.fetchone()
        return _row_to_refuel(row) if row else None


async def get_refuels_page(
    user_id: int,
    car_id: int,
    page: int,
    per_page: int = 10,
) -> list[RefuelRecord]:
    offset = page * per_page
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM refuels
            WHERE user_id = ? AND car_id = ?
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, car_id, per_page, offset),
        )
        rows = await cursor.fetchall()
        return [_row_to_refuel(row) for row in rows]


async def count_refuels(user_id: int, car_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM refuels WHERE user_id = ? AND car_id = ?",
            (user_id, car_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_all_refuels(user_id: int, car_id: int) -> list[RefuelRecord]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM refuels
            WHERE user_id = ? AND car_id = ?
            ORDER BY date ASC, id ASC
            """,
            (user_id, car_id),
        )
        rows = await cursor.fetchall()
        return [_row_to_refuel(row) for row in rows]


async def delete_last_refuel(user_id: int, car_id: int) -> RefuelRecord | None:
    last = await get_last_refuel(user_id, car_id)
    if not last:
        return None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM refuels WHERE id = ?", (last.id,))
        await db.commit()
    return last
