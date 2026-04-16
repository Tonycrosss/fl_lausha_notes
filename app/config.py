from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_telegram_id: int
    timezone: str
    database_path: Path

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_telegram_id = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    timezone = os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"

    if not bot_token:
        raise ValueError("BOT_TOKEN is not set")
    if not admin_telegram_id:
        raise ValueError("ADMIN_TELEGRAM_ID is not set")

    return Settings(
        bot_token=bot_token,
        admin_telegram_id=int(admin_telegram_id),
        timezone=timezone,
        database_path=BASE_DIR / "app.db",
    )
