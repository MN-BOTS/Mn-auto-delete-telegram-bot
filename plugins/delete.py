from datetime import timedelta
from pyrogram import Client, filters
import database

TRACKED_CHATS = filters.group | filters.channel

@Client.on_message(TRACKED_CHATS, group=10)
async def auto_delete_handler(client, message):
    database.save_chat(message.chat, getattr(message.from_user, "id", None))
    settings = database.get_chat_settings(message.chat.id)
    delay = int(settings.get("delete_delay") or 0)

    # Default is safe: nothing is deleted until an owner/admin enables a chat.
    if not settings.get("enabled") or delay <= 0:
        return

    delete_at = database.now_utc() + timedelta(seconds=delay)
    database.save_scheduled_message(message.chat.id, message.id, delete_at)
    client.schedule_delete(message.chat.id, message.id, delete_at)
