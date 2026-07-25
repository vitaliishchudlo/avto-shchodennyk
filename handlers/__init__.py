"""Handler router modules registered by the bot application."""

from handlers import (
    add_fuel,
    cars,
    export,
    fallback,
    history,
    import_data,
    settings,
    start,
    stats,
)

__all__ = [
    "add_fuel",
    "cars",
    "export",
    "fallback",
    "history",
    "import_data",
    "settings",
    "start",
    "stats",
]
