---
name: lausha-notes-bot
description: Use this skill when working on the Telegram MVP bot in this repository: aiogram 3 handlers, SQLite access via aiosqlite, APScheduler restore/send flow, admin FSM for broadcasts, and deployment updates for VPS/systemd.
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
- `app/handlers/user.py`: `/start`, `/help`, subscription confirmation
- `app/handlers/admin.py`: admin menu, author management, broadcast FSM
- `app/keyboards.py`: reply and inline keyboards
- `app/states.py`: FSM states

## Working rules

- Keep the storage layer light. Prefer extending `Repository` in `app/models_logic.py` instead of adding an ORM.
- Scheduled broadcasts depend on string datetimes in `YYYY-MM-DD HH:MM` and a shared timezone from config. Preserve that format unless there is a deliberate migration.
- Files are resent through Telegram `file_id`. Do not add local file persistence for MVP behavior.
- When changing broadcast flow, check both scheduler paths:
  - restore from DB on startup
  - live scheduling after admin creates a broadcast
- If a new active author is added, subscribed users must still get automatic `user_authors` links.
- Keep admin UX simple: inline or reply keyboards, short prompts, explicit back paths.

## Validation

- Fast syntax check: `python3 -m compileall app main.py`
- Local run: `.venv/bin/python main.py`
- For process management on VPS, prefer `systemd` over detached shell processes.

## Deployment notes

- Never commit `.env`, `.venv`, or SQLite database files.
- Update `README.md` when changing setup, environment variables, admin flow, or deployment steps.
