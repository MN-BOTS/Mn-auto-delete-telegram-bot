import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserNotParticipant

import database
from config import OWNER
from utils import (
    start_keyboard,
    sleep_flood,
    main_menu_keyboard,
    back_home_keyboard,
    home_text,
    commands_text,
    features_text,
    credits_text,
    chat_help_text,
    safe_edit_message,
    safe_callback_answer,
)

log = logging.getLogger(__name__)


async def missing_fsubs(client, user_id):
    """Return force-sub chats the user has not joined."""
    subs = await asyncio.to_thread(database.list_fsubs)
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
                log.exception("Could not verify force-sub chat %s", sub.get("_id"))
                missing.append(sub)
        except UserNotParticipant:
            missing.append(sub)
        except Exception:
            log.exception("Could not verify force-sub chat %s", sub.get("_id"))
            missing.append(sub)

    return missing


async def reply_start(client, message, text, reply_markup):
    """Send directly so a helper cannot silently swallow the send error."""
    try:
        await client.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            reply_to_message_id=message.id,
        )
    except Exception:
        log.exception(
            "Failed to answer /start (chat_id=%s, message_id=%s)",
            getattr(getattr(message, "chat", None), "id", None),
            getattr(message, "id", None),
        )
        try:
            await client.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception:
            log.exception("Fallback send failed for /start")


@Client.on_message(filters.private & filters.incoming & filters.command("start"), group=-10)
async def start_command(client, message):
    user = getattr(message, "from_user", None)
    if not user:
        log.warning("Received /start without from_user (message_id=%s)", message.id)
        return

    log.info("Received /start from user_id=%s", user.id)

    # A temporary database error should not prevent a welcome response.
    try:
        await asyncio.to_thread(database.upsert_user, user)
    except Exception:
        log.exception("Could not save user %s during /start", user.id)

    try:
        missing = await missing_fsubs(client, user.id)
    except Exception:
        log.exception("Force-sub lookup failed for user %s", user.id)
        missing = []

    if missing:
        await reply_start(
            client,
            message,
            "**🔐 Force Subscribe Required**\n\n"
            "Please join every required channel/group, then tap **I Joined**.",
            start_keyboard(missing),
        )
        return

    await reply_start(
        client,
        message,
        home_text(),
        main_menu_keyboard(user.id == OWNER.ID),
    )


@Client.on_callback_query(filters.regex(r"^check_fsub$"))
async def check_fsub(client, query):
    try:
        await asyncio.to_thread(database.upsert_user, query.from_user)
        missing = await missing_fsubs(client, query.from_user.id)
    except Exception:
        log.exception("Force-sub check failed for user %s", query.from_user.id)
        await safe_callback_answer(
            query, "Verification is temporarily unavailable. Please try again.", show_alert=True
        )
        return

    if missing:
        await safe_callback_answer(query, "Please join all required chats first.", show_alert=True)
        await safe_edit_message(
            query.message,
            "**🔐 Force Subscribe Required**\n\n"
            "Please join every required channel/group, then tap **I Joined**.",
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


@Client.on_callback_query(filters.regex(r"^start:"))
async def start_callbacks(client, query):
    try:
        await asyncio.to_thread(database.upsert_user, query.from_user)
        missing = await missing_fsubs(client, query.from_user.id)
    except Exception:
        log.exception("Start-menu callback failed for user %s", query.from_user.id)
        await safe_callback_answer(
            query, "Menu is temporarily unavailable. Please try again.", show_alert=True
        )
        return

    if missing:
        await safe_callback_answer(query, "Join all required chats first.", show_alert=True)
        await safe_edit_message(
            query.message,
            "**🔐 Force Subscribe Required**\n\n"
            "Please join every required channel/group, then tap **I Joined**.",
            reply_markup=start_keyboard(missing),
            disable_web_page_preview=True,
        )
        return

    action = query.data.split(":", 1)[1]
    is_owner = query.from_user.id == OWNER.ID
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

    await safe_callback_answer(query, "Updated ✨")
    await safe_edit_message(
        query.message,
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
