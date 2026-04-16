from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddAuthorStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_channel_title = State()
    waiting_for_channel_url = State()


class EditAuthorStates(StatesGroup):
    waiting_for_channel_title = State()
    waiting_for_channel_url = State()


class CreateBroadcastStates(StatesGroup):
    waiting_for_author = State()
    waiting_for_title = State()
    waiting_for_announce_photo = State()
    waiting_for_announce_text = State()
    waiting_for_files = State()
    waiting_for_notify_at = State()
    waiting_for_send_at = State()
    waiting_for_confirmation = State()
