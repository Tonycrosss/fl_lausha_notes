from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models_logic import Author, Broadcast


def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить подписку", callback_data="user:confirm_subscription")]
        ]
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Авторы"), KeyboardButton(text="Новая рассылка")],
            [KeyboardButton(text="Запланированные рассылки"), KeyboardButton(text="Статистика")],
        ],
        resize_keyboard=True,
    )


def back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Назад")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def authors_manage_keyboard(authors: list[Author]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for author in authors:
        action = "deactivate" if author.is_active else "activate"
        icon = "🟢" if author.is_active else "⚪"
        builder.button(
            text=f"{icon} {author.name}",
            callback_data=f"admin:author:{action}:{author.id}",
        )
    builder.button(text="Добавить автора", callback_data="admin:add_author")
    builder.adjust(1)
    return builder.as_markup()


def authors_select_keyboard(authors: list[Author], prefix: str = "admin:broadcast_author") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for author in authors:
        builder.button(text=author.name, callback_data=f"{prefix}:{author.id}")
    builder.adjust(1)
    return builder.as_markup()


def broadcast_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сохранить", callback_data="admin:broadcast:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:broadcast:cancel")],
        ]
    )


def done_files_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Готово", callback_data="admin:broadcast:files_done")]
        ]
    )


def scheduled_broadcasts_keyboard(broadcasts: list[Broadcast]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for broadcast in broadcasts:
        builder.button(
            text=f"{broadcast.id}. {broadcast.author_name} | {broadcast.send_at}",
            callback_data=f"admin:broadcast:delete_prompt:{broadcast.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def delete_broadcast_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить", callback_data=f"admin:broadcast:delete:{broadcast_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:broadcast:delete_cancel")],
        ]
    )
