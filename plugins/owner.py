"""Owner commands and panel callbacks with visible fallbacks and useful logs."""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER, BROADCAST
import database
from utils import forward_with_flood, REPO_URL, DEV_URL, safe_callback_answer

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
    users, chats, enabled, pending, fsubs = await owner_stats()
    return (
        "**👑 Owner Management Panel**\n\n"
        f"Users in DB: `{users}`\n"
        f"Known groups/channels: `{chats}`\n"
        f"Auto-delete enabled chats: `{enabled}`\n"
        f"Pending delete jobs: `{pending}`\n"
        f"Force-sub chats: `{fsubs}`\n\n"
        "Use the buttons below or owner commands for full control."
    )


def owner_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Stats 🔄", callback_data="owner:stats"), InlineKeyboardButton("Force-Subs 🔐", callback_data="owner:fsubs")],
        [InlineKeyboardButton("Broadcast Help 📣", callback_data="owner:broadcast"), InlineKeyboardButton("Commands 📚", callback_data="owner:commands")],
        [InlineKeyboardButton("Repo ⭐", url=REPO_URL), InlineKeyboardButton("Developer", url=DEV_URL)],
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
        lines.append(f"• `{sub['_id']}` - {sub.get('title') or sub.get('username') or 'Unknown'}")
    return "\n".join(lines)


async def reply_reliably(client, message, text, **kwargs):
    """Reply normally; if helper/API failure occurs, log and try a fresh send."""
    try:
        return await message.reply_text(text, **kwargs)
    except Exception:
        log.exception("reply_text failed; trying send_message")
        try:
            return await client.send_message(message.chat.id, text, **kwargs)
        except Exception:
            log.exception("send_message fallback failed")
            return None


async def show_panel(client, message, text, keyboard):
    """Edit the callback's message, but send a new message if editing fails."""
    try:
        await message.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        log.exception("Could not edit owner-panel message; sending a new panel")
        try:
            await client.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return True
        except Exception:
            log.exception("Could not send fallback owner panel")
            return False


@Client.on_message(filters.private & owner_filter & filters.command("admin"))
async def admin_panel(client, message):
    log.info("Owner command /admin received from user_id=%s", message.from_user.id)
    try:
        text = await owner_panel_text()
        await reply_reliably(client, message, text, reply_markup=owner_panel_keyboard(), disable_web_page_preview=True)
    except Exception:
        log.exception("Failed to build /admin panel")
        await reply_reliably(client, message, "Could not load the owner panel. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("stats"))
async def stats_cmd(client, message):
    log.info("Owner command /stats received from user_id=%s", message.from_user.id)
    await admin_panel(client, message)


@Client.on_callback_query(filters.regex(r"^owner:"))
async def owner_callbacks(client, query):
    user = query.from_user
    if not user or user.id != OWNER.ID:
        await safe_callback_answer(query, "Owner only.", show_alert=True)
        return

    action = (query.data or "owner:panel").split(":", 1)[1]
    log.info("Owner callback received: %s from user_id=%s", action, user.id)
    try:
        if action in {"panel", "stats"}:
            text, keyboard = await owner_panel_text(), owner_panel_keyboard()
        elif action == "fsubs":
            text, keyboard = await fsub_text(), owner_back_keyboard()
        elif action == "broadcast":
            text = (
                "**📣 Broadcast Help**\n\n"
                "Reply to the message you want to broadcast, then send `/broadcast`. "
                "The bot forwards it to saved bot users and known groups/channels."
            )
            keyboard = owner_back_keyboard()
        else:
            text = (
                "**📚 Owner Commands**\n\n"
                "• `/admin` - owner panel\n• `/stats` - database statistics\n"
                "• `/broadcast` - reply to a message and broadcast it\n"
                "• `/addfsub <chat_id> [invite_link]`\n• `/delfsub <chat_id>`\n• `/fsubs`"
            )
            keyboard = owner_back_keyboard()

        # Do not report a successful refresh until an edit or fallback send succeeds.
        success = await show_panel(client, query.message, text, keyboard)
        await safe_callback_answer(query, "Panel opened ✅" if success else "Could not open panel; check Koyeb logs.", show_alert=not success)
    except Exception:
        log.exception("Owner callback crashed for data=%r", query.data)
        await safe_callback_answer(query, "Owner panel failed. Check Koyeb logs.", show_alert=True)


@Client.on_message(filters.private & owner_filter & filters.command("addfsub"))
async def add_fsub_cmd(client, message):
    log.info("Owner command /addfsub received from user_id=%s", message.from_user.id)
    if len(message.command) < 2:
        return await reply_reliably(client, message, "Usage: `/addfsub -1001234567890 https://t.me/example`", reply_markup=owner_back_keyboard())
    try:
        chat_id = int(message.command[1])
    except ValueError:
        return await reply_reliably(client, message, "Chat ID must be numeric.")
    invite_link = message.command[2] if len(message.command) > 2 else None
    title = username = None
    try:
        chat = await client.get_chat(chat_id)
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None)
        username = getattr(chat, "username", None)
        invite_link = invite_link or getattr(chat, "invite_link", None)
    except Exception:
        log.warning("Could not fetch chat metadata for fsub %s", chat_id, exc_info=True)
    try:
        await db_call(database.add_fsub, chat_id, title=title, username=username, invite_link=invite_link)
        await reply_reliably(client, message, f"Force-sub chat added ✅\nID: `{chat_id}`", reply_markup=owner_back_keyboard())
    except Exception:
        log.exception("Could not save fsub %s", chat_id)
        await reply_reliably(client, message, "Could not save that chat. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("delfsub"))
async def del_fsub_cmd(client, message):
    log.info("Owner command /delfsub received from user_id=%s", message.from_user.id)
    if len(message.command) < 2:
        return await reply_reliably(client, message, "Usage: `/delfsub -1001234567890`")
    try:
        chat_id = int(message.command[1])
        await db_call(database.remove_fsub, chat_id)
        await reply_reliably(client, message, f"Force-sub chat removed ✅\nID: `{chat_id}`")
    except ValueError:
        await reply_reliably(client, message, "Chat ID must be numeric.")
    except Exception:
        log.exception("Could not remove fsub")
        await reply_reliably(client, message, "Could not remove that chat. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("fsubs"))
async def list_fsub_cmd(client, message):
    log.info("Owner command /fsubs received from user_id=%s", message.from_user.id)
    try:
        await reply_reliably(client, message, await fsub_text(), reply_markup=owner_back_keyboard(), disable_web_page_preview=True)
    except Exception:
        log.exception("Could not load fsub list")
        await reply_reliably(client, message, "Could not load force-sub chats. Check Koyeb logs.")


@Client.on_message(filters.private & owner_filter & filters.command("broadcast"))
async def broadcast_cmd(client, message):
    log.info("Owner command /broadcast received from user_id=%s", message.from_user.id)
    if not message.reply_to_message:
        return await reply_reliably(client, message, "Reply to the message you want to broadcast, then send `/broadcast`.", reply_markup=owner_back_keyboard())

    try:
        def get_targets():
            targets = {u["_id"] for u in database.users.find({}, {"_id": 1})}
            targets.update(c["_id"] for c in database.chats.find({}, {"_id": 1}))
            return targets

        targets = await asyncio.to_thread(get_targets)
        if not targets:
            return await reply_reliably(client, message, "No broadcast targets found yet.")
        status = await reply_reliably(client, message, f"Broadcast started to `{len(targets)}` targets...")
        results = {"sent": 0, "blocked_removed": 0, "forbidden": 0, "failed": 0}
        for target in targets:
            result = await forward_with_flood(message.reply_to_message, target)
            results[result] = results.get(result, 0) + 1
            await asyncio.sleep(BROADCAST.SLEEP)
        await db_call(database.broadcasts.insert_one, {
            "from_user": message.from_user.id,
            "message_id": message.reply_to_message.id,
            "targets": len(targets),
            "stats": results,
            "created_at": database.now_utc(),
        })
        text = (
            "**Broadcast completed ✅**\n\n"
            f"Sent: `{results['sent']}`\nBlocked/deleted PM users removed: `{results['blocked_removed']}`\n"
            f"Forbidden chats: `{results['forbidden']}`\nFailed: `{results['failed']}`"
        )
        if status:
            try:
                await status.edit_text(text, reply_markup=owner_panel_keyboard())
            except Exception:
                log.exception("Could not edit broadcast status")
                await client.send_message(message.chat.id, text, reply_markup=owner_panel_keyboard())
        else:
            await reply_reliably(client, message, text, reply_markup=owner_panel_keyboard())
    except Exception:
        log.exception("Broadcast failed")
        await reply_reliably(client, message, "Broadcast failed. Check Koyeb logs.")
