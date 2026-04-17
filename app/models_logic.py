from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.db import Database

logger = logging.getLogger(__name__)

DATETIME_FORMAT = "%Y-%m-%d %H:%M"
STATUS_SCHEDULED = "scheduled"
STATUS_NOTIFIED = "notified"
STATUS_SENT = "sent"
STATUS_CANCELED = "canceled"


@dataclass(slots=True)
class Author:
    id: int
    name: str
    channel_title: str | None
    channel_url: str | None
    is_active: bool
    created_at: str


@dataclass(slots=True)
class Broadcast:
    id: int
    author_id: int
    author_names: list[str]
    title: str
    announce_text: str | None
    announce_photo_file_id: str | None
    notify_at: str
    send_at: str
    status: str
    created_at: str


@dataclass(slots=True)
class BroadcastFile:
    id: int
    broadcast_id: int
    telegram_file_id: str
    file_name: str
    mime_type: str | None


def now_str(tzinfo) -> str:
    return datetime.now(tzinfo).strftime(DATETIME_FORMAT)


def parse_datetime(value: str, tzinfo) -> datetime:
    return datetime.strptime(value, DATETIME_FORMAT).replace(tzinfo=tzinfo)


def row_to_author(row: Any) -> Author:
    return Author(
        id=row["id"],
        name=row["name"],
        channel_title=row["channel_title"],
        channel_url=row["channel_url"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


def normalize_channel_url(url: str) -> str:
    value = url.strip()
    if value.startswith("@"):
        value = f"https://t.me/{value[1:]}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc not in {"t.me", "www.t.me"}:
        raise ValueError("Channel URL must point to t.me")
    path = parsed.path.strip("/")
    if not path or "/" in path or path.startswith("+"):
        raise ValueError("Channel URL must contain a public username")
    return f"https://t.me/{path}"


def extract_channel_username(channel_url: str | None) -> str | None:
    if not channel_url:
        return None
    parsed = urlparse(channel_url.strip())
    if parsed.netloc not in {"t.me", "www.t.me"}:
        return None
    path = parsed.path.strip("/")
    if not path or "/" in path or path.startswith("+"):
        return None
    return f"@{path}"


def row_to_broadcast(row: Any) -> Broadcast:
    raw_names = str(row["author_names"] or "").strip()
    return Broadcast(
        id=row["id"],
        author_id=row["author_id"],
        author_names=[item for item in raw_names.split("||") if item],
        title=row["title"],
        announce_text=row["announce_text"],
        announce_photo_file_id=row["announce_photo_file_id"],
        notify_at=row["notify_at"],
        send_at=row["send_at"],
        status=row["status"],
        created_at=row["created_at"],
    )


def row_to_broadcast_file(row: Any) -> BroadcastFile:
    return BroadcastFile(
        id=row["id"],
        broadcast_id=row["broadcast_id"],
        telegram_file_id=row["telegram_file_id"],
        file_name=row["file_name"],
        mime_type=row["mime_type"],
    )


class Repository:
    def __init__(self, db: Database, tzinfo) -> None:
        self.db = db
        self.tzinfo = tzinfo

    async def upsert_user(self, telegram_id: int, username: str | None, full_name: str) -> int:
        existing = await self.db.fetchone(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        timestamp = now_str(self.tzinfo)
        if existing:
            await self.db.execute(
                """
                UPDATE users
                SET username = ?, full_name = ?
                WHERE telegram_id = ?
                """,
                (username, full_name, telegram_id),
            )
            return int(existing["id"])

        cursor = await self.db.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, is_subscribed, created_at)
            VALUES (?, ?, ?, 0, ?)
            """,
            (telegram_id, username, full_name, timestamp),
        )
        return int(cursor.lastrowid)

    async def get_user_by_telegram_id(self, telegram_id: int):
        return await self.db.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))

    async def confirm_subscription(self, telegram_id: int) -> None:
        user = await self.get_user_by_telegram_id(telegram_id)
        if user is None:
            raise ValueError("User not found")

        await self.db.execute(
            "UPDATE users SET is_subscribed = 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        active_authors = await self.get_active_authors()
        if active_authors:
            params = [(int(user["id"]), author.id) for author in active_authors]
            await self.db.executemany(
                "INSERT OR IGNORE INTO user_authors (user_id, author_id) VALUES (?, ?)",
                params,
            )

    async def sync_active_authors_for_subscribed_users(self, author_id: int) -> None:
        users = await self.db.fetchall("SELECT id FROM users WHERE is_subscribed = 1")
        if not users:
            return
        params = [(int(row["id"]), author_id) for row in users]
        await self.db.executemany(
            "INSERT OR IGNORE INTO user_authors (user_id, author_id) VALUES (?, ?)",
            params,
        )

    async def get_user_author_names(self, telegram_id: int) -> list[str]:
        rows = await self.db.fetchall(
            """
            SELECT a.name
            FROM user_authors ua
            JOIN users u ON u.id = ua.user_id
            JOIN authors a ON a.id = ua.author_id
            WHERE u.telegram_id = ? AND a.is_active = 1
            ORDER BY a.name
            """,
            (telegram_id,),
        )
        return [str(row["name"]) for row in rows]

    async def get_all_authors(self) -> list[Author]:
        rows = await self.db.fetchall("SELECT * FROM authors ORDER BY id")
        return [row_to_author(row) for row in rows]

    async def get_active_authors(self) -> list[Author]:
        rows = await self.db.fetchall("SELECT * FROM authors WHERE is_active = 1 ORDER BY id")
        return [row_to_author(row) for row in rows]

    async def get_required_channel_authors(self) -> list[Author]:
        rows = await self.db.fetchall(
            """
            SELECT *
            FROM authors
            WHERE is_active = 1 AND channel_url IS NOT NULL AND TRIM(channel_url) != ''
            ORDER BY id
            """
        )
        return [row_to_author(row) for row in rows]

    async def get_authors_by_ids(self, author_ids: list[int]) -> list[Author]:
        if not author_ids:
            return []
        placeholders = ",".join("?" for _ in author_ids)
        rows = await self.db.fetchall(
            f"SELECT * FROM authors WHERE id IN ({placeholders}) ORDER BY name",
            tuple(author_ids),
        )
        return [row_to_author(row) for row in rows]

    async def get_author(self, author_id: int) -> Author | None:
        row = await self.db.fetchone("SELECT * FROM authors WHERE id = ?", (author_id,))
        return row_to_author(row) if row else None

    async def create_author(self, name: str, channel_title: str, channel_url: str) -> int:
        cursor = await self.db.execute(
            """
            INSERT INTO authors (name, channel_title, channel_url, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (
                name.strip(),
                channel_title.strip(),
                normalize_channel_url(channel_url),
                now_str(self.tzinfo),
            ),
        )
        author_id = int(cursor.lastrowid)
        await self.sync_active_authors_for_subscribed_users(author_id)
        return author_id

    async def update_author_channel_title(self, author_id: int, channel_title: str) -> None:
        await self.db.execute(
            "UPDATE authors SET channel_title = ? WHERE id = ?",
            (channel_title.strip(), author_id),
        )

    async def update_author_channel_url(self, author_id: int, channel_url: str) -> None:
        await self.db.execute(
            "UPDATE authors SET channel_url = ? WHERE id = ?",
            (normalize_channel_url(channel_url), author_id),
        )

    async def set_author_status(self, author_id: int, is_active: bool) -> None:
        await self.db.execute(
            "UPDATE authors SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, author_id),
        )
        if is_active:
            await self.sync_active_authors_for_subscribed_users(author_id)

    async def create_broadcast(
        self,
        author_ids: list[int],
        title: str,
        announce_text: str | None,
        announce_photo_file_id: str | None,
        notify_at: str,
        send_at: str,
        files: list[dict[str, str | None]],
    ) -> int:
        if not author_ids:
            raise ValueError("Broadcast must include at least one author")

        cursor = await self.db.execute(
            """
            INSERT INTO broadcasts (
                author_id, title, announce_text, announce_photo_file_id, notify_at, send_at, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                author_ids[0],
                title.strip(),
                announce_text.strip() if announce_text else None,
                announce_photo_file_id,
                notify_at,
                send_at,
                STATUS_SCHEDULED,
                now_str(self.tzinfo),
            ),
        )
        broadcast_id = int(cursor.lastrowid)

        await self.db.executemany(
            """
            INSERT INTO broadcast_authors (broadcast_id, author_id)
            VALUES (?, ?)
            """,
            [(broadcast_id, author_id) for author_id in sorted(set(author_ids))],
        )

        await self.db.executemany(
            """
            INSERT INTO broadcast_files (broadcast_id, telegram_file_id, file_name, mime_type)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    broadcast_id,
                    str(file["telegram_file_id"]),
                    str(file["file_name"]),
                    file["mime_type"],
                )
                for file in files
            ],
        )
        return broadcast_id

    async def get_scheduled_broadcasts(self) -> list[Broadcast]:
        rows = await self.db.fetchall(
            """
            SELECT
                b.*,
                COALESCE(GROUP_CONCAT(ba_name.name, '||'), legacy_author.name) AS author_names
            FROM broadcasts b
            LEFT JOIN broadcast_authors ba ON ba.broadcast_id = b.id
            LEFT JOIN authors ba_name ON ba_name.id = ba.author_id
            LEFT JOIN authors legacy_author ON legacy_author.id = b.author_id
            WHERE b.status IN (?, ?)
            GROUP BY b.id
            ORDER BY b.send_at
            """,
            (STATUS_SCHEDULED, STATUS_NOTIFIED),
        )
        return [row_to_broadcast(row) for row in rows]

    async def get_broadcast(self, broadcast_id: int) -> Broadcast | None:
        row = await self.db.fetchone(
            """
            SELECT
                b.*,
                COALESCE(GROUP_CONCAT(ba_name.name, '||'), legacy_author.name) AS author_names
            FROM broadcasts b
            LEFT JOIN broadcast_authors ba ON ba.broadcast_id = b.id
            LEFT JOIN authors ba_name ON ba_name.id = ba.author_id
            LEFT JOIN authors legacy_author ON legacy_author.id = b.author_id
            WHERE b.id = ?
            GROUP BY b.id
            """,
            (broadcast_id,),
        )
        return row_to_broadcast(row) if row else None

    async def get_broadcast_files(self, broadcast_id: int) -> list[BroadcastFile]:
        rows = await self.db.fetchall(
            "SELECT * FROM broadcast_files WHERE broadcast_id = ? ORDER BY id",
            (broadcast_id,),
        )
        return [row_to_broadcast_file(row) for row in rows]

    async def get_broadcast_authors(self, broadcast_id: int) -> list[Author]:
        rows = await self.db.fetchall(
            """
            SELECT a.*
            FROM broadcast_authors ba
            JOIN authors a ON a.id = ba.author_id
            WHERE ba.broadcast_id = ?
            ORDER BY a.name
            """,
            (broadcast_id,),
        )
        if rows:
            return [row_to_author(row) for row in rows]

        legacy_row = await self.db.fetchone(
            "SELECT author_id FROM broadcasts WHERE id = ?",
            (broadcast_id,),
        )
        if legacy_row is None:
            return []
        legacy_author = await self.get_author(int(legacy_row["author_id"]))
        return [legacy_author] if legacy_author else []

    async def cancel_broadcast(self, broadcast_id: int) -> None:
        await self.db.execute(
            "UPDATE broadcasts SET status = ? WHERE id = ?",
            (STATUS_CANCELED, broadcast_id),
        )

    async def update_broadcast_status(self, broadcast_id: int, status: str) -> None:
        await self.db.execute(
            "UPDATE broadcasts SET status = ? WHERE id = ?",
            (status, broadcast_id),
        )

    async def get_broadcast_recipients(self, broadcast_id: int) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            """
            SELECT DISTINCT u.id, u.telegram_id, u.full_name
            FROM users u
            JOIN user_authors ua ON ua.user_id = u.id
            JOIN broadcast_authors ba ON ba.author_id = ua.author_id
            WHERE ba.broadcast_id = ? AND u.is_subscribed = 1
            ORDER BY u.id
            """,
            (broadcast_id,),
        )
        if rows:
            return [dict(row) for row in rows]

        legacy_row = await self.db.fetchone(
            "SELECT author_id FROM broadcasts WHERE id = ?",
            (broadcast_id,),
        )
        if legacy_row is None:
            return []

        legacy_rows = await self.db.fetchall(
            """
            SELECT DISTINCT u.id, u.telegram_id, u.full_name
            FROM users u
            JOIN user_authors ua ON ua.user_id = u.id
            WHERE ua.author_id = ? AND u.is_subscribed = 1
            ORDER BY u.id
            """,
            (int(legacy_row["author_id"]),),
        )
        return [dict(row) for row in legacy_rows]

    async def add_broadcast_log(
        self,
        broadcast_id: int,
        user_id: int,
        status: str,
        error_text: str | None = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO broadcast_logs (broadcast_id, user_id, status, error_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (broadcast_id, user_id, status, error_text, now_str(self.tzinfo)),
        )

    async def get_last_broadcast_stats(self) -> dict[str, int]:
        row = await self.db.fetchone(
            "SELECT id FROM broadcasts WHERE status = ? ORDER BY id DESC LIMIT 1",
            (STATUS_SENT,),
        )
        if row is None:
            return {"success": 0, "errors": 0}

        broadcast_id = int(row["id"])
        success_row = await self.db.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM broadcast_logs
            WHERE broadcast_id = ? AND status = 'success'
            """,
            (broadcast_id,),
        )
        errors_row = await self.db.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM broadcast_logs
            WHERE broadcast_id = ? AND status = 'error'
            """,
            (broadcast_id,),
        )
        return {
            "success": int(success_row["total"]) if success_row else 0,
            "errors": int(errors_row["total"]) if errors_row else 0,
        }

    async def get_statistics(self) -> dict[str, int]:
        users_row = await self.db.fetchone("SELECT COUNT(*) AS total FROM users")
        authors_row = await self.db.fetchone("SELECT COUNT(*) AS total FROM authors WHERE is_active = 1")
        scheduled_row = await self.db.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM broadcasts
            WHERE status IN (?, ?)
            """,
            (STATUS_SCHEDULED, STATUS_NOTIFIED),
        )
        last_stats = await self.get_last_broadcast_stats()
        return {
            "users_total": int(users_row["total"]) if users_row else 0,
            "active_authors_total": int(authors_row["total"]) if authors_row else 0,
            "scheduled_broadcasts_total": int(scheduled_row["total"]) if scheduled_row else 0,
            "last_broadcast_success_total": last_stats["success"],
            "last_broadcast_error_total": last_stats["errors"],
        }
