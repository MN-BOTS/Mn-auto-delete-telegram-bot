import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER, BROADCAST
import database
from utils import (
    forward_with_flood,
    REPO_URL,
    DEV_URL,
    safe_reply,
    safe_edit_message,
    safe_callback_answer,
)

log = logging.getLogger(__name__)


def owner_only(_, __, message):
    return bool(message.from_user and message.from_user.id == OWNER.ID)


owner_filter = filters.create(owner_only)


async def db_call(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def owner_stats():
    def read_stats():
        return (
            database.users.count_documents({}),
            database.chats.count_documents({}),
            database.chats.count_documents({"enabled": True}),
            database.messages.count_documents({"status": "pending"}),
            database.fsubs.count_documents({}),
        )
    return await asyncio.to_thread(read_stats)


async def owner_panel_text():
    total_users, total_chats, enabled_chats, pending, fsubs = await owner_stats()
    return (
        "**👑 Owner Management Panel**\n\n"
        f"Users in DB: `{total_users}`\n"
        f"Known groups/channels: `{total_chats}`\n"
        f"Auto-delete enabled chats: `{enabled_chats}`\n"
        f"Pending delete jobs: `{pending}`\n"
        f"Force-sub chats: `{fsubs}`\n\n"
        "Use the buttons below or owner commands for full control."
    )


def owner_panel_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Stats 🔄", callback_data="owner:stats"),
            InlineKeyboardButton("Force-Subs 🔐", callback_data="owner:fsubs"),
        ],
        [
            InlineKeyboardButton("Broadcast Help 📣", callback_data="owner:broadcast"),
            InlineKeyboardButton("Commands 📚", callback_data="owner:commands"),
        ],
        [
            InlineKeyboardButton("Repo ⭐", url=REPO_URL),
            InlineKeyboardButton("Developer", url=DEV_URL),
        ],
    ])


def owner_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Owner Panel", callback_data="owner:panel")],
        [InlineKeyboardButton("Repo ⭐", url=REPO_URL)],
    ])


async def fsub_text():
    subs = await db_call(database.list_fsubs)
    if not subs:
        return "**🔐 Force-Sub Chats**\n\nNo force-sub chats configured."
    lines = ["**🔐 Force-Sub Chats**\n"]
    for sub in subs:
        lines.append(
            f"• `{sub['_id']}` - "
            f"{sub.get('title') or sub.get('username') or 'Unknown'}"
        )
    return "\n".join(lines)


@Client.on_message(filters.private & owner_filter & filters.command("admin"))
async def admin_panel(client, message):
    log.info("Owner command /admin received from %s", message.from_user.id)
    try:
        text = await owner_panel_text()
        await safe_reply(
            message, text, reply_markup=owner_panel_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Failed to render owner panel")
        await safe_reply(message, "Could not load the owner panel. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("stats"))
async def stats_cmd(client, message):
    log.info("Owner command /stats received from %s", message.from_user.id)
    await admin_panel(client, message)


@Client.on_callback_query(filters.regex(r"^owner:"))
async def owner_callbacks(client, query):
    if query.from_user.id != OWNER.ID:
        await safe_callback_answer(query, "Owner only.", show_alert=True)
        return

    action = query.data.split(":", 1)[1]
    try:
        if action in {"panel", "stats"}:
            await safe_callback_answer(query, "Panel refreshed ✅")
            await safe_edit_message(
                query.message, await owner_panel_text(),
                reply_markup=owner_panel_keyboard(),
                disable_web_page_preview=True,
            )
            return

        if action == "fsubs":
            await safe_callback_answer(query, "Force-sub list opened 🔐")
            await safe_edit_message(
                query.message, await fsub_text(),
                reply_markup=owner_back_keyboard(),
                disable_web_page_preview=True,
            )
            return

        if action == "broadcast":
            text = (
                "**📣 Broadcast**\n\n"
                "Reply to any message with `/broadcast`. The bot forwards it to "
                "bot PM users, groups, and channels."
            )
        else:
            text = (
                "**📚 Owner Commands**\n\n"
                "• `/admin` - rich owner panel\n"
                "• `/broadcast` - reply and forward everywhere\n"
                "• `/addfsub <chat_id> [invite_link]`\n"
                "• `/delfsub <chat_id>`\n"
                "• `/fsubs`\n"
                "• `/stats`"
            )

        await safe_callback_answer(query, "Opened ✅")
        await safe_edit_message(
            query.message, text, reply_markup=owner_back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Owner callback failed: %r", query.data)
        await safe_callback_answer(query, "Owner panel error. Check Koyeb logs.", show_alert=True)


@Client.on_message(filters.private & owner_filter & filters.command("addfsub"))
async def add_fsub_cmd(client, message):
    log.info("Owner command /addfsub received from %s", message.from_user.id)
    if len(message.command) < 2:
        await safe_reply(
            message, "Usage: `/addfsub -1001234567890 https://t.me/example`",
            reply_markup=owner_back_keyboard(),
        )
        return

    try:
        chat_id = int(message.command[1])
    except ValueError:
        await safe_reply(message, "Chat ID must be numeric.")
        return

    invite_link = message.command[2] if len(message.command) > 2 else None
    title = username = None
    try:
        chat = await client.get_chat(chat_id)
        title = chat.title or chat.first_name
        username = chat.username
        invite_link = invite_link or getattr(chat, "invite_link", None)
    except Exception:
        log.exception("Could not fetch force-sub chat metadata for %s", chat_id)

    try:
        await db_call(
            database.add_fsub, chat_id,
            title=title, username=username, invite_link=invite_link,
        )
        await safe_reply(
            message, f"Force-sub chat added ✅\nID: `{chat_id}`",
            reply_markup=owner_back_keyboard(),
        )
    except Exception:
        log.exception("Could not add force-sub chat %s", chat_id)
        await safe_reply(message, "Could not save that chat. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("delfsub"))
async def del_fsub_cmd(client, message):
    log.info("Owner command /delfsub received from %s", message.from_user.id)
    if len(message.command) < 2:
        await safe_reply(message, "Usage: `/delfsub -1001234567890`")
        return
    try:
        chat_id = int(message.command[1])
        await db_call(database.remove_fsub, chat_id)
        await safe_reply(message, f"Force-sub chat removed ✅\nID: `{chat_id}`")
    except ValueError:
        await safe_reply(message, "Chat ID must be numeric.")
    except Exception:
        log.exception("Could not remove force-sub chat")
        await safe_reply(message, "Could not remove that chat. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("fsubs"))
async def list_fsub_cmd(client, message):
    log.info("Owner command /fsubs received from %s", message.from_user.id)
    try:
        await safe_reply(
            message, await fsub_text(), reply_markup=owner_back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Could not list force-sub chats")
        await safe_reply(message, "Could not load force-sub chats. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("broadcast"))
async def broadcast_cmd(client, message):
    log.info("Owner command /broadcast received from %s", message.from_user.id)
    if not message.reply_to_message:
        await safe_reply(
            message,
            "Reply to the message you want to broadcast. The bot will use Telegram forward, not copy.",
            reply_markup=owner_back_keyboard(),
        )
        return

    try:
        def get_targets():
            targets = {u["_id"] for u in database.users.find({}, {"_id": 1})}
            targets.update(c["_id"] for c in database.chats.find({}, {"_id": 1}))
            return targets

        targets = await asyncio.to_thread(get_targets)
        if not targets:
            await safe_reply(message, "No broadcast targets found yet.")
            return

        status_message = await safe_reply(
            message, f"Broadcast started to `{len(targets)}` targets using forward method..."
        )
        stats = {"sent": 0, "blocked_removed": 0, "forbidden": 0, "failed": 0}
        for target in targets:
            result = await forward_with_flood(message.reply_to_message, target)
            stats[result] = stats.get(result, 0) + 1
            await asyncio.sleep(BROADCAST.SLEEP)

        await db_call(
            database.broadcasts.insert_one,
            {
                "from_user": message.from_user.id,
                "message_id": message.reply_to_message.id,
                "targets": len(targets),
                "stats": stats,
                "created_at": database.now_utc(),
            },
        )
        result_text = (
            "**Broadcast completed ✅**\n\n"
            f"Sent: `{stats['sent']}`\n"
            f"Blocked/deleted PM users removed from DB: `{stats['blocked_removed']}`\n"
            f"Forbidden chats: `{stats['forbidden']}`\n"
            f"Failed: `{stats['failed']}`"
        )
        if status_message:
            await safe_edit_message(status_message, result_text, reply_markup=owner_panel_keyboard())
        else:
            await safe_reply(message, result_text, reply_markup=owner_panel_keyboard())
    except Exception:
        log.exception("Broadcast failed")
        await safe_reply(message, "Broadcast failed. Check Koyeb logs.")
