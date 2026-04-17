from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.keyboards import channels_subscription_keyboard, subscribe_keyboard
from app.models_logic import Author, Repository, extract_channel_username

router = Router()
logger = logging.getLogger(__name__)


def format_authors_list(authors: list[str]) -> str:
    if not authors:
        return "Список активных авторов пока пуст."
    return "\n".join(f"• {name}" for name in authors)


def format_channel_requirements(authors: list[Author]) -> str:
    if not authors:
        return (
            "Сейчас обязательных каналов нет.\n\n"
            "Нажмите кнопку ниже, чтобы подтвердить подписку на рассылку."
        )

    channel_lines = []
    for author in authors:
        channel_title = author.channel_title or author.name
        channel_lines.append(f"• {author.name} — {channel_title}")

    return (
        "Чтобы подписаться на рассылку, сначала подпишитесь на все каналы авторов:\n\n"
        f"{chr(10).join(channel_lines)}\n\n"
        "После подписки нажмите «Проверить подписку»."
    )


async def get_missing_channel_titles(bot: Bot, authors: list[Author], user_id: int) -> tuple[list[str], bool]:
    missing_titles: list[str] = []
    has_unverifiable_channels = False

    for author in authors:
        chat_id = extract_channel_username(author.channel_url)
        channel_title = author.channel_title or author.name
        if chat_id is None:
            has_unverifiable_channels = True
            logger.warning("Channel URL cannot be verified for author_id=%s url=%s", author.id, author.channel_url)
            continue
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            has_unverifiable_channels = True
            logger.warning("Failed to verify channel %s for user %s: %s", chat_id, user_id, exc)
            continue

        if member.status in {"left", "kicked"}:
            missing_titles.append(channel_title)

    return missing_titles, has_unverifiable_channels


@router.message(Command("start"))
async def start_handler(message: Message, repository: Repository) -> None:
    await repository.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    user = await repository.get_user_by_telegram_id(message.from_user.id)

    if user and int(user["is_subscribed"]) == 1:
        authors = await repository.get_user_author_names(message.from_user.id)
        await message.answer(
            "Подписка на рассылку уже подтверждена.\n\n"
            "Вы будете получать материалы по этим активным авторам:\n"
            f"{format_authors_list(authors)}"
        )
        return

    required_authors = await repository.get_required_channel_authors()
    await message.answer(
        "Добро пожаловать.\n\n"
        f"{format_channel_requirements(required_authors)}",
        reply_markup=channels_subscription_keyboard(required_authors) if required_authors else subscribe_keyboard(),
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "/start - регистрация и проверка подписки на каналы авторов\n"
        "/help - помощь по командам\n\n"
        "Для доступа к рассылке пользователь должен быть подписан на все обязательные каналы авторов."
    )


@router.callback_query(F.data == "user:confirm_subscription")
async def confirm_subscription_handler(
    callback: CallbackQuery,
    repository: Repository,
    bot: Bot,
) -> None:
    required_authors = await repository.get_required_channel_authors()
    if required_authors:
        missing_titles, has_unverifiable_channels = await get_missing_channel_titles(
            bot=bot,
            authors=required_authors,
            user_id=callback.from_user.id,
        )
        if has_unverifiable_channels:
            await callback.answer(
                "Проверка недоступна. Добавьте бота в администраторы каналов и используйте публичные @username.",
                show_alert=True,
            )
            return
        if missing_titles:
            await callback.answer(
                "Подписка найдена не на всех каналах. Откройте ссылки и повторите проверку.",
                show_alert=True,
            )
            await callback.message.edit_text(
                "Подписка на рассылку пока не подтверждена.\n\n"
                "Нужно подписаться на все каналы из списка ниже:\n"
                f"{format_authors_list(missing_titles)}",
                reply_markup=channels_subscription_keyboard(required_authors),
            )
            return

    await repository.confirm_subscription(callback.from_user.id)
    authors = await repository.get_user_author_names(callback.from_user.id)
    await callback.message.edit_text(
        "Подписка на рассылку подтверждена.\n"
        "Материалы будут приходить по всем активным авторам из списка ниже.\n\n"
        f"{format_authors_list(authors)}"
    )
    await callback.answer("Подписка на рассылку подтверждена")
