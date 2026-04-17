---
name: lausha-notes-bot
description: Use this skill when working on the Telegram MVP bot in this repository: aiogram 3 handlers, SQLite access via aiosqlite, channel-subscription gating before broadcast access, multi-author broadcasts, author channel title/url management, photo-and-text notify announcements, APScheduler restore/send flow, and VPS/systemd deployment updates.
---

# Lausha Notes Bot

Repository skill for the Telegram broadcast bot MVP.

## Stack

- Python 3.11+ runtime target
- aiogram 3.x
- SQLite via `aiosqlite`
- APScheduler for delayed notify/send jobs
- `.env` config loaded by `python-dotenv`

## Project map

- `main.py`: app entrypoint, dependency wiring, polling startup
- `app/config.py`: environment loading and timezone setup
- `app/db.py`: SQLite connection and schema bootstrap
- `app/models_logic.py`: repository-style data access and business logic
- `app/scheduler.py`: APScheduler integration, restore-on-start, notify/send jobs
- `app/handlers/user.py`: `/start`, `/help`, required-channel subscription check before broadcast access
- `app/handlers/admin.py`: admin menu, author CRUD, channel title/url editing, broadcast FSM, optional notify photo/text
- `app/keyboards.py`: reply and inline keyboards
- `app/states.py`: FSM states

## Working rules

- Keep the storage layer light. Prefer extending `Repository` in `app/models_logic.py` instead of adding an ORM.
- Authors now carry channel metadata. Preserve `channel_title` and `channel_url` handling when changing author flows.
- Access to the broadcast is now gated by verified channel subscriptions. Do not revert `/start` back to blind confirmation.
- Channel verification relies on public `t.me/<username>` links and Telegram `getChatMember`. Private invite links are not enough for this flow.
- Production checks require the bot to be an admin in the required channels; keep that assumption explicit in docs and ops notes.
- Broadcasts can target multiple authors through `broadcast_authors`. Do not collapse this back to single-author behavior by accident.
- Notify flow can include `announce_photo_file_id` and `announce_text` on the broadcast. Keep these fields optional.
- Scheduled broadcasts depend on string datetimes in `YYYY-MM-DD HH:MM` and a shared timezone from config. Preserve that format unless there is a deliberate migration.
- Files are resent through Telegram `file_id`. Do not add local file persistence for MVP behavior.
- When changing broadcast flow, check both scheduler paths:
  - restore from DB on startup
  - live scheduling after admin creates a broadcast
- User-facing channel links are rendered as HTML links in bot messages. Keep escaping and URL validation intact.
- Photo notifications use Telegram caption limits. Preserve the current short-text guard or replace it with another explicit strategy if you change this flow.
- If a new active author is added, subscribed users must still get automatic `user_authors` links.
- Keep admin UX simple: inline or reply keyboards, short prompts, explicit back paths.

## Validation

- Fast syntax check: `python3 -m compileall app main.py`
- Local run: `.venv/bin/python main.py`
- For process management on VPS, prefer `systemd` over detached shell processes.

## Deployment notes

- Never commit `.env`, `.venv`, or SQLite database files.
- Update `README.md` when changing setup, environment variables, admin flow, or deployment steps.
- Current VPS layout uses `/opt/fl_lausha_notes`.
- Current systemd unit on the VPS is `fl-lausha-notes.service`.
