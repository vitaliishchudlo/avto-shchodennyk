"""Load environment variables and shared application paths."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не знайдено. Створіть файл .env з BOT_TOKEN=...")

DATABASE_PATH = BASE_DIR / "fuel_tracker.db"
