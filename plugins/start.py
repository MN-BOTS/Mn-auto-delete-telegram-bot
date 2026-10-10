import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserNotParticipant

import database
from config import OWNER
from utils import (
    start_keyboard, sleep_flood, main_menu_keyboard, back_home_keyboard,
    home_text, commands_text, features_text, credits_text, chat_help_text,
    safe_edit_message, safe_callback_answer,
)

log = logging.getLogger(__name__)


async def db_call(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def missing_fsubs(client, user_id):
    try:
        subs = await db_call(database.list_fsubs)
    except Exception:
        log.exception("Could not load force-sub list")
        # Do not silently block every user if MongoDB has a temporary issue.
        return []

    missing = []
    for sub in subs:
        try:
            await client.get_chat_member(sub["_id"], user_id)
        except FloodWait as fw:
            await sleep_flood(fw.value)
            try:
                await client.get_chat_member(sub["_id"], user_id)
            except UserNotParticipant:
                missing.append(sub)
            except Exception:
                log.exception("Force-sub check failed for chat %s", sub.get("_id"))
                missing.append(sub)
        except UserNotParticipant:
            missing.append(sub)
        except Exception:
            log.exception("Force-sub check failed for chat %s", sub.get("_id"))
            # An inaccessible required channel should be surfaced as missing.
            missing.append(sub)
    return missing


async def send_menu(client, message, text, keyboard):
    try:
        await client.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
            reply_to_message_id=message.id,
        )
    except Exception:
        log.exception("Reply failed for command in chat %s", getattr(message.chat, "id", None))
        try:
            await client.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            log.exception("Fallback send failed")


@Client.on_message(filters.private & filters.incoming & filters.command(["start", "help"]), group=-10)
async def start_help_command(client, message):
    user = message.from_user
    if user is None:
        return
    command = (message.command or ["start"])[0].lower()
    log.info("Received /%s from user_id=%s", command, user.id)

    try:
        await db_call(database.upsert_user, user)
    except Exception:
        log.exception("Could not save user %s", user.id)

    missing = await missing_fsubs(client, user.id)
    if missing:
        await send_menu(
            client, message,
            "**🔐 Force Subscribe Required**\n\nPlease join every required channel/group, then tap **I Joined**.",
            start_keyboard(missing),
        )
        return

    is_owner = user.id == OWNER.ID
    await send_menu(client, message, home_text(), main_menu_keyboard(is_owner))


@Client.on_callback_query(filters.regex(r"^check_fsub$"))
async def check_fsub(client, query):
    try:
        await db_call(database.upsert_user, query.from_user)
        missing = await missing_fsubs(client, query.from_user.id)
        if missing:
            await safe_callback_answer(query, "Please join all required chats first.", show_alert=True)
            await safe_edit_message(
                query.message,
                "**🔐 Force Subscribe Required**\n\nPlease join every required channel/group, then tap **I Joined**.",
                reply_markup=start_keyboard(missing),
                disable_web_page_preview=True,
            )
            return

        await safe_callback_answer(query, "Verified ✅", show_alert=True)
        await safe_edit_message(
            query.message,
            home_text(),
            reply_markup=main_menu_keyboard(query.from_user.id == OWNER.ID),
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("check_fsub callback failed")
        await safe_callback_answer(query, "Verification failed. Check bot logs and try again.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^start:"))
async def start_callbacks(client, query):
    try:
        user = query.from_user
        await db_call(database.upsert_user, user)
        missing = await missing_fsubs(client, user.id)
        if missing:
            await safe_callback_answer(query, "Join all required chats first.", show_alert=True)
            await safe_edit_message(
                query.message,
                "**🔐 Force Subscribe Required**\n\nPlease join every required channel/group, then tap **I Joined**.",
                reply_markup=start_keyboard(missing),
                disable_web_page_preview=True,
            )
            return

        action = query.data.split(":", 1)[1]
        is_owner = user.id == OWNER.ID
        if action == "home":
            text, keyboard = home_text(), main_menu_keyboard(is_owner)
        elif action == "commands":
            text, keyboard = commands_text(), back_home_keyboard(is_owner)
        elif action == "features":
            text, keyboard = features_text(), back_home_keyboard(is_owner)
        elif action == "credits":
            text, keyboard = credits_text(), back_home_keyboard(is_owner)
        else:
            text, keyboard = chat_help_text(), back_home_keyboard(is_owner)

        await safe_callback_answer(query, "Updated ✅")
        await safe_edit_message(
            query.message, text, reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Start menu callback failed for data=%r", getattr(query, "data", None))
        await safe_callback_answer(query, "Menu error. Please check Koyeb logs.", show_alert=True)
