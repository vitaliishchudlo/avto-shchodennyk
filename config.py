"""Load environment variables and shared application paths."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не знайдено. Створіть файл .env з BOT_TOKEN=...")

DATABASE_PATH = Path(os.getenv("DATABASE_PATH") or BASE_DIR / "fuel_tracker.db")

# AI import (Google Gemini free tier by default)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
IMPORT_MAX_ROWS = int(os.getenv("IMPORT_MAX_ROWS", "200"))
IMPORT_MAX_FILE_BYTES = int(os.getenv("IMPORT_MAX_FILE_BYTES", str(5 * 1024 * 1024)))
