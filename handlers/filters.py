"""Shared message filters for FSM-driven routers."""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message


class NotForeignCommand(Filter):
    """Let a router skip slash commands it does not own.

    Wizard steps accept free text; without this filter a command like /history typed
    mid-wizard would be read as an odometer value or a car name instead of reaching
    its own handler in a later router.
    """

    def __init__(self, *own_commands: str) -> None:
        self.own = {f"/{name.lower()}" for name in own_commands}

    async def __call__(self, message: Message) -> bool:
        text = message.text or ""
        if not text.startswith("/"):
            return True
        command = text.split()[0].split("@")[0].lower()
        return command in self.own
