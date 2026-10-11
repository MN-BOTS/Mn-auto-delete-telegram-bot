
import asyncio
import logging
from datetime import timedelta

from pyrogram import Client, filters

import database

TRACKED_CHATS = filters.group | filters.channel

_registered_chats: set[int] = set()
_registration_lock = asyncio.Lock()


@Client.on_message(TRACKED_CHATS, group=10)
async def auto_delete_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    user_id = getattr(message.from_user, "id", None)

    try:
        if chat_id not in _registered_chats:
            async with _registration_lock:
                if chat_id not in _registered_chats:
                    await asyncio.to_thread(database.save_chat, chat, user_id)
                    _registered_chats.add(chat_id)

        # PyMongo is synchronous; never let its network I/O block the event loop.
        settings = await asyncio.to_thread(database.get_chat_settings, chat_id)
        delay = min(max(int(settings.get("delete_delay") or 0), 0), 3600)
        if not settings.get("enabled") or delay <= 0:
            return

        delete_at = database.now_utc() + timedelta(seconds=delay)
        await asyncio.to_thread(
            database.save_scheduled_message, chat_id, message.id, delete_at
        )
        client.schedule_delete(chat_id, message.id, delete_at)

    except asyncio.CancelledError:
        raise
    except Exception:
        logging.exception(
            "Auto-delete handler failed (chat=%s, message=%s)",
            chat_id,
            message.id,
        )
