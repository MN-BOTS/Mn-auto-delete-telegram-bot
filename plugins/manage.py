import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER
import database
from utils import (
    parse_time,
    human_time,
    is_chat_admin,
    settings_keyboard,
    settings_text,
    chat_help_text,
    safe_reply,
    safe_edit_message,
    safe_callback_answer,
)

log = logging.getLogger(__name__)
CHAT_FILTER = filters.group | filters.channel


async def db_call(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def can_manage(client, message):
    if message.from_user and message.from_user.id == OWNER.ID:
        return True
    user_id = getattr(message.from_user, "id", None)
    return await is_chat_admin(client, message.chat.id, user_id)


async def deny(message):
    await safe_reply(
        message,
        "**Only the group/channel owner or admins can manage this bot here.**",
    )


@Client.on_message(CHAT_FILTER & filters.command(["settings", "autodelete", "panel"]))
async def settings_cmd(client, message):
    try:
        await db_call(database.save_chat, message.chat, getattr(message.from_user, "id", None))
        if not await can_manage(client, message):
            return await deny(message)

        settings = await db_call(database.get_chat_settings, message.chat.id)
        await safe_reply(
            message,
            settings_text(message.chat, settings),
            reply_markup=settings_keyboard(message.chat.id, settings.get("enabled")),
        )
    except Exception:
        log.exception("Settings command failed in chat %s", message.chat.id)
        await safe_reply(message, "Could not load settings. Please try again.")


@Client.on_message(CHAT_FILTER & filters.command(["setdelete", "deletedelay"]))
async def set_delete_cmd(client, message):
    if not await can_manage(client, message):
        return await deny(message)
    if len(message.command) < 2:
        return await safe_reply(
            message, "Usage: `/setdelete 30s` or `/setdelete off`", quote=True
        )
    try:
        seconds = parse_time(message.command[1])
    except ValueError as err:
        return await safe_reply(
            message,
            f"Invalid time: {err}\nExamples: `10s`, `5m`, `1h`, `off` (1 hour max)",
            quote=True,
        )

    try:
        settings = await db_call(
            database.set_chat_settings,
            message.chat,
            message.from_user.id,
            enabled=seconds > 0,
            delete_delay=seconds,
        )
        await safe_reply(
            message,
            f"**Updated ✅**\n\nAuto-delete: {'Enabled' if seconds > 0 else 'Disabled'}\n"
            f"Time: `{human_time(seconds)}`",
            reply_markup=settings_keyboard(message.chat.id, settings.get("enabled")),
        )
    except Exception:
        log.exception("Could not update delete timer for chat %s", message.chat.id)
        await safe_reply(message, "Could not update the timer. Please try again.")


@Client.on_message(CHAT_FILTER & filters.command("deleteon"))
async def delete_on_cmd(client, message):
    if not await can_manage(client, message):
        return await deny(message)
    try:
        settings = await db_call(database.get_chat_settings, message.chat.id)
        delay = min(int(settings.get("delete_delay") or 0), 3600) or 60
        settings = await db_call(
            database.set_chat_settings,
            message.chat,
            message.from_user.id,
            enabled=True,
            delete_delay=delay,
        )
        await safe_reply(
            message,
            f"Auto-delete enabled ✅\nTime: `{human_time(delay)}`",
            reply_markup=settings_keyboard(message.chat.id, True),
        )
    except Exception:
        log.exception("Could not enable auto-delete for chat %s", message.chat.id)
        await safe_reply(message, "Could not enable auto-delete. Please try again.")


@Client.on_message(CHAT_FILTER & filters.command(["deleteoff", "resetdelete"]))
async def delete_off_cmd(client, message):
    if not await can_manage(client, message):
        return await deny(message)
    try:
        await db_call(
            database.set_chat_settings,
            message.chat,
            message.from_user.id,
            enabled=False,
        )
        await safe_reply(
            message,
            "Auto-delete disabled 📴\nNo new messages will be scheduled.",
            reply_markup=settings_keyboard(message.chat.id, False),
        )
    except Exception:
        log.exception("Could not disable auto-delete for chat %s", message.chat.id)
        await safe_reply(message, "Could not disable auto-delete. Please try again.")


@Client.on_callback_query(filters.regex(r"^(settings|set|delay|chathelp):"))
async def settings_callbacks(client, query):
    try:
        parts = query.data.split(":")
        action = parts[0]
        chat_id = int(parts[1])

        if query.from_user.id != OWNER.ID and not await is_chat_admin(
            client, chat_id, query.from_user.id
        ):
            return await safe_callback_answer(query, "Admins only.", show_alert=True)

        try:
            chat = await client.get_chat(chat_id)
        except Exception:
            log.exception("Cannot access settings chat %s", chat_id)
            return await safe_callback_answer(
                query, "I cannot access that chat anymore.", show_alert=True
            )

        if action == "set":
            enabled = parts[2] == "on"
            await db_call(
                database.set_chat_settings, chat, query.from_user.id, enabled=enabled
            )
            await safe_callback_answer(query, "Updated ✅")
        elif action == "delay":
            seconds = min(max(int(parts[2]), 0), 3600)
            await db_call(
                database.set_chat_settings,
                chat,
                query.from_user.id,
                enabled=seconds > 0,
                delete_delay=seconds,
            )
            await safe_callback_answer(query, f"Delay set to {human_time(seconds)} ✅")
        elif action == "chathelp":
            settings = await db_call(database.get_chat_settings, chat_id)
            await safe_callback_answer(query, "Help opened 📘")
            await safe_edit_message(
                query.message,
                chat_help_text(),
                reply_markup=settings_keyboard(chat_id, settings.get("enabled")),
                disable_web_page_preview=True,
            )
            return
        else:
            await safe_callback_answer(query, "Refreshed 🔄")

        settings = await db_call(database.get_chat_settings, chat_id)
        await safe_edit_message(
            query.message,
            settings_text(chat, settings),
            reply_markup=settings_keyboard(chat_id, settings.get("enabled")),
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Settings callback failed for %r", getattr(query, "data", None))
        await safe_callback_answer(
            query, "Settings error. Please try again.", show_alert=True
        )


@Client.on_message(CHAT_FILTER & filters.command("help"))
async def chat_help(client, message):
    await safe_reply(
        message,
        chat_help_text()
        + "\n\nCredits: GitHub.com/mntgxo\nRepo: https://github.com/MN-BOTS/Mn-auto-delete-telegram-bot",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Open Settings 🛠", callback_data=f"settings:{message.chat.id}")],
            [InlineKeyboardButton("Repo", url="https://github.com/MN-BOTS/Mn-auto-delete-telegram-bot")],
        ]),
        disable_web_page_preview=True,
    )
