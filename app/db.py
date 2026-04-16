from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not initialized")
        return self._connection

    async def connect(self) -> None:
        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON;")
        await self._connection.execute("PRAGMA journal_mode = WAL;")
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def init(self) -> None:
        await self.connect()
        await self._create_schema()

    async def _create_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            username TEXT,
            full_name TEXT NOT NULL,
            is_subscribed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            channel_title TEXT,
            channel_url TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            UNIQUE(user_id, author_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            announce_text TEXT,
            announce_photo_file_id TEXT,
            notify_at TEXT NOT NULL,
            send_at TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS broadcast_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER NOT NULL,
            telegram_file_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            mime_type TEXT,
            FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS broadcast_authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            UNIQUE(broadcast_id, author_id),
            FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_text TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
        await self.connection.executescript(schema)
        await self._ensure_column("authors", "channel_title", "TEXT")
        await self._ensure_column("authors", "channel_url", "TEXT")
        await self._ensure_column("broadcasts", "announce_text", "TEXT")
        await self._ensure_column("broadcasts", "announce_photo_file_id", "TEXT")
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO broadcast_authors (broadcast_id, author_id)
            SELECT id, author_id
            FROM broadcasts
            WHERE author_id IS NOT NULL
            """
        )
        await self.connection.commit()
        logger.info("Database schema initialized")

    async def _ensure_column(self, table_name: str, column_name: str, column_definition: str) -> None:
        rows = await self.fetchall(f"PRAGMA table_info({table_name})")
        existing_columns = {str(row["name"]) for row in rows}
        if column_name in existing_columns:
            return
        await self.connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        cursor = await self.connection.execute(query, params)
        await self.connection.commit()
        return cursor

    async def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        await self.connection.executemany(query, params)
        await self.connection.commit()

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self.connection.execute(query, params)
        return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        cursor = await self.connection.execute(query, params)
        return await cursor.fetchall()
