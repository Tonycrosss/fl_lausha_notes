from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, Message

from app.keyboards import (
    admin_menu_keyboard,
    authors_manage_keyboard,
    authors_select_keyboard,
    back_keyboard,
    broadcast_confirmation_keyboard,
    delete_broadcast_keyboard,
    done_files_keyboard,
    scheduled_broadcasts_keyboard,
)
from app.models_logic import DATETIME_FORMAT, Repository, parse_datetime
from app.scheduler import BroadcastScheduler
from app.states import AddAuthorStates, CreateBroadcastStates

router = Router()
logger = logging.getLogger(__name__)


def is_admin(message: Message | CallbackQuery, admin_telegram_id: int) -> bool:
    user_id = message.from_user.id if isinstance(message, CallbackQuery) else message.from_user.id
    return user_id == admin_telegram_id


def format_authors_manage_text(authors) -> str:
    if not authors:
        return "Авторов пока нет."
    lines = ["Список авторов:"]
    for author in authors:
        status = "активен" if author.is_active else "отключен"
        lines.append(f"{author.id}. {author.name} [{status}]")
    return "\n".join(lines)


def format_broadcast_preview(data: dict, author_name: str) -> str:
    files = data.get("files", [])
    file_lines = "\n".join(f"• {item['file_name']}" for item in files) if files else "Файлы не загружены"
    return (
        "Подтвердите создание рассылки.\n\n"
        f"Автор: {author_name}\n"
        f"Название: {data['title']}\n"
        f"Уведомление: {data['notify_at']}\n"
        f"Отправка: {data['send_at']}\n"
        f"Файлы:\n{file_lines}"
    )


async def show_admin_menu(message: Message) -> None:
    await message.answer("Панель администратора", reply_markup=admin_menu_keyboard())


@router.message(Command("admin"))
async def admin_panel_handler(message: Message, admin_telegram_id: int) -> None:
    if not is_admin(message, admin_telegram_id):
        return
    await show_admin_menu(message)


@router.message(F.text == "Авторы")
async def authors_menu_handler(
    message: Message,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    authors = await repository.get_all_authors()
    await message.answer(
        format_authors_manage_text(authors),
        reply_markup=authors_manage_keyboard(authors),
    )


@router.callback_query(F.data == "admin:add_author")
async def add_author_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return
    await state.set_state(AddAuthorStates.waiting_for_name)
    await callback.message.answer("Введите имя нового автора.", reply_markup=back_keyboard())
    await callback.answer()


@router.message(AddAuthorStates.waiting_for_name)
async def add_author_handler(
    message: Message,
    state: FSMContext,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    if message.text == "Назад":
        await state.clear()
        await show_admin_menu(message)
        return

    if not message.text or not message.text.strip():
        await message.answer("Имя автора не должно быть пустым.")
        return

    try:
        author_id = await repository.create_author(message.text)
    except Exception as exc:
        logger.exception("Failed to create author: %s", exc)
        await message.answer("Не удалось добавить автора. Возможно, такое имя уже существует.")
        return

    await state.clear()
    await message.answer(f"Автор добавлен. ID: {author_id}", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data.startswith("admin:author:"))
async def author_toggle_handler(
    callback: CallbackQuery,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return

    _, _, action, author_id_str = callback.data.split(":")
    author_id = int(author_id_str)
    await repository.set_author_status(author_id, action == "activate")
    authors = await repository.get_all_authors()
    await callback.message.edit_text(
        format_authors_manage_text(authors),
        reply_markup=authors_manage_keyboard(authors),
    )
    await callback.answer("Статус автора обновлен")


@router.message(F.text == "Новая рассылка")
async def new_broadcast_handler(
    message: Message,
    state: FSMContext,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    authors = await repository.get_active_authors()
    if not authors:
        await message.answer("Нет активных авторов. Сначала добавьте автора.")
        return

    await state.clear()
    await state.set_state(CreateBroadcastStates.waiting_for_author)
    await message.answer(
        "Выберите автора для рассылки.",
        reply_markup=authors_select_keyboard(authors),
    )


@router.callback_query(F.data.startswith("admin:broadcast_author:"))
async def select_broadcast_author_handler(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return

    author_id = int(callback.data.split(":")[-1])
    author = await repository.get_author(author_id)
    if author is None or not author.is_active:
        await callback.answer("Автор недоступен", show_alert=True)
        return

    await state.update_data(author_id=author.id, author_name=author.name, files=[])
    await state.set_state(CreateBroadcastStates.waiting_for_title)
    await callback.message.answer("Введите название рассылки.", reply_markup=back_keyboard())
    await callback.answer()


@router.message(CreateBroadcastStates.waiting_for_title)
async def broadcast_title_handler(
    message: Message,
    state: FSMContext,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    if message.text == "Назад":
        await state.clear()
        await show_admin_menu(message)
        return

    if not message.text or not message.text.strip():
        await message.answer("Название рассылки не должно быть пустым.")
        return

    await state.update_data(title=message.text.strip())
    await state.set_state(CreateBroadcastStates.waiting_for_files)
    await message.answer(
        "Загрузите один или несколько документов. Когда закончите, нажмите Готово.",
        reply_markup=done_files_keyboard(),
    )


@router.message(CreateBroadcastStates.waiting_for_files, F.text == "Назад")
async def broadcast_files_back_handler(
    message: Message,
    state: FSMContext,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return
    await state.set_state(CreateBroadcastStates.waiting_for_title)
    await message.answer("Введите название рассылки заново.", reply_markup=back_keyboard())


@router.message(CreateBroadcastStates.waiting_for_files, F.document)
async def broadcast_file_handler(
    message: Message,
    state: FSMContext,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    document: Document = message.document
    data = await state.get_data()
    files = list(data.get("files", []))
    files.append(
        {
            "telegram_file_id": document.file_id,
            "file_name": document.file_name or "document",
            "mime_type": document.mime_type,
        }
    )
    await state.update_data(files=files)
    await message.answer(f"Файл сохранен: {document.file_name}")


@router.message(CreateBroadcastStates.waiting_for_files)
async def broadcast_files_invalid_handler(
    message: Message,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return
    await message.answer("Отправьте документ или нажмите кнопку Готово.")


@router.callback_query(F.data == "admin:broadcast:files_done")
async def broadcast_files_done_handler(
    callback: CallbackQuery,
    state: FSMContext,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return

    data = await state.get_data()
    if not data.get("files"):
        await callback.answer("Сначала загрузите хотя бы один файл", show_alert=True)
        return

    await state.set_state(CreateBroadcastStates.waiting_for_notify_at)
    await callback.message.answer(
        f"Введите дату и время уведомления в формате {DATETIME_FORMAT}.",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


def validate_datetime_order(notify_at: str, send_at: str, tzinfo) -> tuple[bool, str]:
    notify_dt = parse_datetime(notify_at, tzinfo)
    send_dt = parse_datetime(send_at, tzinfo)
    if send_dt <= notify_dt:
        return False, "Время отправки должно быть позже времени уведомления."
    if notify_dt <= datetime.now(tzinfo):
        return False, "Время уведомления должно быть в будущем."
    return True, ""


@router.message(CreateBroadcastStates.waiting_for_notify_at)
async def broadcast_notify_at_handler(
    message: Message,
    state: FSMContext,
    admin_telegram_id: int,
    tzinfo,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    if message.text == "Назад":
        await state.set_state(CreateBroadcastStates.waiting_for_files)
        await message.answer(
            "Вернулись к загрузке файлов. Можете отправить документы или нажать Готово.",
            reply_markup=done_files_keyboard(),
        )
        return

    try:
        parse_datetime(message.text.strip(), tzinfo)
    except ValueError:
        await message.answer(f"Некорректный формат. Используйте {DATETIME_FORMAT}.")
        return

    await state.update_data(notify_at=message.text.strip())
    await state.set_state(CreateBroadcastStates.waiting_for_send_at)
    await message.answer(f"Введите дату и время отправки в формате {DATETIME_FORMAT}.")


@router.message(CreateBroadcastStates.waiting_for_send_at)
async def broadcast_send_at_handler(
    message: Message,
    state: FSMContext,
    repository: Repository,
    admin_telegram_id: int,
    tzinfo,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    if message.text == "Назад":
        await state.set_state(CreateBroadcastStates.waiting_for_notify_at)
        await message.answer(f"Введите дату и время уведомления в формате {DATETIME_FORMAT}.")
        return

    try:
        parse_datetime(message.text.strip(), tzinfo)
    except ValueError:
        await message.answer(f"Некорректный формат. Используйте {DATETIME_FORMAT}.")
        return

    data = await state.get_data()
    is_valid, error_text = validate_datetime_order(data["notify_at"], message.text.strip(), tzinfo)
    if not is_valid:
        await message.answer(error_text)
        return

    await state.update_data(send_at=message.text.strip())
    data = await state.get_data()
    author = await repository.get_author(int(data["author_id"]))
    if author is None:
        await state.clear()
        await message.answer("Автор не найден. Начните создание рассылки заново.")
        return

    await state.set_state(CreateBroadcastStates.waiting_for_confirmation)
    await message.answer(
        format_broadcast_preview(data, author.name),
        reply_markup=broadcast_confirmation_keyboard(),
    )


@router.callback_query(F.data == "admin:broadcast:confirm")
async def broadcast_confirm_handler(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    broadcast_scheduler: BroadcastScheduler,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return

    data = await state.get_data()
    broadcast_id = await repository.create_broadcast(
        author_id=int(data["author_id"]),
        title=str(data["title"]),
        notify_at=str(data["notify_at"]),
        send_at=str(data["send_at"]),
        files=list(data["files"]),
    )
    broadcast = await repository.get_broadcast(broadcast_id)
    if broadcast:
        broadcast_scheduler.schedule_broadcast(broadcast)

    await state.clear()
    await callback.message.answer(
        f"Рассылка #{broadcast_id} создана и поставлена в планировщик.",
        reply_markup=admin_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast:cancel")
async def broadcast_cancel_creation_handler(
    callback: CallbackQuery,
    state: FSMContext,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return
    await state.clear()
    await callback.message.answer("Создание рассылки отменено.", reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.message(F.text == "Запланированные рассылки")
async def scheduled_broadcasts_handler(
    message: Message,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    broadcasts = await repository.get_scheduled_broadcasts()
    if not broadcasts:
        await message.answer("Запланированных рассылок нет.")
        return

    lines = [
        f"{item.id}. {item.author_name} | {item.title} | уведомление: {item.notify_at} | отправка: {item.send_at}"
        for item in broadcasts
    ]
    await message.answer(
        "Запланированные рассылки:\n\n" + "\n".join(lines),
        reply_markup=scheduled_broadcasts_keyboard(broadcasts),
    )


@router.callback_query(F.data.startswith("admin:broadcast:delete_prompt:"))
async def delete_broadcast_prompt_handler(
    callback: CallbackQuery,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return

    broadcast_id = int(callback.data.split(":")[-1])
    broadcast = await repository.get_broadcast(broadcast_id)
    if broadcast is None:
        await callback.answer("Рассылка не найдена", show_alert=True)
        return

    await callback.message.answer(
        f"Удалить рассылку #{broadcast.id}?\n{broadcast.author_name} | {broadcast.title}",
        reply_markup=delete_broadcast_keyboard(broadcast.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:broadcast:delete:"))
async def delete_broadcast_handler(
    callback: CallbackQuery,
    repository: Repository,
    broadcast_scheduler: BroadcastScheduler,
    admin_telegram_id: int,
) -> None:
    if not is_admin(callback, admin_telegram_id):
        return

    broadcast_id = int(callback.data.split(":")[-1])
    await repository.cancel_broadcast(broadcast_id)
    broadcast_scheduler.remove_broadcast_jobs(broadcast_id)
    await callback.message.answer("Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast:delete_cancel")
async def cancel_delete_broadcast_handler(callback: CallbackQuery, admin_telegram_id: int) -> None:
    if not is_admin(callback, admin_telegram_id):
        return
    await callback.message.answer("Удаление отменено.")
    await callback.answer()


@router.message(F.text == "Статистика")
async def statistics_handler(
    message: Message,
    repository: Repository,
    admin_telegram_id: int,
) -> None:
    if not is_admin(message, admin_telegram_id):
        return

    stats = await repository.get_statistics()
    text = (
        "Статистика:\n\n"
        f"Всего пользователей: {stats['users_total']}\n"
        f"Активных авторов: {stats['active_authors_total']}\n"
        f"Запланированных рассылок: {stats['scheduled_broadcasts_total']}\n"
        f"Успешных отправок в последней рассылке: {stats['last_broadcast_success_total']}\n"
        f"Ошибок отправки в последней рассылке: {stats['last_broadcast_error_total']}"
    )
    await message.answer(text)
