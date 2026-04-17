from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models_logic import Author, Broadcast


def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Проверить подписку", callback_data="user:confirm_subscription")]]
    )


def channels_subscription_keyboard(authors: list[Author]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for author in authors:
        if author.channel_url:
            title = author.channel_title or author.name
            builder.row(InlineKeyboardButton(text=f"Подписаться: {title}", url=author.channel_url))
    builder.row(InlineKeyboardButton(text="Проверить подписку", callback_data="user:confirm_subscription"))
    return builder.as_markup()


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


def skip_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def authors_manage_keyboard(authors: list[Author]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for author in authors:
        icon = "🟢" if author.is_active else "⚪"
        builder.button(
            text=f"{icon} {author.name}",
            callback_data=f"admin:author:view:{author.id}",
        )
    builder.button(text="Добавить автора", callback_data="admin:add_author")
    builder.adjust(1)
    return builder.as_markup()


def author_detail_keyboard(author: Author) -> InlineKeyboardMarkup:
    toggle_action = "deactivate" if author.is_active else "activate"
    toggle_label = "Отключить автора" if author.is_active else "Активировать автора"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить название канала", callback_data=f"admin:author:edit_title:{author.id}")],
            [InlineKeyboardButton(text="Изменить ссылку канала", callback_data=f"admin:author:edit_url:{author.id}")],
            [InlineKeyboardButton(text=toggle_label, callback_data=f"admin:author:{toggle_action}:{author.id}")],
            [InlineKeyboardButton(text="Назад к списку", callback_data="admin:author:list")],
        ]
    )


def broadcast_authors_keyboard(authors: list[Author], selected_ids: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    selected = set(selected_ids)
    for author in authors:
        marker = "✅" if author.id in selected else "⬜"
        builder.button(
            text=f"{marker} {author.name}",
            callback_data=f"admin:broadcast_author:toggle:{author.id}",
        )
    builder.button(text="Готово", callback_data="admin:broadcast_author:done")
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
        authors_label = ", ".join(broadcast.author_names)
        builder.button(
            text=f"{broadcast.id}. {authors_label} | {broadcast.send_at}",
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
