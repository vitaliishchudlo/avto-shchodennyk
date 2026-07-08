"""Module: formatting
Description: Telegram HTML message formatting helpers for bot output.
"""

from __future__ import annotations

from datetime import date, datetime

from services.calculations import format_date, format_number


def html_escape(text: str) -> str:
    """Escape characters that are special in Telegram HTML parse mode.

    Args:
        text: Raw user or display text.

    Returns:
        HTML-safe string.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def code(value: str | int | float) -> str:
    """Wrap a value in a Telegram <code> tag for tap-to-copy.

    Args:
        value: Scalar value to display.

    Returns:
        HTML fragment with escaped content.
    """
    return f"<code>{html_escape(str(value))}</code>"


def fmt_num(value: float, decimals: int = 1) -> str:
    """Format a number for Telegram HTML with tap-to-copy styling.

    Args:
        value: Number to format.
        decimals: Decimal places to show.

    Returns:
        HTML fragment containing the formatted number.
    """
    return code(format_number(value, decimals))


def fmt_date(dt: date | datetime) -> str:
    """Format a date for Telegram HTML with tap-to-copy styling.

    Args:
        dt: Date or datetime to format.

    Returns:
        HTML fragment containing DD.MM.YYYY.
    """
    return code(format_date(dt))


def active_car_banner(car_name: str) -> str:
    """Build the active-car banner line shown at the top of car-scoped screens.

    Args:
        car_name: Display name of the selected car.

    Returns:
        HTML banner string (Ukrainian user-facing label preserved).
    """
    return f"🚗 Активне авто: <b>{html_escape(car_name)}</b>\n"
