from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import subscribe_keyboard
from app.models_logic import Repository

router = Router()


def format_authors_list(authors: list[str]) -> str:
    if not authors:
        return "Список активных авторов пока пуст."
    return "\n".join(f"• {name}" for name in authors)


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
            "Вы уже подписаны.\n\nТекущие активные авторы:\n"
            f"{format_authors_list(authors)}"
        )
        return

    await message.answer(
        "Добро пожаловать.\n\n"
        "Подтвердите подписку, чтобы получать материалы всех активных авторов.",
        reply_markup=subscribe_keyboard(),
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "/start - регистрация и подтверждение подписки\n"
        "/help - помощь по командам\n\n"
        "После подтверждения подписки вы будете автоматически подписаны на всех активных авторов."
    )


@router.callback_query(F.data == "user:confirm_subscription")
async def confirm_subscription_handler(callback: CallbackQuery, repository: Repository) -> None:
    await repository.confirm_subscription(callback.from_user.id)
    authors = await repository.get_user_author_names(callback.from_user.id)
    await callback.message.edit_text(
        "Подписка подтверждена.\n\n"
        "Вы подписаны на всех активных авторов:\n"
        f"{format_authors_list(authors)}"
    )
    await callback.answer("Подписка активирована")
