import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER, BROADCAST
import database
from utils import forward_with_flood, REPO_URL, DEV_URL


def owner_only(_, __, message):
    return bool(message.from_user and message.from_user.id == OWNER.ID)

owner_filter = filters.create(owner_only)


def owner_stats():
    total_users = database.users.count_documents({})
    total_chats = database.chats.count_documents({})
    enabled_chats = database.chats.count_documents({"enabled": True})
    pending = database.messages.count_documents({"status": "pending"})
    fsubs = database.fsubs.count_documents({})
    return total_users, total_chats, enabled_chats, pending, fsubs


def owner_panel_text():
    total_users, total_chats, enabled_chats, pending, fsubs = owner_stats()
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
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Stats 🔄", callback_data="owner:stats"), InlineKeyboardButton("Force-Subs 🔐", callback_data="owner:fsubs")],
            [InlineKeyboardButton("Broadcast Help 📣", callback_data="owner:broadcast"), InlineKeyboardButton("Commands 📚", callback_data="owner:commands")],
            [InlineKeyboardButton("Repo ⭐", url=REPO_URL), InlineKeyboardButton("Developer", url=DEV_URL)],
        ]
    )


def owner_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Owner Panel", callback_data="owner:panel")], [InlineKeyboardButton("Repo ⭐", url=REPO_URL)]])


def fsub_text():
    subs = database.list_fsubs()
    if not subs:
        return "**🔐 Force-Sub Chats**\n\nNo force-sub chats configured."
    lines = ["**🔐 Force-Sub Chats**\n"]
    for sub in subs:
        lines.append(f"• `{sub['_id']}` - {sub.get('title') or sub.get('username') or 'Unknown'}")
    return "\n".join(lines)


@Client.on_message(filters.private & owner_filter & filters.command("admin"))
async def admin_panel(client, message):
    await message.reply_text(owner_panel_text(), reply_markup=owner_panel_keyboard(), disable_web_page_preview=True)

@Client.on_message(filters.private & owner_filter & filters.command("stats"))
async def stats_cmd(client, message):
    await admin_panel(client, message)

@Client.on_callback_query(filters.regex(r"^owner:"))
async def owner_callbacks(client, query):
    if query.from_user.id != OWNER.ID:
        return await query.answer("Owner only.", show_alert=True)
    action = query.data.split(":", 1)[1]
    if action in {"panel", "stats"}:
        await query.answer("Panel refreshed ✅")
        return await query.message.edit_text(owner_panel_text(), reply_markup=owner_panel_keyboard(), disable_web_page_preview=True)
    if action == "fsubs":
        await query.answer("Force-sub list opened 🔐")
        return await query.message.edit_text(fsub_text(), reply_markup=owner_back_keyboard(), disable_web_page_preview=True)
    if action == "broadcast":
        await query.answer("Broadcast help opened 📣")
        return await query.message.edit_text(
            "**📣 Broadcast**\n\nReply to any message with `/broadcast`. The bot forwards it to bot PM users, groups, and channels. "
            "If a PM user blocked the bot or deleted the account, that user is removed from MongoDB automatically.",
            reply_markup=owner_back_keyboard(),
            disable_web_page_preview=True,
        )
    await query.answer("Commands opened 📚")
    await query.message.edit_text(
        "**📚 Owner Commands**\n\n"
        "• `/admin` - rich owner panel\n"
        "• `/broadcast` - reply and forward everywhere\n"
        "• `/addfsub <chat_id> [invite_link]`\n"
        "• `/delfsub <chat_id>`\n"
        "• `/fsubs`\n"
        "• `/stats`",
        reply_markup=owner_back_keyboard(),
        disable_web_page_preview=True,
    )

@Client.on_message(filters.private & owner_filter & filters.command("addfsub"))
async def add_fsub_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/addfsub -1001234567890 https://t.me/example`", reply_markup=owner_back_keyboard())
    try:
        chat_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("Chat ID must be numeric.", reply_markup=owner_back_keyboard())
    invite_link = message.command[2] if len(message.command) > 2 else None
    title = None
    username = None
    try:
        chat = await client.get_chat(chat_id)
        title = chat.title
        username = chat.username
        invite_link = invite_link or chat.invite_link
    except Exception:
        pass
    database.add_fsub(chat_id, title=title, username=username, invite_link=invite_link)
    await message.reply_text(f"Force-sub chat added ✅\nID: `{chat_id}`", reply_markup=owner_back_keyboard())

@Client.on_message(filters.private & owner_filter & filters.command("delfsub"))
async def del_fsub_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delfsub -1001234567890`", reply_markup=owner_back_keyboard())
    database.remove_fsub(int(message.command[1]))
    await message.reply_text("Force-sub chat removed ✅", reply_markup=owner_back_keyboard())

@Client.on_message(filters.private & owner_filter & filters.command("fsubs"))
async def list_fsub_cmd(client, message):
    await message.reply_text(fsub_text(), reply_markup=owner_back_keyboard(), disable_web_page_preview=True)

@Client.on_message(filters.private & owner_filter & filters.command("broadcast"))
async def broadcast_cmd(client, message):
    if not message.reply_to_message:
        return await message.reply_text(
            "Reply to the message you want to broadcast. The bot will use Telegram forward, not copy.",
            reply_markup=owner_back_keyboard(),
        )

    targets = set()
    targets.update(user["_id"] for user in database.users.find({}, {"_id": 1}))
    targets.update(chat["_id"] for chat in database.chats.find({}, {"_id": 1}))

    if not targets:
        return await message.reply_text("No broadcast targets found yet.", reply_markup=owner_back_keyboard())

    status_message = await message.reply_text(f"Broadcast started to `{len(targets)}` targets using forward method...")
    stats = {"sent": 0, "blocked_removed": 0, "forbidden": 0, "failed": 0}
    for target in targets:
        result = await forward_with_flood(message.reply_to_message, target)
        stats[result] = stats.get(result, 0) + 1
        await asyncio.sleep(BROADCAST.SLEEP)

    database.broadcasts.insert_one(
        {
            "from_user": message.from_user.id,
            "message_id": message.reply_to_message.id,
            "targets": len(targets),
            "stats": stats,
            "created_at": database.now_utc(),
        }
    )
    await status_message.edit_text(
        "**Broadcast completed ✅**\n\n"
        f"Sent: `{stats['sent']}`\n"
        f"Blocked/deleted PM users removed from DB: `{stats['blocked_removed']}`\n"
        f"Forbidden chats: `{stats['forbidden']}`\n"
        f"Failed: `{stats['failed']}`",
        reply_markup=owner_panel_keyboard(),
    )
