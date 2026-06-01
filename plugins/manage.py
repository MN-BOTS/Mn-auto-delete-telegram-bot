from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER
import database
from utils import parse_time, human_time, is_chat_admin, settings_keyboard, settings_text, chat_help_text

CHAT_FILTER = filters.group | filters.channel

async def can_manage(client, message):
    if message.from_user and message.from_user.id == OWNER.ID:
        return True
    user_id = getattr(message.from_user, "id", None)
    return await is_chat_admin(client, message.chat.id, user_id)

async def deny(message):
    await message.reply_text("**Only the group/channel owner or admins can manage this bot here.**")

@Client.on_message(CHAT_FILTER & filters.command(["settings", "autodelete", "panel"]))
async def settings_cmd(client, message):
    database.save_chat(message.chat, getattr(message.from_user, "id", None))
    if not await can_manage(client, message):
        return await deny(message)
    settings = database.get_chat_settings(message.chat.id)
    await message.reply_text(
        settings_text(message.chat, settings),
        reply_markup=settings_keyboard(message.chat.id, settings.get("enabled")),
    )

@Client.on_message(CHAT_FILTER & filters.command(["setdelete", "deletedelay"]))
async def set_delete_cmd(client, message):
    if not await can_manage(client, message):
        return await deny(message)
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/setdelete 30s` or `/setdelete off`", quote=True)
    try:
        seconds = parse_time(message.command[1])
    except ValueError as err:
        return await message.reply_text(f"Invalid time: {err}\nExamples: `10s`, `5m`, `1h`, `off` (1 hour max)", quote=True)

    enabled = seconds > 0
    settings = database.set_chat_settings(message.chat, message.from_user.id, enabled=enabled, delete_delay=seconds)
    await message.reply_text(
        f"**Updated ✅**\n\nAuto-delete: {'Enabled' if enabled else 'Disabled'}\nTime: `{human_time(seconds)}`",
        reply_markup=settings_keyboard(message.chat.id, settings.get("enabled")),
    )

@Client.on_message(CHAT_FILTER & filters.command("deleteon"))
async def delete_on_cmd(client, message):
    if not await can_manage(client, message):
        return await deny(message)
    settings = database.get_chat_settings(message.chat.id)
    delay = min(int(settings.get("delete_delay") or 0), 3600) or 60
    settings = database.set_chat_settings(message.chat, message.from_user.id, enabled=True, delete_delay=delay)
    await message.reply_text(f"Auto-delete enabled ✅\nTime: `{human_time(delay)}`", reply_markup=settings_keyboard(message.chat.id, True))

@Client.on_message(CHAT_FILTER & filters.command(["deleteoff", "resetdelete"]))
async def delete_off_cmd(client, message):
    if not await can_manage(client, message):
        return await deny(message)
    database.set_chat_settings(message.chat, message.from_user.id, enabled=False)
    await message.reply_text("Auto-delete disabled 📴\nNo new messages will be scheduled.", reply_markup=settings_keyboard(message.chat.id, False))

@Client.on_callback_query(filters.regex(r"^(settings|set|delay|chathelp):"))
async def settings_callbacks(client, query):
    parts = query.data.split(":")
    action = parts[0]
    chat_id = int(parts[1])
    if query.from_user.id != OWNER.ID and not await is_chat_admin(client, chat_id, query.from_user.id):
        return await query.answer("Admins only.", show_alert=True)

    chat = await client.get_chat(chat_id)
    if action == "set":
        enabled = parts[2] == "on"
        database.set_chat_settings(chat, query.from_user.id, enabled=enabled)
        await query.answer("Updated ✅")
    elif action == "delay":
        seconds = int(parts[2])
        database.set_chat_settings(chat, query.from_user.id, enabled=True, delete_delay=seconds)
        await query.answer(f"Delay set to {human_time(seconds)} ✅")
    elif action == "chathelp":
        await query.answer("Help opened 📘")
        return await query.message.edit_text(chat_help_text(), reply_markup=settings_keyboard(chat_id, database.get_chat_settings(chat_id).get("enabled")))
    else:
        await query.answer("Refreshed 🔄")

    settings = database.get_chat_settings(chat_id)
    await query.message.edit_text(settings_text(chat, settings), reply_markup=settings_keyboard(chat_id, settings.get("enabled")))

@Client.on_message(CHAT_FILTER & filters.command("help"))
async def chat_help(client, message):
    await message.reply_text(
        chat_help_text() + "\n\nCredits: GitHub.com/mntgxo\nRepo: https://github.com/MN-BOTS/Mn-Auto-Delete",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Settings 🛠", callback_data=f"settings:{message.chat.id}")], [InlineKeyboardButton("Repo", url="https://github.com/MN-BOTS/Mn-Auto-Delete")]]),
        disable_web_page_preview=True,
    )
