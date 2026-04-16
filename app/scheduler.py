from __future__ import annotations

from html import escape
import logging
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.models_logic import (
    STATUS_NOTIFIED,
    STATUS_SCHEDULED,
    STATUS_SENT,
    Broadcast,
    Repository,
    parse_datetime,
)

logger = logging.getLogger(__name__)


def format_broadcast_authors(author_names: list[str]) -> str:
    return ", ".join(author_names)


def format_author_links(authors) -> str:
    lines: list[str] = []
    for author in authors:
        if author.channel_url and author.channel_title:
            lines.append(f'• <a href="{escape(author.channel_url, quote=True)}">{escape(author.channel_title)}</a>')
        elif author.channel_title:
            lines.append(f"• {escape(author.channel_title)}")
        else:
            lines.append(f"• {escape(author.name)}")
    return "\n".join(lines)


def build_notify_text(broadcast, authors_text: str, author_links: str) -> str:
    parts: list[str] = []
    if broadcast.announce_text:
        parts.append(escape(broadcast.announce_text))
    parts.append(f"Авторы: {escape(authors_text)}")
    parts.append(f"Каналы:\n{author_links}")
    parts.append(f"Рассылка: {escape(broadcast.title)}")
    parts.append(f"Время отправки: {broadcast.send_at}")
    return "\n\n".join(parts)


class BroadcastScheduler:
    def __init__(self, repository: Repository, bot: Bot, timezone) -> None:
        self.repository = repository
        self.bot = bot
        self.timezone = timezone
        self.scheduler = AsyncIOScheduler(timezone=timezone)

    def start(self) -> None:
        self.scheduler.start()

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    def _notify_job_id(self, broadcast_id: int) -> str:
        return f"broadcast_notify_{broadcast_id}"

    def _send_job_id(self, broadcast_id: int) -> str:
        return f"broadcast_send_{broadcast_id}"

    def remove_broadcast_jobs(self, broadcast_id: int) -> None:
        for job_id in (self._notify_job_id(broadcast_id), self._send_job_id(broadcast_id)):
            job = self.scheduler.get_job(job_id)
            if job:
                job.remove()

    def schedule_broadcast(self, broadcast: Broadcast) -> None:
        notify_dt = parse_datetime(broadcast.notify_at, self.timezone)
        send_dt = parse_datetime(broadcast.send_at, self.timezone)
        now = datetime.now(self.timezone)

        self.remove_broadcast_jobs(broadcast.id)

        if notify_dt > now and broadcast.status == STATUS_SCHEDULED:
            self.scheduler.add_job(
                self.process_notify,
                trigger=DateTrigger(run_date=notify_dt),
                id=self._notify_job_id(broadcast.id),
                args=[broadcast.id],
                replace_existing=True,
            )

        if send_dt > now and broadcast.status in (STATUS_SCHEDULED, STATUS_NOTIFIED):
            self.scheduler.add_job(
                self.process_send,
                trigger=DateTrigger(run_date=send_dt),
                id=self._send_job_id(broadcast.id),
                args=[broadcast.id],
                replace_existing=True,
            )

    async def restore_jobs(self) -> None:
        broadcasts = await self.repository.get_scheduled_broadcasts()
        now = datetime.now(self.timezone)

        for broadcast in broadcasts:
            notify_dt = parse_datetime(broadcast.notify_at, self.timezone)
            send_dt = parse_datetime(broadcast.send_at, self.timezone)

            if send_dt <= now:
                logger.warning(
                    "Broadcast %s is overdue and will not be auto-sent. notify_at=%s send_at=%s",
                    broadcast.id,
                    broadcast.notify_at,
                    broadcast.send_at,
                )
                continue

            if notify_dt <= now < send_dt:
                logger.info(
                    "Notify time already passed for broadcast %s, scheduling send only",
                    broadcast.id,
                )
            self.schedule_broadcast(broadcast)

    async def process_notify(self, broadcast_id: int) -> None:
        broadcast = await self.repository.get_broadcast(broadcast_id)
        if broadcast is None or broadcast.status != STATUS_SCHEDULED:
            return

        recipients = await self.repository.get_broadcast_recipients(broadcast.id)
        authors = await self.repository.get_broadcast_authors(broadcast.id)
        authors_text = format_broadcast_authors(broadcast.author_names)
        author_links = format_author_links(authors)
        text = build_notify_text(broadcast, authors_text, author_links)

        for recipient in recipients:
            try:
                if broadcast.announce_photo_file_id:
                    await self.bot.send_photo(
                        recipient["telegram_id"],
                        photo=broadcast.announce_photo_file_id,
                        caption=text[:1024],
                    )
                else:
                    await self.bot.send_message(recipient["telegram_id"], text)
            except Exception as exc:
                logger.exception(
                    "Failed to send notification for broadcast %s to user %s: %s",
                    broadcast_id,
                    recipient["telegram_id"],
                    exc,
                )

        await self.repository.update_broadcast_status(broadcast_id, STATUS_NOTIFIED)
        logger.info("Broadcast %s notification stage completed", broadcast_id)

    async def process_send(self, broadcast_id: int) -> None:
        broadcast = await self.repository.get_broadcast(broadcast_id)
        if broadcast is None or broadcast.status == STATUS_SENT:
            return

        recipients = await self.repository.get_broadcast_recipients(broadcast.id)
        files = await self.repository.get_broadcast_files(broadcast_id)
        authors = await self.repository.get_broadcast_authors(broadcast.id)
        authors_text = format_broadcast_authors(broadcast.author_names)
        author_links = format_author_links(authors)

        for recipient in recipients:
            user_id = int(recipient["id"])
            try:
                await self.bot.send_message(
                    recipient["telegram_id"],
                    "Материалы по авторам:\n"
                    f"{escape(authors_text)}\n\n"
                    f"Каналы:\n{author_links}\n\n"
                    f"{escape(broadcast.title)}",
                )
                for file in files:
                    await self.bot.send_document(
                        recipient["telegram_id"],
                        document=file.telegram_file_id,
                        caption=file.file_name,
                    )
                await self.repository.add_broadcast_log(broadcast_id, user_id, "success")
            except Exception as exc:
                logger.exception(
                    "Failed to send broadcast %s to user %s: %s",
                    broadcast_id,
                    recipient["telegram_id"],
                    exc,
                )
                await self.repository.add_broadcast_log(
                    broadcast_id,
                    user_id,
                    "error",
                    str(exc)[:1000],
                )

        await self.repository.update_broadcast_status(broadcast_id, STATUS_SENT)
        self.remove_broadcast_jobs(broadcast_id)
        logger.info("Broadcast %s send stage completed", broadcast_id)
